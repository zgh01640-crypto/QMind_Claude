import os
from contextlib import contextmanager
from itertools import count
from threading import BoundedSemaphore, Lock, get_ident, local
from time import monotonic

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

_POOL_LOCK = Lock()
_POOL: ThreadedConnectionPool | None = None
_POOL_SLOTS: BoundedSemaphore | None = None
_POOL_MAX = 0
_THREAD_STATE = local()
_LEASE_LOCK = Lock()
_LEASE_SEQUENCE = count(1)
_ACTIVE_LEASES: dict[int, dict[str, float | int]] = {}
_POOL_WAITING = 0
_BACKGROUND_POOL_LOCK = Lock()
_BACKGROUND_POOL_SLOTS: BoundedSemaphore | None = None
_BACKGROUND_POOL_LIMIT = 0
_BACKGROUND_POOL_WAITING = 0
_BACKGROUND_POOL_IN_USE = 0


class DatabasePoolBusyError(RuntimeError):
    """Raised when the bounded database pool cannot provide a short lease."""


def _pool_config() -> tuple[str, int, int]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 未设置，请检查 .env 文件")
    max_connections = max(2, int(os.getenv("DB_POOL_MAX", "24")))
    wait_seconds = max(1, int(os.getenv("DB_POOL_WAIT_SECONDS", "15")))
    return url, max_connections, wait_seconds


def _get_pool() -> tuple[ThreadedConnectionPool, BoundedSemaphore, int]:
    global _POOL, _POOL_SLOTS, _POOL_MAX
    if _POOL is not None and _POOL_SLOTS is not None:
        return _POOL, _POOL_SLOTS, _POOL_MAX
    with _POOL_LOCK:
        if _POOL is None or _POOL_SLOTS is None:
            url, max_connections, _ = _pool_config()
            _POOL = ThreadedConnectionPool(1, max_connections, url)
            _POOL_SLOTS = BoundedSemaphore(max_connections)
            _POOL_MAX = max_connections
    return _POOL, _POOL_SLOTS, _POOL_MAX


def _background_pool_config() -> int:
    _, max_connections, _ = _pool_config()
    try:
        configured = int(os.getenv("PRICING_BACKGROUND_DB_CONCURRENCY", "16"))
    except ValueError:
        configured = 16
    return max(1, min(configured, max_connections - 1))


def _get_background_pool_slots() -> tuple[BoundedSemaphore, int]:
    global _BACKGROUND_POOL_SLOTS, _BACKGROUND_POOL_LIMIT
    limit = _background_pool_config()
    with _BACKGROUND_POOL_LOCK:
        if _BACKGROUND_POOL_SLOTS is None:
            _BACKGROUND_POOL_SLOTS = BoundedSemaphore(limit)
            _BACKGROUND_POOL_LIMIT = limit
    return _BACKGROUND_POOL_SLOTS, _BACKGROUND_POOL_LIMIT


def _thread_connections() -> list["PooledConnection"]:
    connections = getattr(_THREAD_STATE, "connections", None)
    if connections is None:
        connections = []
        _THREAD_STATE.connections = connections
    return connections


def _model_release_enabled() -> bool:
    return bool(getattr(_THREAD_STATE, "release_before_model", False))


def _background_database_enabled() -> bool:
    return bool(getattr(_THREAD_STATE, "background_database", False))


class PooledConnection:
    """A lazy pool lease compatible with the existing psycopg2 call sites.

    ``suspend`` returns a checked-out physical connection before a long model call.
    The next cursor/commit operation checks out a fresh short-lived lease.
    """

    def __init__(self) -> None:
        self._conn = None
        self._lease_id: int | None = None
        self._open_cursors = 0
        self._return_pending = False
        self._pin_depth = 0
        self._closed = False
        self._background_slot_acquired = False
        _thread_connections().append(self)

    def _acquire_background_slot(self) -> None:
        if not _background_database_enabled() or self._background_slot_acquired:
            return
        background_slots, _ = _get_background_pool_slots()
        global _BACKGROUND_POOL_WAITING, _BACKGROUND_POOL_IN_USE
        with _BACKGROUND_POOL_LOCK:
            _BACKGROUND_POOL_WAITING += 1
        try:
            # Background database work queues here without consuming the
            # ordinary pool wait timeout or a business retry attempt.
            background_slots.acquire()
        finally:
            with _BACKGROUND_POOL_LOCK:
                _BACKGROUND_POOL_WAITING -= 1
        with _BACKGROUND_POOL_LOCK:
            _BACKGROUND_POOL_IN_USE += 1
        self._background_slot_acquired = True

    def _release_background_slot(self) -> None:
        if not self._background_slot_acquired:
            return
        background_slots, _ = _get_background_pool_slots()
        self._background_slot_acquired = False
        global _BACKGROUND_POOL_IN_USE
        with _BACKGROUND_POOL_LOCK:
            _BACKGROUND_POOL_IN_USE = max(0, _BACKGROUND_POOL_IN_USE - 1)
        background_slots.release()

    def _acquire(self):
        if self._closed:
            raise RuntimeError("数据库连接已关闭")
        if self._conn is not None:
            return self._conn
        self._acquire_background_slot()
        pool, slots, _ = _get_pool()
        _, _, wait_seconds = _pool_config()
        global _POOL_WAITING
        with _LEASE_LOCK:
            _POOL_WAITING += 1
        try:
            if not slots.acquire(timeout=wait_seconds):
                self._release_background_slot()
                raise DatabasePoolBusyError("数据库连接池繁忙，请稍后重试")
        finally:
            with _LEASE_LOCK:
                _POOL_WAITING -= 1
        try:
            conn = pool.getconn()
        except Exception:
            slots.release()
            self._release_background_slot()
            raise
        lease_id = next(_LEASE_SEQUENCE)
        with _LEASE_LOCK:
            _ACTIVE_LEASES[lease_id] = {"started_at": monotonic(), "thread_id": get_ident()}
        self._conn = conn
        self._lease_id = lease_id
        return conn

    def cursor(self, *args, **kwargs):
        cursor = self._acquire().cursor(*args, **kwargs)
        self._open_cursors += 1
        return _TrackedCursor(self, cursor)

    def commit(self) -> None:
        self._finish_transaction("commit")

    def rollback(self) -> None:
        if self._conn is not None:
            self._finish_transaction("rollback")

    def _return_to_pool(self, conn) -> None:
        lease_id = self._lease_id
        self._conn = None
        self._lease_id = None
        self._return_pending = False
        pool, slots, _ = _get_pool()
        try:
            pool.putconn(conn, close=bool(getattr(conn, "closed", False)))
        finally:
            if lease_id is not None:
                with _LEASE_LOCK:
                    _ACTIVE_LEASES.pop(lease_id, None)
            slots.release()
            self._release_background_slot()

    def _finish_transaction(self, action: str, *, suppress_errors: bool = False) -> None:
        conn = self._acquire()
        failure: Exception | None = None
        try:
            if action == "rollback":
                conn.rollback()
            else:
                conn.commit()
        except Exception as exc:
            failure = exc
            try:
                conn.rollback()
            except Exception:
                pass
        if self._pin_depth:
            self._return_pending = False
        elif self._open_cursors:
            self._return_pending = True
        else:
            self._return_to_pool(conn)
        if failure is not None and not suppress_errors:
            raise failure

    def _cursor_closed(self) -> None:
        self._open_cursors = max(0, self._open_cursors - 1)
        if self._open_cursors == 0 and self._return_pending and self._conn is not None:
            self._return_to_pool(self._conn)

    def suspend(self) -> None:
        if self._conn is None:
            return
        # Reads may have opened an implicit transaction. Finish it before a
        # model call so there is never an idle transaction while waiting.
        self._finish_transaction("commit", suppress_errors=True)

    def pin(self) -> None:
        """Keep this proxy on one physical session across commits."""
        if self._closed:
            raise RuntimeError("数据库连接已关闭")
        self._pin_depth += 1

    def unpin(self) -> None:
        self._pin_depth = max(0, self._pin_depth - 1)

    def close(self) -> None:
        if self._closed:
            return
        self._pin_depth = 0
        self.suspend()
        self._closed = True
        connections = _thread_connections()
        if self in connections:
            connections.remove(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type:
            self.rollback()
        self.close()

    def __getattr__(self, name):
        return getattr(self._acquire(), name)


class _TrackedCursor:
    """Cursor wrapper that delays returning a committed lease until cursor exit."""

    def __init__(self, connection: PooledConnection, cursor) -> None:
        self._connection = connection
        self._cursor = cursor
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._cursor.close()
        finally:
            self._connection._cursor_closed()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def get_connection() -> PooledConnection:
    _get_pool()
    return PooledConnection()


@contextmanager
def release_connections_during_model_calls():
    previous = getattr(_THREAD_STATE, "release_before_model", False)
    _THREAD_STATE.release_before_model = True
    try:
        yield
    finally:
        _THREAD_STATE.release_before_model = previous


@contextmanager
def background_database_connections():
    """Cap physical leases used by background pricing while reserving API capacity."""
    previous = getattr(_THREAD_STATE, "background_database", False)
    _THREAD_STATE.background_database = True
    try:
        yield
    finally:
        _THREAD_STATE.background_database = previous


def suspend_connections_for_model_call() -> None:
    if not _model_release_enabled():
        return
    for connection in list(_thread_connections()):
        connection.suspend()


def get_connection_pool_metrics() -> dict[str, int | float]:
    _, _, max_connections = _get_pool()
    _, background_limit = _get_background_pool_slots()
    now = monotonic()
    with _LEASE_LOCK:
        ages = [max(0.0, now - float(lease["started_at"])) for lease in _ACTIVE_LEASES.values()]
        in_use = len(_ACTIVE_LEASES)
        waiting = _POOL_WAITING
    with _BACKGROUND_POOL_LOCK:
        background_in_use = _BACKGROUND_POOL_IN_USE
        background_waiting = _BACKGROUND_POOL_WAITING
    return {
        "max": max_connections,
        "in_use": in_use,
        "available": max(0, max_connections - in_use),
        "waiting": waiting,
        "longest_lease_seconds": round(max(ages), 3) if ages else 0.0,
        "long_lease_count": sum(1 for age in ages if age >= 30.0),
        "background_limit": background_limit,
        "background_in_use": background_in_use,
        "background_waiting": background_waiting,
    }


def apply_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

import os
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock, local

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

load_dotenv()

_POOL_LOCK = Lock()
_POOL: ThreadedConnectionPool | None = None
_POOL_SLOTS: BoundedSemaphore | None = None
_POOL_MAX = 0
_THREAD_STATE = local()


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


def _thread_connections() -> list["PooledConnection"]:
    connections = getattr(_THREAD_STATE, "connections", None)
    if connections is None:
        connections = []
        _THREAD_STATE.connections = connections
    return connections


def _model_release_enabled() -> bool:
    return bool(getattr(_THREAD_STATE, "release_before_model", False))


class PooledConnection:
    """A lazy pool lease compatible with the existing psycopg2 call sites.

    ``suspend`` returns a checked-out physical connection before a long model call.
    The next cursor/commit operation checks out a fresh short-lived lease.
    """

    def __init__(self) -> None:
        self._conn = None
        self._closed = False
        _thread_connections().append(self)

    def _acquire(self):
        if self._closed:
            raise RuntimeError("数据库连接已关闭")
        if self._conn is not None:
            return self._conn
        pool, slots, _ = _get_pool()
        _, _, wait_seconds = _pool_config()
        if not slots.acquire(timeout=wait_seconds):
            raise DatabasePoolBusyError("数据库连接池繁忙，请稍后重试")
        try:
            self._conn = pool.getconn()
            return self._conn
        except Exception:
            slots.release()
            raise

    def cursor(self, *args, **kwargs):
        return self._acquire().cursor(*args, **kwargs)

    def commit(self) -> None:
        self._acquire().commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    def suspend(self) -> None:
        if self._conn is None:
            return
        conn = self._conn
        self._conn = None
        pool, slots, _ = _get_pool()
        try:
            # Reads may have opened an implicit transaction. Finish it before
            # a model call so there is never an idle transaction while waiting.
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            pool.putconn(conn)
            slots.release()

    def close(self) -> None:
        if self._closed:
            return
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


def suspend_connections_for_model_call() -> None:
    if not _model_release_enabled():
        return
    for connection in list(_thread_connections()):
        connection.suspend()


def get_connection_pool_metrics() -> dict[str, int]:
    _, _, max_connections = _get_pool()
    pool = _POOL
    used = len(getattr(pool, "_used", {})) if pool is not None else 0
    return {"max": max_connections, "in_use": used, "available": max(0, max_connections - used)}


def apply_schema(conn):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

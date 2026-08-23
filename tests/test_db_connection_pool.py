from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from time import sleep

from db import connection


class FakeCursor:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeRawConnection:
    def __init__(self):
        self.closed = False
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self, *_args, **_kwargs):
        return FakeCursor()

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class FakePool:
    def __init__(self):
        self.raw = FakeRawConnection()
        self.checkout_count = 0
        self.return_count = 0

    def getconn(self):
        self.checkout_count += 1
        return self.raw

    def putconn(self, raw, close=False):
        assert raw is self.raw
        self.return_count += 1


def pool_fixture(monkeypatch):
    pool = FakePool()
    slots = BoundedSemaphore(2)
    connection._ACTIVE_LEASES.clear()
    connection._thread_connections().clear()
    connection._BACKGROUND_POOL_SLOTS = None
    connection._BACKGROUND_POOL_LIMIT = 0
    connection._BACKGROUND_POOL_WAITING = 0
    connection._BACKGROUND_POOL_IN_USE = 0
    monkeypatch.setattr(connection, "_get_pool", lambda: (pool, slots, 2))
    monkeypatch.setattr(connection, "_pool_config", lambda: ("fake", 2, 1))
    return pool


def test_commit_returns_lease_after_open_cursor_exits(monkeypatch):
    pool = pool_fixture(monkeypatch)
    conn = connection.PooledConnection()

    with conn.cursor():
        conn.commit()
        assert pool.return_count == 0
        assert connection.get_connection_pool_metrics()["in_use"] == 1

    assert pool.return_count == 1
    assert connection.get_connection_pool_metrics()["in_use"] == 0
    conn.close()
    assert pool.return_count == 1


def test_close_and_duplicate_close_return_exactly_once(monkeypatch):
    pool = pool_fixture(monkeypatch)
    conn = connection.PooledConnection()

    with conn.cursor():
        pass
    conn.close()
    conn.close()

    assert pool.raw.commit_count == 1
    assert pool.return_count == 1
    assert connection.get_connection_pool_metrics()["available"] == 2


def test_rollback_returns_lease_and_records_no_active_lease(monkeypatch):
    pool = pool_fixture(monkeypatch)
    conn = connection.PooledConnection()

    with conn.cursor():
        conn.rollback()

    assert pool.raw.rollback_count == 1
    assert pool.return_count == 1
    assert connection.get_connection_pool_metrics()["in_use"] == 0
    conn.close()


def test_pinned_session_keeps_same_lease_across_commits(monkeypatch):
    pool = pool_fixture(monkeypatch)
    conn = connection.PooledConnection()
    conn.pin()

    with conn.cursor():
        conn.commit()
    with conn.cursor():
        conn.commit()

    assert pool.checkout_count == 1
    assert pool.return_count == 0
    conn.unpin()
    conn.close()
    assert pool.return_count == 1


def test_99_concurrent_tasks_never_use_more_than_24_leases(monkeypatch):
    class StressPool:
        def __init__(self):
            self.lock = Lock()
            self.in_use = 0
            self.peak = 0

        def getconn(self):
            with self.lock:
                self.in_use += 1
                self.peak = max(self.peak, self.in_use)
            return FakeRawConnection()

        def putconn(self, _raw, close=False):
            with self.lock:
                self.in_use -= 1

    pool = StressPool()
    slots = BoundedSemaphore(24)
    connection._ACTIVE_LEASES.clear()
    monkeypatch.setattr(connection, "_get_pool", lambda: (pool, slots, 24))
    monkeypatch.setattr(connection, "_pool_config", lambda: ("fake", 24, 2))

    def run_one(_index):
        conn = connection.PooledConnection()
        try:
            with conn.cursor():
                sleep(0.005)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=99) as executor:
        list(executor.map(run_one, range(99)))

    assert pool.peak <= 24
    assert connection.get_connection_pool_metrics()["in_use"] == 0


def test_99_background_tasks_leave_eight_pool_slots_for_api(monkeypatch):
    class StressPool:
        def __init__(self):
            self.lock = Lock()
            self.in_use = 0
            self.peak = 0

        def getconn(self):
            with self.lock:
                self.in_use += 1
                self.peak = max(self.peak, self.in_use)
            return FakeRawConnection()

        def putconn(self, _raw, close=False):
            with self.lock:
                self.in_use -= 1

    pool = StressPool()
    slots = BoundedSemaphore(24)
    connection._ACTIVE_LEASES.clear()
    connection._BACKGROUND_POOL_SLOTS = None
    connection._BACKGROUND_POOL_LIMIT = 0
    connection._BACKGROUND_POOL_WAITING = 0
    connection._BACKGROUND_POOL_IN_USE = 0
    monkeypatch.setattr(connection, "_get_pool", lambda: (pool, slots, 24))
    monkeypatch.setattr(connection, "_pool_config", lambda: ("fake", 24, 2))
    monkeypatch.setattr(connection, "_background_pool_config", lambda: 16)

    def run_one(_index):
        with connection.background_database_connections():
            conn = connection.PooledConnection()
            try:
                with conn.cursor():
                    sleep(0.01)
            finally:
                conn.close()

    with ThreadPoolExecutor(max_workers=99) as executor:
        list(executor.map(run_one, range(99)))

    metrics = connection.get_connection_pool_metrics()
    assert pool.peak <= 16
    assert metrics["background_limit"] == 16
    assert metrics["background_in_use"] == 0
    assert metrics["background_waiting"] == 0
    assert metrics["in_use"] == 0

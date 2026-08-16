from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from api import auth
from api.routers import pricing_task
from db.schema_lock import SCHEMA_ADVISORY_LOCK_ID, acquire_schema_transaction_lock


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.calls.append((sql, params))


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.rollback_count = 0

    def cursor(self):
        return self.cursor_instance

    def rollback(self) -> None:
        self.rollback_count += 1


class SchemaInitializationLockingTests(unittest.TestCase):
    def test_advisory_lock_uses_shared_transaction_key(self) -> None:
        conn = _Connection()

        acquire_schema_transaction_lock(conn)

        self.assertEqual(
            conn.cursor_instance.calls,
            [("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_ADVISORY_LOCK_ID,))],
        )

    def test_pricing_schema_runs_once_under_concurrent_requests(self) -> None:
        previous_ready = pricing_task._SCHEMA_READY
        pricing_task._SCHEMA_READY = False
        conn = _Connection()

        try:
            with (
                mock.patch.object(pricing_task, "apply_version_schema") as apply_version,
                mock.patch.object(pricing_task, "acquire_schema_transaction_lock") as acquire_lock,
                mock.patch.object(pricing_task, "_apply_schema") as apply_schema,
            ):
                apply_version.side_effect = lambda _: time.sleep(0.02)
                with ThreadPoolExecutor(max_workers=8) as executor:
                    list(executor.map(lambda _: pricing_task._ensure_schema(conn), range(16)))

                apply_version.assert_called_once_with(conn)
                acquire_lock.assert_called_once_with(conn)
                apply_schema.assert_called_once_with(conn)
                self.assertTrue(pricing_task._SCHEMA_READY)
        finally:
            pricing_task._SCHEMA_READY = previous_ready

    def test_ready_ownership_schema_does_not_acquire_ddl_lock(self) -> None:
        conn = mock.MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        with (
            mock.patch.object(auth, "_missing_ownership_objects", return_value=[]),
            mock.patch.object(auth, "acquire_schema_transaction_lock") as acquire_lock,
        ):
            auth.ensure_ownership_schema(conn)

        acquire_lock.assert_not_called()
        conn.commit.assert_called_once()

    def test_missing_ownership_schema_releases_inspection_transaction_first(self) -> None:
        conn = mock.MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        order: list[str] = []
        conn.commit.side_effect = lambda: order.append("commit")

        with (
            mock.patch.object(
                auth,
                "_missing_ownership_objects",
                side_effect=[[('pricing_tasks', False, False)], []],
            ),
            mock.patch.object(
                auth,
                "acquire_schema_transaction_lock",
                side_effect=lambda _: order.append("lock"),
            ),
        ):
            auth.ensure_ownership_schema(conn)

        self.assertEqual(order[:2], ["commit", "lock"])


if __name__ == "__main__":
    unittest.main()

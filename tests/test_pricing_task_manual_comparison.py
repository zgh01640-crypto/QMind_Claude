from __future__ import annotations

import re
import sys
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


class FakeCursor:
    def __init__(self, review_row=None, batch_run_id=None):
        self.review_row = review_row
        self.batch_run_id = batch_run_id
        self.last_sql = ""
        self.executions: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(str(sql).split())
        self.executions.append((self.last_sql, params))

    def fetchall(self):
        if "FROM manual_boq_items" in self.last_sql:
            return [(55, Decimal("10"))]
        return []

    def fetchone(self):
        if "INSERT INTO pricing_task_manual_comparison_reviews" in self.last_sql:
            return self.review_row
        if "INSERT INTO pricing_task_batch_item_runs" in self.last_sql:
            return (self.batch_run_id,)
        return None


class FakeConnection:
    def __init__(self, review_row=None, batch_run_id=None):
        self.cursor_instance = FakeCursor(review_row, batch_run_id)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class ManualComparisonReviewTests(unittest.TestCase):
    def setUp(self):
        self.matches = [
            {"dekid": 1, "dezmid": 11, "zmbh": "A-1", "zmmc": "Shared", "dw": "m", "qty_factor": 1},
            {"dekid": 2, "dezmid": 22, "zmbh": "B-2", "zmmc": "AI only", "dw": "m2", "qty_factor": 2},
        ]
        self.before_manual = [
            {"id": 101, "boq_item_id": 55, "quota_code": "A-1", "quota_name": "Shared", "quota_unit": "m", "quantity": 10.0, "qty_factor": 1.0, "quota_item_id": None, "is_formula": False},
            {"id": 102, "boq_item_id": 55, "quota_code": "C-3", "quota_name": "Manual only", "quota_unit": "m", "quantity": 10.0, "qty_factor": 1.0, "quota_item_id": None, "is_formula": False},
        ]
        self.after_manual = [
            self.before_manual[0],
            {"id": 103, "boq_item_id": 55, "quota_code": "B-2", "quota_name": "AI only", "quota_unit": "m2", "quantity": 20.0, "qty_factor": 2.0, "quota_item_id": None, "is_formula": False},
        ]
        self.context = {
            "source_type": "batch",
            "source_run_id": 900,
            "task_id": None,
            "quota_match": {"matches": self.matches},
            "manual_project_id": 77,
            "item_code": "010101",
            "boq_item_id": 88,
        }

    def review_row(self):
        before_evaluation = pricing_task._evaluate(self.matches, self.before_manual)
        after_evaluation = pricing_task._evaluate(self.matches, self.after_manual)
        return (
            1,
            "batch",
            900,
            77,
            55,
            self.before_manual,
            self.after_manual,
            before_evaluation,
            after_evaluation,
            [101],
            [{"dekid": 2, "dezmid": 22}],
            "system",
            datetime(2026, 8, 5, 12, 0, 0),
        )

    def test_new_and_legacy_batch_create_contracts_are_separate(self):
        legacy = pricing_task.PricingTaskBatchCreate(
            name="legacy",
            boq_project_id=1,
        )
        self.assertIsNone(legacy.manual_project_id)
        with self.assertRaises(ValidationError):
            pricing_task.NewPricingTaskBatchCreate(
                name="streamlined",
                boq_project_id=1,
            )
        streamlined = pricing_task.NewPricingTaskBatchCreate(
            name="streamlined",
            boq_project_id=1,
            manual_project_id=2,
        )
        self.assertEqual(streamlined.manual_project_id, 2)

    def test_evaluation_matches_duplicate_codes_one_to_one(self):
        matches = [
            {"zmbh": "INSTALL"},
            {"zmbh": "FLUSH"},
            {"zmbh": "BOTTOM"},
            {"zmbh": "OIL"},
            {"zmbh": "CLOTH"},
            {"zmbh": "RUST"},
        ]
        manual = [
            {"id": 1, "quota_code": "INSTALL"},
            {"id": 2, "quota_code": "FLUSH"},
            {"id": 3, "quota_code": "BOTTOM"},
            {"id": 4, "quota_code": "OIL"},
            {"id": 5, "quota_code": "CLOTH"},
            {"id": 6, "quota_code": "OIL"},
            {"id": 7, "quota_code": "CLOTH"},
            {"id": 8, "quota_code": "OIL"},
            {"id": 9, "quota_code": "CLOTH"},
        ]

        evaluation = pricing_task._evaluate(matches, manual)

        self.assertEqual(evaluation["manual_count"], 9)
        self.assertEqual(evaluation["ai_count"], 6)
        self.assertEqual(evaluation["hit_count"], 5)
        self.assertEqual(evaluation["missed_count"], 4)
        self.assertEqual(evaluation["extra_count"], 1)
        self.assertEqual(evaluation["hit_codes"], ["INSTALL", "FLUSH", "BOTTOM", "OIL", "CLOTH"])
        self.assertEqual(evaluation["missed_codes"], ["OIL", "CLOTH", "OIL", "CLOTH"])
        self.assertEqual(evaluation["extra_codes"], ["RUST"])
        self.assertEqual(evaluation["matched_manual_indexes"], [0, 1, 2, 3, 4])
        self.assertEqual(evaluation["missed_manual_indexes"], [5, 6, 7, 8])
        self.assertEqual(evaluation["matched_ai_indexes"], [0, 1, 2, 3, 4])
        self.assertEqual(evaluation["extra_ai_indexes"], [5])
        self.assertEqual(evaluation["matched_manual_quota_ids"], [1, 2, 3, 4, 5])
        self.assertEqual(evaluation["missed_manual_quota_ids"], [6, 7, 8, 9])

    def test_evaluation_keeps_manual_conversion_suffix_compatibility(self):
        evaluation = pricing_task._evaluate(
            [{"zmbh": "010001-32"}],
            [{"id": 1, "quota_code": "010001-32换"}],
        )

        self.assertEqual(evaluation["hit_count"], 1)
        self.assertEqual(evaluation["missed_count"], 0)
        self.assertEqual(evaluation["extra_count"], 0)

    def test_batch_item_run_insert_has_one_value_for_every_column(self):
        conn = FakeConnection(batch_run_id=71)

        run_id = pricing_task._create_or_reset_batch_item_run(
            conn,
            batch_id=4,
            boq_item={"id": 75, "project_id": 2},
            kb_version_id=5,
        )

        self.assertEqual(run_id, 71)
        insert_sql = next(
            sql
            for sql, _ in conn.cursor_instance.executions
            if "INSERT INTO pricing_task_batch_item_runs" in sql
        )
        match = re.search(
            r"pricing_task_batch_item_runs\((.*?)\) VALUES \((.*?)\) ON CONFLICT",
            insert_sql,
        )
        self.assertIsNotNone(match)
        columns = [part.strip() for part in match.group(1).split(",")]
        values = [part.strip() for part in match.group(2).split(",")]
        self.assertEqual(len(columns), 20)
        self.assertEqual(len(values), len(columns))
        self.assertTrue(conn.committed)

    def test_batch_review_updates_only_current_run_and_writes_history(self):
        conn = FakeConnection(self.review_row())
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[101],
            accepted_ai_quotas=[{"dekid": 2, "dezmid": 22}],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", side_effect=[self.before_manual, self.after_manual]):
            result = pricing_task._apply_manual_comparison_review(conn, self.context, body)

        self.assertEqual(result["evaluation"]["missed_count"], 0)
        self.assertEqual(result["evaluation"]["extra_count"], 0)
        statements = [sql for sql, _ in conn.cursor_instance.executions]
        self.assertTrue(any("UPDATE pricing_task_batch_item_runs SET evaluation" in sql for sql in statements))
        self.assertTrue(any("INSERT INTO pricing_task_manual_comparison_reviews" in sql for sql in statements))
        self.assertFalse(any("UPDATE pricing_tasks SET accuracy_report" in sql for sql in statements))

    def test_single_review_updates_only_its_task_and_run(self):
        review_row = list(self.review_row())
        review_row[1] = "single"
        review_row[2] = 901
        conn = FakeConnection(tuple(review_row))
        context = dict(self.context, source_type="single", source_run_id=901, task_id=44)
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[101],
            accepted_ai_quotas=[{"dekid": 2, "dezmid": 22}],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", side_effect=[self.before_manual, self.after_manual]):
            pricing_task._apply_manual_comparison_review(conn, context, body)

        statements = conn.cursor_instance.executions
        self.assertTrue(any("UPDATE pricing_task_runs SET evaluation" in sql for sql, _ in statements))
        task_updates = [(sql, params) for sql, params in statements if "UPDATE pricing_tasks SET accuracy_report" in sql]
        self.assertEqual(len(task_updates), 1)
        self.assertEqual(task_updates[0][1], (44,))
        self.assertNotIn("manual_project_id", task_updates[0][0])

    def test_consistent_manual_quota_cannot_be_removed(self):
        conn = FakeConnection(self.review_row())
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[102],
            accepted_ai_quotas=[],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", return_value=self.before_manual):
            with self.assertRaises(HTTPException) as raised:
                pricing_task._apply_manual_comparison_review(conn, self.context, body)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertFalse(any(sql.startswith("DELETE FROM manual_boq_quotas") for sql, _ in conn.cursor_instance.executions))

    def test_ai_quota_must_belong_to_source_run(self):
        conn = FakeConnection(self.review_row())
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[101, 102],
            accepted_ai_quotas=[{"dekid": 99, "dezmid": 999}],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", return_value=self.before_manual):
            with self.assertRaises(HTTPException) as raised:
                pricing_task._apply_manual_comparison_review(conn, self.context, body)
        self.assertEqual(raised.exception.status_code, 400)

    def test_non_positive_ai_factor_is_rejected(self):
        conn = FakeConnection(self.review_row())
        context = dict(self.context)
        context["quota_match"] = {"matches": [dict(self.matches[1], qty_factor=0)]}
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[101, 102],
            accepted_ai_quotas=[{"dekid": 2, "dezmid": 22}],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", return_value=self.before_manual):
            with self.assertRaises(HTTPException) as raised:
                pricing_task._apply_manual_comparison_review(conn, context, body)
        self.assertEqual(raised.exception.status_code, 400)

    def test_final_quota_set_cannot_be_empty(self):
        conn = FakeConnection(self.review_row())
        context = dict(self.context)
        context["quota_match"] = {"matches": []}
        body = pricing_task.ManualComparisonUpdateRequest(
            retained_manual_quota_ids=[],
            accepted_ai_quotas=[],
        )
        with mock.patch.object(pricing_task, "_manual_quotas", return_value=self.before_manual):
            with self.assertRaises(HTTPException) as raised:
                pricing_task._apply_manual_comparison_review(conn, context, body)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertFalse(any(sql.startswith("DELETE FROM manual_boq_quotas") for sql, _ in conn.cursor_instance.executions))

    def test_endpoint_rolls_back_when_review_fails(self):
        from db import connection as db_connection

        conn = FakeConnection()
        with (
            mock.patch.object(db_connection, "get_connection", return_value=conn),
            mock.patch.object(pricing_task, "_ensure_schema"),
            mock.patch.object(pricing_task, "_load_manual_comparison_context", return_value=self.context),
            mock.patch.object(pricing_task, "_apply_manual_comparison_review", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                pricing_task._update_manual_comparison(
                    "batch",
                    900,
                    pricing_task.ManualComparisonUpdateRequest(retained_manual_quota_ids=[101]),
                )
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()

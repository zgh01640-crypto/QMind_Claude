from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


class CandidateCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(str(sql).split())
        self.params = params

    def fetchall(self):
        return self.rows


class CandidateConnection:
    def __init__(self, rows):
        self.cursor_instance = CandidateCursor(rows)

    def cursor(self):
        return self.cursor_instance


class SpecialCandidateTests(unittest.TestCase):
    def test_combines_sources_and_preserves_typical_group_metadata(self):
        conn = CandidateConnection(
            [
                (
                    11852, 1020206, "深圳市安装工程消耗量标准(2025)",
                    "031103-336", "环氧煤沥青防腐漆", "10m2", "", "防腐工程",
                    ["TQDK_TQDZY", "TQDK_TQDZY_SPECIAL"], [33], ["沥青涂料加强级防腐层"],
                ),
            ]
        )

        result = pricing_task.exec_fetch_quota_candidates(conn, "031001006006", 7, [1020206])

        self.assertEqual(result["base_code"], "031001006")
        self.assertEqual(result["total"], 1)
        self.assertEqual(
            result["candidates"][0]["source_tables"],
            ["TQDK_TQDZY", "TQDK_TQDZY_SPECIAL"],
        )
        self.assertEqual(result["candidates"][0]["typical_group_ids"], [33])
        self.assertEqual(result["candidates"][0]["typical_group_names"], ["沥青涂料加强级防腐层"])
        self.assertIn("tqdk_tqdzy_special", conn.cursor_instance.sql.lower())
        self.assertIn("group by dekid, dezmid", conn.cursor_instance.sql.lower())
        self.assertNotIn(" limit ", conn.cursor_instance.sql.lower())
        self.assertEqual(conn.cursor_instance.params[-1], [1020206])

    def test_special_rows_without_quota_keys_are_filtered_by_query(self):
        conn = CandidateConnection([])

        result = pricing_task.exec_fetch_quota_candidates(conn, "031001006006", 7)

        self.assertEqual(result["candidates"], [])
        self.assertIn("cand.dekid is not null", conn.cursor_instance.sql.lower())
        self.assertIn("cand.dezmid is not null", conn.cursor_instance.sql.lower())


if __name__ == "__main__":
    unittest.main()

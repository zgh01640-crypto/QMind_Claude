from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


class FeatureDefaultCursor:
    def __init__(self, schema_rows):
        self.schema_rows = schema_rows
        self.last_sql = ""
        self.executions: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(str(sql).split())
        self.executions.append((self.last_sql, params))

    def fetchone(self):
        if "SELECT EXISTS" in self.last_sql:
            return (True,)
        return None

    def fetchall(self):
        if "JOIN tqdk_tqdxmtz" in self.last_sql:
            return self.schema_rows
        return []


class FeatureDefaultConnection:
    def __init__(self, schema_rows):
        self.cursor_instance = FeatureDefaultCursor(schema_rows)

    def cursor(self):
        return self.cursor_instance


class FeatureDefaultTests(unittest.TestCase):
    def test_only_native_tqdxmtz_defaults_become_candidates(self):
        conn = FeatureDefaultConnection(
            [
                ("模板材质", "木模板", 11),
                ("支模高度", "", 12),
            ]
        )

        context = pricing_task._load_feature_default_context(conn, "010505004", 7)

        self.assertEqual(len(context["feature_schema"]), 2)
        self.assertEqual(
            context["default_candidates"],
            [
                {
                    "candidate_id": "tqdxmtz:11",
                    "source": "TQDK_TQDXMTZ",
                    "priority": 1,
                    "source_code": "010505004",
                    "feature_name": "模板材质",
                    "target_feature_name": "模板材质",
                    "feature_value": "综合考虑",
                    "default_value": "木模板",
                    "source_rowid": 11,
                }
            ],
        )
        sql_text = " ".join(sql for sql, _ in conn.cursor_instance.executions).lower()
        self.assertNotIn("tqdk_tzhkl", sql_text)

    def test_missing_native_default_does_not_create_fallback_candidate(self):
        conn = FeatureDefaultConnection([("模板材质", None, 21)])

        context = pricing_task._load_feature_default_context(conn, "010505004", 7)

        self.assertEqual(context["default_candidates"], [])
        self.assertEqual(context["feature_schema"][0]["native_default_value"], "")

    def test_native_candidate_replaces_only_comprehensive_value(self):
        context = {
            "feature_schema": [
                {
                    "feature_name": "模板材质",
                    "native_default_value": "木模板",
                    "source": "TQDK_TQDXMTZ",
                    "source_rowid": 11,
                }
            ],
            "default_candidates": [
                {
                    "candidate_id": "tqdxmtz:11",
                    "source": "TQDK_TQDXMTZ",
                    "source_code": "010505004",
                    "feature_name": "模板材质",
                    "target_feature_name": "模板材质",
                    "default_value": "木模板",
                    "source_rowid": 11,
                }
            ],
            "schema_kb_version_id": 7,
        }
        raw = {
            "is_complete": True,
            "missing_features": [],
            "analysis": "使用原生默认值补全。",
            "default_fills": [
                {
                    "candidate_id": "tqdxmtz:11",
                    "target_feature_name": "模板材质",
                    "confidence": "high",
                    "reason": "特征名一致",
                }
            ],
        }

        result = pricing_task._normalize_feature_analysis_result(
            raw,
            "模板材质：综合考虑；支模高度：3.6m",
            "010505004",
            context,
        )

        self.assertEqual(result["effective_description"], "模板材质：木模板；支模高度：3.6m")
        self.assertEqual(result["default_fills"][0]["source"], "TQDK_TQDXMTZ")
        self.assertFalse(result["description_updated"])

    def test_explicit_original_value_is_not_filled(self):
        context = {
            "feature_schema": [],
            "default_candidates": [
                {
                    "candidate_id": "tqdxmtz:11",
                    "source": "TQDK_TQDXMTZ",
                    "source_code": "010505004",
                    "feature_name": "模板材质",
                    "target_feature_name": "模板材质",
                    "default_value": "木模板",
                    "source_rowid": 11,
                }
            ],
            "schema_kb_version_id": 7,
        }

        result = pricing_task._normalize_feature_analysis_result(
            {"default_fills": [{"candidate_id": "tqdxmtz:11"}]},
            "模板材质：铝模板",
            "010505004",
            context,
        )

        self.assertEqual(result["default_fills"], [])
        self.assertEqual(result["effective_description"], "模板材质：铝模板")


if __name__ == "__main__":
    unittest.main()

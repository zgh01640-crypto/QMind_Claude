from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402
from db.migrations import MIGRATIONS  # noqa: E402


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
    def test_pump_weight_default_correction_is_registered(self):
        migrations = dict(MIGRATIONS)
        correction = migrations["20260901_correct_pump_weight_default"]

        self.assertTrue(correction.exists())
        sql = correction.read_text(encoding="utf-8")
        self.assertIn("qdkid = 1020025", sql)
        self.assertIn("qdzmid = 4067", sql)
        self.assertIn("设备重量W(t) 1＜W≤1.2", sql)
        self.assertIn("设备重量W(t) 0.4＜W≤0.6", sql)

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
                    "feature_value": "",
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
                    "match_state": "comprehensive",
                    "original_feature_text": "模板材质：综合考虑",
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

    def _native_context(self, feature_name="防腐：喷（刷）沥青或防腐漆", default_value="沥青漆二道"):
        return {
            "feature_schema": [
                {
                    "feature_name": feature_name,
                    "native_default_value": default_value,
                    "source": "TQDK_TQDXMTZ",
                    "source_rowid": 15932,
                }
            ],
            "default_candidates": [
                {
                    "candidate_id": "tqdxmtz:15932",
                    "source": "TQDK_TQDXMTZ",
                    "source_code": "031001001",
                    "feature_name": feature_name,
                    "target_feature_name": feature_name,
                    "default_value": default_value,
                    "source_rowid": 15932,
                }
            ],
            "schema_kb_version_id": 7,
        }

    def test_vague_native_feature_is_appended_without_rewriting_original(self):
        context = self._native_context()
        original = "防腐：管道及管件内外均应喷（刷）沥青或防腐漆，具体详见设计说明"
        raw = {
            "default_fills": [
                {
                    "candidate_id": "tqdxmtz:15932",
                    "target_feature_name": "防腐：喷（刷）沥青或防腐漆",
                    "match_state": "vague",
                    "original_feature_text": original,
                    "reason": "已说明防腐类别，但未给出涂刷遍数。",
                    "confidence": "high",
                }
            ]
        }

        result = pricing_task._normalize_feature_analysis_result(raw, original, "031001001", context)

        self.assertTrue(result["effective_description"].startswith(original))
        self.assertIn("【智能补全项目特征】", result["effective_description"])
        self.assertIn("沥青漆二道", result["effective_description"])
        self.assertEqual(result["default_fills"][0]["match_state"], "vague")

    def test_missing_native_feature_is_appended(self):
        context = self._native_context()
        raw = {
            "default_fills": [
                {
                    "candidate_id": "tqdxmtz:15932",
                    "target_feature_name": "防腐：喷（刷）沥青或防腐漆",
                    "match_state": "missing",
                    "original_feature_text": "",
                    "reason": "原项目特征没有防腐做法。",
                    "confidence": "medium",
                }
            ]
        }

        result = pricing_task._normalize_feature_analysis_result(raw, "材质：铸铁管", "031001001", context)

        self.assertIn("沥青漆二道", result["effective_description"])
        self.assertEqual(result["default_fills"][0]["match_state"], "missing")

    def test_explicit_original_value_is_not_filled_when_model_returns_no_candidate(self):
        context = self._native_context()

        result = pricing_task._normalize_feature_analysis_result(
            {"default_fills": []},
            "防腐：四油三布石油沥青涂料外防腐层",
            "031001001",
            context,
        )

        self.assertEqual(result["default_fills"], [])
        self.assertEqual(result["effective_description"], "防腐：四油三布石油沥青涂料外防腐层")

    def test_low_confidence_fill_requires_review_and_is_not_applied(self):
        context = self._native_context()
        original = "防腐做法满足设计要求"
        raw = {
            "default_fills": [
                {
                    "candidate_id": "tqdxmtz:15932",
                    "target_feature_name": "防腐：喷（刷）沥青或防腐漆",
                    "match_state": "vague",
                    "original_feature_text": original,
                    "reason": "无法确认防腐类别。",
                    "confidence": "low",
                }
            ]
        }

        result = pricing_task._normalize_feature_analysis_result(raw, original, "031001001", context)

        self.assertEqual(result["default_fills"], [])
        self.assertEqual(result["effective_description"], original)
        self.assertEqual(result["default_review_items"][0]["confidence"], "low")

    def test_conditional_default_is_appended_verbatim(self):
        default_rule = "DN≤32 螺纹连接；32＜DN 法兰连接；"
        context = self._native_context("连接形式", default_rule)
        raw = {
            "default_fills": [
                {
                    "candidate_id": "tqdxmtz:15932",
                    "target_feature_name": "连接形式",
                    "match_state": "missing",
                    "original_feature_text": "",
                    "reason": "缺少连接形式。",
                    "confidence": "high",
                }
            ]
        }

        result = pricing_task._normalize_feature_analysis_result(raw, "规格：DN25", "031002011", context)

        self.assertIn(default_rule, result["effective_description"])
        self.assertNotIn("连接形式：螺纹连接\n", result["effective_description"])


if __name__ == "__main__":
    unittest.main()

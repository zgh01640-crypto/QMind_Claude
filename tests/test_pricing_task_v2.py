from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.routers import pricing_task, pricing_task_v2  # noqa: E402


def _stream(arguments: str):
    function = SimpleNamespace(arguments=arguments)
    tool_call = SimpleNamespace(function=function)
    delta = SimpleNamespace(reasoning_content="分析候选", content=None, tool_calls=[tool_call])
    return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])


class PricingTaskV2Tests(unittest.TestCase):
    def setUp(self):
        self.candidates = [{
            "dekid": 12, "dezmid": 34, "zmbh": "A-1", "zmmc": "测试定额", "dw": "10m3",
            "library_name": "测试库", "chapter_name": "测试章",
        }]

    def test_normalize_rejects_outside_and_invalid_ids_without_aborting(self):
        result = pricing_task_v2._normalize_matches_v2({"matches": [
            {"dekid": "bad", "dezmid": 34},
            {"dekid": 99, "dezmid": 99, "qty_factor": 1},
            {"dekid": 12, "dezmid": 34, "qty_factor": 0, "confidence": "unknown"},
            {"dekid": 12, "dezmid": 34, "qty_factor": 2},
        ], "issues": ["原始问题", ""]}, self.candidates)

        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["qty_factor"], 1.0)
        self.assertEqual(result["matches"][0]["confidence"], "low")
        self.assertTrue(any("候选外定额" in issue for issue in result["issues"]))
        self.assertTrue(any("人工复核" in issue for issue in result["issues"]))

    def test_combined_match_forces_single_tool_call(self):
        captured = []

        class Completions:
            def create(self, **kwargs):
                captured.append(kwargs)
                return _stream('{"matches":[],"issues":[]}')

        client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        with (
            patch.object(pricing_task, "_client", return_value=client),
            patch.object(pricing_task, "_model", return_value="test-model"),
        ):
            events = list(pricing_task_v2._stream_combined_match([{"role": "user", "content": "匹配"}]))

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["tool_choice"]["function"]["name"], "submit_quota_match")
        self.assertTrue(captured[0]["stream"])
        self.assertEqual(events[-1], ("tool_result", {"matches": [], "issues": []}))
        properties = captured[0]["tools"][0]["function"]["parameters"]["properties"]
        self.assertIn("analysis_summary", properties)
        self.assertIn("candidate_decisions", properties)
        self.assertIn("combination_reason", properties)
        self.assertIn("unit_factor_analysis", properties)
        self.assertIn("rule_compliance", properties)

    def test_normalize_preserves_explanation_and_filters_candidate_decisions(self):
        result = pricing_task_v2._normalize_matches_v2({
            "analysis_summary": "  整体判断  ",
            "candidate_decisions": [
                {"dekid": 12, "dezmid": 34, "decision": "accepted", "reason": "匹配工作内容"},
                {"dekid": 99, "dezmid": 88, "decision": "accepted", "reason": "候选外"},
            ],
            "combination_reason": "无需组合",
            "unit_factor_analysis": "单位一致，系数1",
            "rule_compliance": "符合章节规则",
            "matches": [],
            "issues": [],
        }, self.candidates)

        self.assertEqual(result["analysis_summary"], "整体判断")
        self.assertEqual(len(result["candidate_decisions"]), 1)
        self.assertEqual(result["candidate_decisions"][0]["zmbh"], "A-1")
        self.assertTrue(any("候选决策包含候选外定额" in issue for issue in result["issues"]))

    def test_v2_schema_uses_only_v2_management_tables(self):
        source = Path(pricing_task_v2.__file__).read_text(encoding="utf-8")
        self.assertNotIn("INSERT INTO pricing_tasks", source)
        self.assertNotIn("UPDATE pricing_task_runs", source)
        self.assertNotIn("INSERT INTO pricing_task_results", source)


if __name__ == "__main__":
    unittest.main()

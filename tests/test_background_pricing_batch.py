from api.routers import pricing_task


def test_background_pipeline_uses_complete_single_item_tool_sequence():
    assert pricing_task._BACKGROUND_TOOL_NEXT == {
        "code_check": "feature_check",
        "feature_check": "chapter_rule_check",
        "chapter_rule_check": "quota_candidates",
        "quota_candidates": "quota_match",
        "quota_match": "evaluation",
    }


def test_background_tool_output_contains_only_result_summary():
    assert pricing_task._background_tool_output(
        "quota_candidates", {"total": 26, "candidates": []}
    ) == "检索到 26 条候选定额"
    assert pricing_task._background_tool_output(
        "evaluation", {"hit_count": 2, "missed_count": 1, "extra_count": 3}
    ) == "命中 2，遗漏 1，额外 3"


def test_shared_batch_conversion_and_coefficient_services_handle_empty_results():
    conversion_events = list(pricing_task._batch_conversion_business_events([], {}))
    coefficient_events = list(pricing_task._batch_coefficient_business_events([], {}))

    assert conversion_events[-1][0] == "conversion_check"
    assert conversion_events[-1][1]["conversion_check"]["items"] == []
    assert coefficient_events[-1][0] == "coefficient_check"
    assert coefficient_events[-1][1]["coefficient_check"]["items"] == []

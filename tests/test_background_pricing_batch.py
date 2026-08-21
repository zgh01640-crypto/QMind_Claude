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


def test_background_workspace_separates_execution_and_consistency_statuses():
    assert pricing_task._background_execution_status(None) == "waiting"
    assert pricing_task._background_execution_status("queued") == "waiting"
    assert pricing_task._background_execution_status("running") == "processing"
    assert pricing_task._background_execution_status("retrying") == "retrying"
    assert pricing_task._background_execution_status("confirmed") == "completed"
    assert pricing_task._background_execution_status("failed") == "failed"

    assert pricing_task._background_consistency_status(
        {"hit_count": 0, "missed_count": 0, "extra_count": 0, "manual_count": 0, "ai_count": 0}
    ) == "no_comparable"
    assert pricing_task._background_consistency_status(
        {"hit_count": 2, "missed_count": 0, "extra_count": 0, "manual_count": 2, "ai_count": 2}
    ) == "exact"
    assert pricing_task._background_consistency_status(
        {"hit_count": 1, "missed_count": 1, "extra_count": 1, "manual_count": 2, "ai_count": 2}
    ) == "partial"
    assert pricing_task._background_consistency_status(
        {"hit_count": 0, "missed_count": 1, "extra_count": 1, "manual_count": 1, "ai_count": 1}
    ) == "inconsistent"


def test_background_workspace_summary_counts_results_and_estimates_eta():
    items = [
        {"execution_status": "completed", "consistency_status": "exact", "hit_count": 2,
         "missed_count": 0, "extra_count": 0, "manual_count": 2, "ai_count": 2},
        {"execution_status": "processing", "consistency_status": "partial", "hit_count": 1,
         "missed_count": 1, "extra_count": 0, "manual_count": 2, "ai_count": 1},
        {"execution_status": "waiting", "consistency_status": "unassessed", "hit_count": 0,
         "missed_count": 0, "extra_count": 0, "manual_count": 0, "ai_count": 0},
    ]
    summary = pricing_task._background_workspace_summary(items, None)
    assert summary["total_count"] == 3
    assert summary["completed_count"] == 1
    assert summary["running_count"] == 1
    assert summary["waiting_count"] == 1
    assert summary["evaluated_count"] == 2
    assert summary["exact_count"] == 1
    assert summary["partial_count"] == 1
    assert summary["hit_count"] == 3
    assert summary["hit_rate"] == 0.75


def test_background_worker_and_model_gates_never_expand_beyond_99(monkeypatch):
    monkeypatch.setenv("PRICING_BACKGROUND_BATCH_CONCURRENCY", "999")
    monkeypatch.setenv("PRICING_MODEL_CONCURRENCY", "999")

    assert pricing_task._background_worker_limit() == 99
    assert pricing_task._model_gate_limit() == 99


def test_model_rate_limit_is_recognized_without_entering_retry_policy():
    assert pricing_task._is_model_rate_limited(RuntimeError("HTTP 429 too many requests"))
    assert pricing_task._is_model_rate_limited(RuntimeError("当前账号余额不足"))
    assert not pricing_task._is_model_rate_limited(TimeoutError("connection timed out"))

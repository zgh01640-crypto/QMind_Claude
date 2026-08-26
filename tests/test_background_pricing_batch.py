import inspect

from api.routers import pricing_task
from db import connection as db_connection


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


def test_background_match_pipeline_defaults_to_legacy_and_rejects_invalid_values(monkeypatch):
    monkeypatch.delenv("PRICING_BACKGROUND_MATCH_PIPELINE", raising=False)
    assert pricing_task._background_match_pipeline() == "legacy"

    monkeypatch.setenv("PRICING_BACKGROUND_MATCH_PIPELINE", "combined_v2")
    assert pricing_task._background_match_pipeline() == "combined_v2"

    monkeypatch.setenv("PRICING_BACKGROUND_MATCH_PIPELINE", "unknown")
    assert pricing_task._background_match_pipeline() == "legacy"


def test_shared_pricing_pipeline_keeps_legacy_default_for_existing_callers():
    signature = inspect.signature(pricing_task._stream_pricing_item)
    assert signature.parameters["match_pipeline"].default == "legacy"


def test_background_execution_pins_pipeline_and_runner_uses_pinned_value():
    source = inspect.getsource(pricing_task)
    assert "pipeline_version VARCHAR(20) NOT NULL DEFAULT 'legacy'" in source
    assert "e.pipeline_version" in source
    assert "match_pipeline=pipeline_version" in source
    assert '"pipeline_selected"' in source


def test_model_rate_limit_is_recognized_without_entering_retry_policy():
    assert pricing_task._is_model_rate_limited(RuntimeError("HTTP 429 too many requests"))
    assert pricing_task._is_model_rate_limited(RuntimeError("当前账号余额不足"))
    assert not pricing_task._is_model_rate_limited(TimeoutError("connection timed out"))


def test_sse_event_chunk_closes_connection_before_events_are_returned(monkeypatch):
    rows = [
        (index, 1, index, index, "tool_completed", {"index": index}, None)
        for index in range(1, 201)
    ]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            return None

        def fetchall(self):
            return rows

    class Conn:
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    conn = Conn()
    monkeypatch.setattr(db_connection, "get_connection", lambda: conn)

    events = pricing_task._read_background_event_chunk(42, 0)

    assert len(events) == 200
    assert conn.closed is True
    assert events[-1]["id"] == 200


def test_pool_busy_background_item_is_deferred_without_business_retry(monkeypatch):
    class BusyConn:
        rolled_back = False
        closed = False

        def cursor(self):
            raise db_connection.DatabasePoolBusyError("数据库连接池繁忙，请稍后重试")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    conn = BusyConn()
    deferred = []
    monkeypatch.setattr(db_connection, "get_connection", lambda: conn)
    monkeypatch.setattr(pricing_task, "_ensure_schema", lambda _conn: None)
    monkeypatch.setattr(
        pricing_task,
        "_defer_background_item_after_pool_busy",
        lambda item_run_id, message: deferred.append((item_run_id, message)) or True,
    )

    pricing_task._run_background_item(123, "worker:test")

    assert deferred == [(123, "数据库连接池繁忙，请稍后重试")]
    assert conn.rolled_back is True
    assert conn.closed is True


def test_background_item_releases_context_lease_before_loading_model_profile(monkeypatch):
    row = (42, 13, 99, [], None, 8, "031001001", "测试清单", "", "项", 1, 7, 1, 5)

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            return None

        def fetchone(self):
            return row

    class Conn:
        committed = False
        closed = False

        def cursor(self):
            return Cursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            return None

        def close(self):
            self.closed = True

    class ProfileContext:
        def __enter__(self):
            assert conn.committed is True
            raise db_connection.DatabasePoolBusyError("stop after ordering assertion")

        def __exit__(self, *_args):
            return None

    conn = Conn()
    deferred = []
    monkeypatch.setattr(db_connection, "get_connection", lambda: conn)
    monkeypatch.setattr(pricing_task, "_ensure_schema", lambda _conn: None)
    monkeypatch.setattr(pricing_task, "use_default_profile", lambda _user_id: ProfileContext())
    monkeypatch.setattr(
        pricing_task,
        "_defer_background_item_after_pool_busy",
        lambda item_run_id, message: deferred.append((item_run_id, message)) or True,
    )

    pricing_task._run_background_item(123, "worker:test")

    assert deferred == [(123, "stop after ordering assertion")]
    assert conn.closed is True

"""Provider-agnostic AI token and cost metering."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from time import perf_counter
from typing import Any, Iterator

from psycopg2.extras import Json

from db.connection import get_connection

logger = logging.getLogger(__name__)
MILLION = Decimal("1000000")


@dataclass(frozen=True)
class UsageContext:
    business_type: str = "online_ai"
    operation: str = "chat_completion"
    task_id: int | None = None
    batch_id: int | None = None
    run_id: int | None = None
    item_run_id: int | None = None
    execution_id: int | None = None


_active_usage_context: ContextVar[UsageContext] = ContextVar(
    "active_ai_usage_context", default=UsageContext()
)


@contextmanager
def use_usage_context(**values: Any):
    current = _active_usage_context.get()
    data = {name: getattr(current, name) for name in UsageContext.__dataclass_fields__}
    data.update({key: value for key, value in values.items() if value is not None})
    token = _active_usage_context.set(UsageContext(**data))
    try:
        yield
    finally:
        _active_usage_context.reset(token)


def apply_usage_schema() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE user_model_profiles ADD COLUMN IF NOT EXISTS input_price_per_million NUMERIC(20,8) NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE user_model_profiles ADD COLUMN IF NOT EXISTS cached_input_price_per_million NUMERIC(20,8)")
            cur.execute("ALTER TABLE user_model_profiles ADD COLUMN IF NOT EXISTS output_price_per_million NUMERIC(20,8) NOT NULL DEFAULT 0")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage_records (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INT NOT NULL REFERENCES users(id),
                    model_profile_id BIGINT REFERENCES user_model_profiles(id) ON DELETE SET NULL,
                    provider VARCHAR(32) NOT NULL,
                    model VARCHAR(160) NOT NULL,
                    business_type VARCHAR(64) NOT NULL,
                    operation VARCHAR(96) NOT NULL,
                    task_id INT,
                    batch_id INT,
                    run_id BIGINT,
                    item_run_id BIGINT,
                    execution_id BIGINT,
                    status VARCHAR(16) NOT NULL,
                    usage_status VARCHAR(16) NOT NULL,
                    input_tokens BIGINT,
                    cached_input_tokens BIGINT,
                    output_tokens BIGINT,
                    reasoning_tokens BIGINT,
                    total_tokens BIGINT,
                    input_price_snapshot NUMERIC(20,8) NOT NULL,
                    cached_input_price_snapshot NUMERIC(20,8) NOT NULL,
                    output_price_snapshot NUMERIC(20,8) NOT NULL,
                    cost_yuan NUMERIC(24,10),
                    duration_ms INT NOT NULL,
                    error_type VARCHAR(160),
                    provider_usage JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_user_time ON ai_usage_records(user_id, created_at DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_task ON ai_usage_records(task_id) WHERE task_id IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_batch ON ai_usage_records(batch_id) WHERE batch_id IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_run ON ai_usage_records(run_id) WHERE run_id IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_profile ON ai_usage_records(model_profile_id, created_at DESC)")
        conn.commit()
    finally:
        conn.close()


def _value(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def normalize_usage(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    total_input = _value(usage, "prompt_tokens", "input_tokens")
    output = _value(usage, "completion_tokens", "output_tokens")
    total = _value(usage, "total_tokens")
    prompt_details = _value(usage, "prompt_tokens_details", "input_tokens_details")
    output_details = _value(usage, "completion_tokens_details", "output_tokens_details")
    cached = _value(usage, "prompt_cache_hit_tokens", "cached_input_tokens")
    if cached is None:
        cached = _value(prompt_details, "cached_tokens")
    reasoning = _value(output_details, "reasoning_tokens")
    if total_input is None and output is None and total is None:
        return None
    total_input = int(total_input or 0)
    cached = min(total_input, max(0, int(cached or 0)))
    output = int(output or 0)
    raw = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage if isinstance(usage, dict) else None
    return {
        "input_tokens": max(0, total_input - cached),
        "cached_input_tokens": cached,
        "output_tokens": max(0, output),
        "reasoning_tokens": max(0, int(reasoning or 0)),
        "total_tokens": int(total if total is not None else total_input + output),
        "raw": raw,
    }


def calculate_cost(usage: dict[str, Any], profile: Any) -> Decimal:
    input_price = Decimal(str(profile.input_price_per_million))
    cached_price = Decimal(str(profile.cached_input_price_per_million if profile.cached_input_price_per_million is not None else profile.input_price_per_million))
    output_price = Decimal(str(profile.output_price_per_million))
    return (
        Decimal(usage["input_tokens"]) * input_price
        + Decimal(usage["cached_input_tokens"]) * cached_price
        + Decimal(usage["output_tokens"]) * output_price
    ) / MILLION


def record_usage(profile: Any, started: float, status: str, usage_obj: Any = None, error: Exception | None = None) -> None:
    usage = normalize_usage(usage_obj)
    context = _active_usage_context.get()
    cached_price = profile.cached_input_price_per_million if profile.cached_input_price_per_million is not None else profile.input_price_per_million
    cost = calculate_cost(usage, profile) if usage else None
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ai_usage_records(
                        user_id,model_profile_id,provider,model,business_type,operation,
                        task_id,batch_id,run_id,item_run_id,execution_id,status,usage_status,
                        input_tokens,cached_input_tokens,output_tokens,reasoning_tokens,total_tokens,
                        input_price_snapshot,cached_input_price_snapshot,output_price_snapshot,cost_yuan,
                        duration_ms,error_type,provider_usage,finished_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (profile.user_id, profile.id, profile.provider, profile.model, context.business_type,
                     context.operation, context.task_id, context.batch_id, context.run_id,
                     context.item_run_id, context.execution_id, status, "reported" if usage else "unknown",
                     usage and usage["input_tokens"], usage and usage["cached_input_tokens"],
                     usage and usage["output_tokens"], usage and usage["reasoning_tokens"],
                     usage and usage["total_tokens"], profile.input_price_per_million, cached_price,
                     profile.output_price_per_million, cost, duration_ms,
                     type(error).__name__[:160] if error else None, Json(usage["raw"]) if usage and usage["raw"] is not None else None),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("failed to persist AI usage; business request continues")


class MeteredStream:
    def __init__(self, stream: Any, profile: Any, started: float):
        self._stream, self._profile, self._started = stream, profile, started
        self._usage = None
        self._finished = False

    def __iter__(self) -> Iterator[Any]:
        try:
            for chunk in self._stream:
                if getattr(chunk, "usage", None) is not None:
                    self._usage = chunk.usage
                yield chunk
        except Exception as exc:
            self._finish("failed", exc)
            raise
        else:
            self._finish("completed")

    def _finish(self, status: str, error: Exception | None = None) -> None:
        if not self._finished:
            self._finished = True
            record_usage(self._profile, self._started, status, self._usage, error)

    def close(self) -> None:
        try:
            close = getattr(self._stream, "close", None)
            if close:
                close()
        finally:
            self._finish("cancelled")


class MeteredCompletions:
    def __init__(self, completions: Any, profile: Any):
        self._completions, self._profile = completions, profile

    def create(self, *args: Any, **kwargs: Any):
        started = perf_counter()
        if kwargs.get("stream"):
            kwargs.setdefault("stream_options", {"include_usage": True})
        try:
            response = self._completions.create(*args, **kwargs)
        except Exception as exc:
            record_usage(self._profile, started, "failed", error=exc)
            message = str(exc).lower()
            if kwargs.get("stream") and "stream_options" in kwargs and any(token in message for token in ("stream_options", "unknown parameter", "unsupported parameter")):
                fallback = dict(kwargs)
                fallback.pop("stream_options", None)
                fallback_started = perf_counter()
                try:
                    response = self._completions.create(*args, **fallback)
                except Exception as fallback_exc:
                    record_usage(self._profile, fallback_started, "failed", error=fallback_exc)
                    raise
                return MeteredStream(response, self._profile, fallback_started)
            raise
        if kwargs.get("stream"):
            return MeteredStream(response, self._profile, started)
        record_usage(self._profile, started, "completed", getattr(response, "usage", None))
        return response


class MeteredClient:
    def __init__(self, client: Any, profile: Any):
        self._client = client
        self.chat = type("MeteredChat", (), {})()
        self.chat.completions = MeteredCompletions(client.chat.completions, profile)

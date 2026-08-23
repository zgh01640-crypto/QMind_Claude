from decimal import Decimal
from types import SimpleNamespace

from api.services.ai_usage import MeteredCompletions, calculate_cost, normalize_usage


def _profile():
    return SimpleNamespace(
        id=1, user_id=2, provider="test", model="m",
        input_price_per_million=Decimal("2"),
        cached_input_price_per_million=Decimal("0.5"),
        output_price_per_million=Decimal("8"),
    )


def test_normalize_openai_usage_with_cached_and_reasoning_tokens():
    usage = SimpleNamespace(
        prompt_tokens=1000, completion_tokens=250, total_tokens=1250,
        prompt_tokens_details=SimpleNamespace(cached_tokens=400),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=100),
    )
    result = normalize_usage(usage)
    assert result == {
        "input_tokens": 600, "cached_input_tokens": 400, "output_tokens": 250,
        "reasoning_tokens": 100, "total_tokens": 1250, "raw": None,
    }
    assert calculate_cost(result, _profile()) == Decimal("0.0034")


def test_normalize_responses_style_usage_and_cached_price_fallback():
    usage = {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 25}}
    result = normalize_usage(usage)
    profile = _profile()
    profile.cached_input_price_per_million = None
    assert result["input_tokens"] == 75
    assert result["cached_input_tokens"] == 25
    assert calculate_cost(result, profile) == Decimal("0.00036")


def test_stream_requests_terminal_usage(monkeypatch):
    calls = []
    recorded = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(usage=None), SimpleNamespace(usage={"prompt_tokens": 3, "completion_tokens": 2})])

    monkeypatch.setattr("api.services.ai_usage.record_usage", lambda profile, started, status, usage_obj=None, error=None: recorded.append((status, usage_obj)))
    stream = MeteredCompletions(Completions(), _profile()).create(stream=True, model="m")
    assert len(list(stream)) == 2
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert recorded == [("completed", {"prompt_tokens": 3, "completion_tokens": 2})]


def test_unknown_stream_options_falls_back_without_breaking_business(monkeypatch):
    calls = []
    recorded = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if "stream_options" in kwargs:
                raise ValueError("unknown parameter stream_options")
            return iter([SimpleNamespace(usage=None)])

    monkeypatch.setattr("api.services.ai_usage.record_usage", lambda profile, started, status, usage_obj=None, error=None: recorded.append((status, usage_obj)))
    stream = MeteredCompletions(Completions(), _profile()).create(stream=True, model="m")
    list(stream)
    assert len(calls) == 2
    assert "stream_options" not in calls[1]
    assert [item[0] for item in recorded] == ["failed", "completed"]

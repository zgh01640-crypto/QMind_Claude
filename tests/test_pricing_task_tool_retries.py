from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from routers import pricing_task  # noqa: E402


def _response(arguments: str):
    function = SimpleNamespace(arguments=arguments)
    tool_call = SimpleNamespace(function=function)
    message = SimpleNamespace(tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _stream(arguments: str):
    function = SimpleNamespace(arguments=arguments)
    tool_call = SimpleNamespace(function=function)
    delta = SimpleNamespace(reasoning_content=None, content=None, tool_calls=[tool_call])
    return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])


class _Completions:
    def __init__(self, results):
        self.results = iter(results)
        self.call_count = 0

    def create(self, **_kwargs):
        self.call_count += 1
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def _client(completions: _Completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class PricingTaskToolRetryTests(unittest.TestCase):
    def test_non_stream_fallback_retries_invalid_json(self):
        completions = _Completions(
            [
                _response('{"rules":[{"action":"缺少右引号}]'),
                _response('{"rules":[],"issues":[]}'),
            ]
        )

        with (
            patch.object(pricing_task, "_client", return_value=_client(completions)),
            patch.object(pricing_task, "_wait_before_model_retry") as wait_mock,
        ):
            result = pricing_task._run_tool_fallback(
                [{"role": "user", "content": "check"}],
                pricing_task._TOOL_SUBMIT_CHAPTER_RULE_CHECK,
                5000,
            )

        self.assertEqual(result, {"rules": [], "issues": []})
        self.assertEqual(completions.call_count, 2)
        wait_mock.assert_called_once()

    def test_stream_tool_retries_invalid_arguments_before_fallback(self):
        completions = _Completions(
            [
                _stream('{"rules":[{"action":"缺少右引号}]'),
                _stream('{"rules":[],"issues":[]}'),
            ]
        )

        with (
            patch.object(pricing_task, "_client", return_value=_client(completions)),
            patch.object(pricing_task, "_wait_before_model_retry") as wait_mock,
        ):
            events = list(
                pricing_task._stream_tool_call(
                    [{"role": "user", "content": "check"}],
                    pricing_task._TOOL_SUBMIT_CHAPTER_RULE_CHECK,
                    5000,
                )
            )

        self.assertEqual(events, [("tool_result", {"rules": [], "issues": []})])
        self.assertEqual(completions.call_count, 2)
        wait_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

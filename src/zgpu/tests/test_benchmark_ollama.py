"""Pure offline measurement tests: no model download or network required."""

import pytest

from zgpu.benchmarks import benchmark_ollama
from zgpu.benchmarks.benchmark_ollama import (
    MAX_PROMPT_CHARS,
    MAX_RESPONSE_BYTES,
    _NoRedirectHandler,
    main,
    parse_measurement,
)


def test_ollama_uses_actual_eval_counters():
    result = parse_measurement(
        {
            "done": True,
            "eval_count": 12,
            "eval_duration": 2_000_000_000,
            "prompt_eval_count": 4,
            "total_duration": 3_000_000_000,
        }
    )
    assert result["generated_tokens"] == 12
    assert result["decode_tokens_per_second"] == 6
    assert result["prompt_tokens"] == 4


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"done": False, "eval_count": 2, "eval_duration": 50},
        {"done": True, "eval_count": True, "eval_duration": 50},
        {"done": True, "eval_count": 2, "eval_duration": -1},
        {"done": True, "eval_count": 2, "eval_duration": 0},
        {"done": True, "eval_count": "2", "eval_duration": 1},
        {"done": True, "eval_count": 2, "eval_duration": 50, "prompt_eval_count": True},
        {"done": True, "eval_count": 2, "eval_duration": 50, "total_duration": -1},
        [],
    ],
)
def test_rejects_incomplete_or_invalid_responses(data):
    with pytest.raises(ValueError):
        parse_measurement(data)


def test_zero_duration_avoids_division_by_zero():
    assert (
        parse_measurement({"done": True, "eval_count": 0, "eval_duration": 0})["decode_tokens_per_second"]
        == 0
    )


def test_cli_rejects_bad_limits_before_network():
    with pytest.raises(SystemExit):
        main(["--model", "tiny", "--repeats", "0"])


def test_redirects_are_not_followed():
    handler = _NoRedirectHandler()

    assert handler.redirect_request(None, None, 307, "Temporary Redirect", {}, "http://example.com/") is None


def test_run_once_installs_redirect_rejection(monkeypatch):
    handlers = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size):
            return b'{"done":true,"eval_count":1,"eval_duration":1000000000}'

    class FakeOpener:
        def open(self, _request, timeout):
            assert timeout == 3
            return FakeResponse()

    def fake_build_opener(*registered_handlers):
        handlers.extend(registered_handlers)
        return FakeOpener()

    monkeypatch.setattr(benchmark_ollama.urllib.request, "build_opener", fake_build_opener)

    benchmark_ollama.run_once("tiny", "prompt", 1, 3)

    assert any(isinstance(handler, _NoRedirectHandler) for handler in handlers)


def test_run_once_rejects_oversized_response(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size):
            assert size == MAX_RESPONSE_BYTES + 1
            return b"x" * size

    class FakeOpener:
        def open(self, _request, timeout):
            return FakeResponse()

    monkeypatch.setattr(benchmark_ollama.urllib.request, "build_opener", lambda *_handlers: FakeOpener())

    with pytest.raises(ValueError, match="too large"):
        benchmark_ollama.run_once("tiny", "prompt", 1, 3)


def test_cli_rejects_oversized_prompt_before_network():
    with pytest.raises(SystemExit):
        main(["--model", "tiny", "--prompt", "x" * (MAX_PROMPT_CHARS + 1)])

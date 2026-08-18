"""tests/test_coder.py — Coder.generate() with urllib.request.urlopen mocked out.

No real network calls are made anywhere in this file.
"""

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import zcoder.core.resilience as resilience
from zcoder.services.coder import Coder


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    """Give every test its own circuit breaker so failures in one test
    don't trip the breaker for the next one."""
    monkeypatch.setattr(
        "zcoder.services.coder._default_breaker",
        resilience.CircuitBreaker(failure_threshold=10, reset_timeout=0.01),
    )


def _fake_response(payload: dict):
    body = json.dumps(payload).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


def test_generate_returns_error_without_api_key():
    c = Coder(api_key="", model="claude-sonnet-5")
    result = c.generate("hello")
    assert "[ERROR]" in result
    assert "API key" in result


def test_generate_concatenates_multiple_text_blocks():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5")
    payload = {
        "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ]
    }
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        result = c.generate("hi")
    assert result == "Hello world"


def test_generate_handles_refusal():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5")
    payload = {"content": [], "stop_reason": "refusal"}
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        result = c.generate("hi")
    assert result == "[REFUSED] Model declined this request."


def test_generate_no_sampling_params_for_sonnet5():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5", temperature=0.9)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return _fake_response({"content": [{"type": "text", "text": "ok"}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.generate("hi")
    assert "temperature" not in captured["payload"]


def test_generate_401_does_not_retry():
    c = Coder(api_key="sk-ant-bad", model="claude-sonnet-5")
    call_count = {"n": 0}

    def raise_401(req, timeout=None):
        call_count["n"] += 1
        raise urllib.error.HTTPError(
            url="", code=401, msg="unauthorized", hdrs=None, fp=io.BytesIO(b'{"error":"bad key"}')
        )

    with patch("urllib.request.urlopen", side_effect=raise_401):
        result = c.generate("hi")
    assert "[API ERROR 401]" in result
    assert call_count["n"] == 1  # auth errors are not retryable


def test_generate_500_retries_then_succeeds():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5")
    call_count = {"n": 0}

    def flaky(req, timeout=None):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise urllib.error.HTTPError(url="", code=503, msg="unavailable", hdrs=None, fp=io.BytesIO(b"{}"))
        return _fake_response({"content": [{"type": "text", "text": "recovered"}]})

    with patch("urllib.request.urlopen", side_effect=flaky), patch("time.sleep", return_value=None):
        result = c.generate("hi")
    assert result == "recovered"
    assert call_count["n"] == 3


def test_generate_429_exhausts_retries_returns_error():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5")

    def always_429(req, timeout=None):
        raise urllib.error.HTTPError(url="", code=429, msg="rate limited", hdrs=None, fp=io.BytesIO(b"{}"))

    with patch("urllib.request.urlopen", side_effect=always_429), patch("time.sleep", return_value=None):
        result = c.generate("hi")
    assert "[API ERROR 429]" in result


# ── v1.32.0: fast-mode validation (was previously unguarded/untested) ───


def test_fast_mode_sends_speed_fast_on_supported_model():
    c = Coder(api_key="sk-ant-test", model="claude-opus-4-8", fast_mode=True)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response({"content": [{"type": "text", "text": "hi"}]})
        c.generate("hello")
    sent_req = mock_urlopen.call_args[0][0]
    payload = json.loads(sent_req.data)
    assert payload["speed"] == "fast"


def test_fast_mode_on_opus_5_sends_speed_fast():
    c = Coder(api_key="sk-ant-test", model="claude-opus-5", fast_mode=True)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response({"content": [{"type": "text", "text": "hi"}]})
        c.generate("hello")
    sent_req = mock_urlopen.call_args[0][0]
    payload = json.loads(sent_req.data)
    assert payload["speed"] == "fast"


def test_fast_mode_on_opus_4_7_errors_without_calling_api():
    # Fast mode was removed for Opus 4.7 on 2026-07-24 and now 400s server
    # side -- the client should refuse locally instead of burning a request.
    c = Coder(api_key="sk-ant-test", model="claude-opus-4-7", fast_mode=True)
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = c.generate("hello")
    mock_urlopen.assert_not_called()
    assert "[ERROR]" in result
    assert "claude-opus-4-7" in result


def test_fast_mode_on_opus_4_6_warns_but_still_calls_api():
    # Fast mode was removed for Opus 4.6 on 2026-06-29 but silently falls
    # back to standard speed server-side -- safe to send, just pointless.
    c = Coder(api_key="sk-ant-test", model="claude-opus-4-6", fast_mode=True)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response({"content": [{"type": "text", "text": "hi"}]})
        c.generate("hello")
    sent_req = mock_urlopen.call_args[0][0]
    payload = json.loads(sent_req.data)
    assert payload["speed"] == "fast"


def test_fast_mode_off_never_sends_speed_field():
    c = Coder(api_key="sk-ant-test", model="claude-sonnet-5", fast_mode=False)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _fake_response({"content": [{"type": "text", "text": "hi"}]})
        c.generate("hello")
    sent_req = mock_urlopen.call_args[0][0]
    payload = json.loads(sent_req.data)
    assert "speed" not in payload

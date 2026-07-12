"""tests/test_claude_thinking.py

Covers claude_thinking.py's v1.25.0 addition: thinking.display="omitted"
(GA, no beta header) — see docs/37_upgrade_v1.25.0_audit_and_impl.md
Finding 1.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def thinking_mod(monkeypatch):
    fake_anthropic = types.ModuleType("anthropic")

    class _FakeClient:
        def __init__(self, api_key=None):
            self.messages = MagicMock()

    fake_anthropic.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    import importlib
    import claude_thinking as mod
    importlib.reload(mod)
    return mod


def _fake_message_response():
    resp = MagicMock()
    resp.content = []
    resp.usage = MagicMock()
    resp.usage.model_dump = lambda: {}
    return resp


def test_generate_with_thinking_display_omitted_sets_field(thinking_mod):
    tc = thinking_mod.ThinkingCoder(api_key="sk-test")
    tc.client.messages.create.return_value = _fake_message_response()

    tc.generate_with_thinking("q", display_omitted=True)

    _, kwargs = tc.client.messages.create.call_args
    assert kwargs["thinking"]["display"] == "omitted"


def test_generate_with_thinking_display_omitted_default_false_no_regression(thinking_mod):
    tc = thinking_mod.ThinkingCoder(api_key="sk-test")
    tc.client.messages.create.return_value = _fake_message_response()

    tc.generate_with_thinking("q")

    _, kwargs = tc.client.messages.create.call_args
    assert "display" not in kwargs["thinking"]


def test_generate_with_thinking_display_omitted_works_with_adaptive(thinking_mod):
    tc = thinking_mod.ThinkingCoder(api_key="sk-test")
    tc.client.messages.create.return_value = _fake_message_response()

    tc.generate_with_thinking("q", adaptive=True, display_omitted=True)

    _, kwargs = tc.client.messages.create.call_args
    assert kwargs["thinking"] == {"type": "adaptive", "budget_tokens": 8_000, "display": "omitted"}


def test_cmd_thinking_threads_display_omitted(thinking_mod, monkeypatch):
    captured = {}

    class FakeCoder:
        def __init__(self, api_key, model):
            pass

        def generate_with_thinking(self, prompt, **kwargs):
            captured.update(kwargs)
            return {"response": "ok", "usage": {}}

    monkeypatch.setattr(thinking_mod, "ThinkingCoder", FakeCoder)

    thinking_mod.cmd_thinking(
        "q", api_key="sk-test", model="claude-sonnet-5", budget=8000,
        effort=None, adaptive=False, show_thinking=False, stream=False,
        display_omitted=True,
    )

    assert captured["display_omitted"] is True

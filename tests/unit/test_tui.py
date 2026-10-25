"""Tests for the local llama-server Textual front end."""

from __future__ import annotations

import io
import json
import types

import pytest

pytest.importorskip("textual", reason="optional dependency for --tui")

import zcoder.interfaces.cli.tui as tui  # noqa: E402


@pytest.fixture
def local_server(monkeypatch):
    """Provide deterministic model discovery and completion responses."""
    requests = []

    def open_local(request, *, timeout):
        payload = json.loads(request.data) if request.data else None
        requests.append((request, payload, timeout))
        if payload is None:
            body = {"data": [{"id": "zcoder-qwen2.5-coder-7b"}]}
        elif payload["stream"]:
            body = (
                b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":" there"}}]}\n\n'
                b"data: [DONE]\n\n"
            )
            return io.BytesIO(body)
        else:
            body = {"choices": [{"message": {"content": "local response"}}]}
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(tui, "_open_local", open_local)
    return requests


@pytest.mark.asyncio
async def test_compose_builds_settings_and_transcript(local_server):
    app = tui.ZCoderTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#sidebar") is not None
        assert app.query_one("#transcript") is not None
        assert app.query_one("#prompt_input") is not None
        assert app.loaded_model == "zcoder-qwen2.5-coder-7b"


@pytest.mark.asyncio
async def test_prompt_uses_local_server_without_credentials(local_server):
    app = tui.ZCoderTUI(api_key="ignored")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt_input").value = "hello there"
        await pilot.press("enter")
        await pilot.pause(0.2)
        transcript = app.query_one("#transcript")
        messages = [c for c in transcript.children if isinstance(c, tui.ChatMessage)]
        assert any(message.role == "user" and message.raw_text == "hello there" for message in messages)
        assert any(message.role == "assistant" and message.raw_text == "Hello there" for message in messages)
        assert len(local_server) == 2
        assert local_server[1][0].full_url == "http://127.0.0.1:8080/v1/chat/completions"


@pytest.mark.asyncio
async def test_generation_guard_prevents_overlapping_requests(local_server):
    app = tui.ZCoderTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt_input").value = "first request"
        app._send()
        app.query_one("#prompt_input").value = "second request"
        app._send()
        await pilot.pause(0.2)
        assert len([request for request, payload, _ in local_server if payload is not None]) == 1
        assert app.history[-2]["content"] == "first request"


@pytest.mark.asyncio
async def test_new_session_clears_transcript_and_history(local_server):
    app = tui.ZCoderTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.history = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        app.action_new_session()
        await pilot.pause()
        assert app.history == []
        transcript = app.query_one("#transcript")
        assert len(transcript.children) == 1
        assert transcript.children[0].raw_text == "new session started."


@pytest.mark.asyncio
async def test_build_system_prompt_combines_agent_skill_personality(local_server):
    app = tui.ZCoderTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#agent_select").value = "code_reviewer"
        app.query_one("#skill_select").value = "testing"
        app.query_one("#personality_select").value = "precise"
        prompt = app._build_system_prompt()
        assert "code review agent" in prompt
        assert "testing" in prompt
        assert "concise" in prompt.lower()


@pytest.mark.asyncio
async def test_temperature_falls_back_to_default_and_clamps(local_server):
    app = tui.ZCoderTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        temp_input = app.query_one("#temp_input")
        temp_input.value = "not-a-number"
        assert app._temperature() == 0.3
        temp_input.value = "5.0"
        assert app._temperature() == 1.0


def test_local_server_url_rejects_non_loopback(monkeypatch):
    for url in ("https://127.0.0.1:8080", "http://model.example:8080", "http://user@127.0.0.1"):
        monkeypatch.setenv("ZCODER_BASE_URL", url)
        with pytest.raises(ValueError, match="loopback"):
            tui._local_server_base_url()


def test_local_server_endpoint_supports_existing_v1_prefix(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1/")
    assert tui._local_server_endpoint("chat/completions") == "http://127.0.0.1:8080/v1/chat/completions"


def test_run_tui_entry_point_ignores_legacy_api_key(monkeypatch):
    created = []

    class FakeApp:
        def __init__(self):
            created.append(self)

        def run(self):
            return None

    monkeypatch.setattr(tui, "ZCoderTUI", FakeApp)
    tui.run_tui(api_key="must-not-be-used")
    assert len(created) == 1


def test_streamed_reply_flushes_final_text(monkeypatch):
    monkeypatch.setattr(tui.time, "monotonic", lambda: 1.0)
    updates = []
    transcript = types.SimpleNamespace(scroll_end=lambda **kwargs: None)
    owner = types.SimpleNamespace(
        call_from_thread=lambda callback, *args, **kwargs: callback(*args, **kwargs),
        query_one=lambda selector: transcript,
    )
    stream = io.BytesIO(
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" there"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    owner._local_request = lambda *args, **kwargs: stream
    widget = types.SimpleNamespace(update_text=updates.append)

    result = tui.ZCoderTUI._stream_reply(owner, "hello", "local-model", None, 0.3, [], widget)

    assert result == "Hi there"
    assert updates[-1] == "Hi there"

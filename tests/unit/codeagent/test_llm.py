from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from zcoder.agent.codeagent.llm import LLMError, LocalLLM, _NoRedirect, endpoint, local_base_url


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "http://[::1]:8080/", "http://127.0.0.1:8080/v1"])
def test_loopback_urls_accepted(url):
    assert local_base_url(url).startswith("http://")


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8080",
        "http://example.com",
        "http://localhost:8080",
        "http://127.0.0.1@evil.com",
        "http://user:pw@127.0.0.1",
        "http://127.0.0.1:8080?x=1",
        "http://127.0.0.1:8080#f",
        "http://0.0.0.0:8080",
        "http://127.0.0.1.evil.com",
    ],
)
def test_non_loopback_urls_rejected(url):
    with pytest.raises(ValueError):
        local_base_url(url)


def test_endpoint_handles_v1_suffix():
    assert (
        endpoint("chat/completions", "http://127.0.0.1:8080") == "http://127.0.0.1:8080/v1/chat/completions"
    )
    assert endpoint("/models", "http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1/models"


def test_redirects_are_refused():
    assert _NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://evil") is None


def sse(*events):
    return io.BytesIO(
        "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events).encode()
    )


def fake_opener(body, seen=None, exc=None):
    def opener(request, *, timeout):
        if seen is not None:
            seen.append((request, timeout))
        if exc:
            raise exc
        return body

    return opener


async def drain(llm, tools=None):
    return [c async for c in llm.stream([{"role": "user", "content": "x"}], tools or [])]


async def test_stream_parses_text_reasoning_usage_and_split_tool_calls():
    body = sse(
        {"choices": [{"delta": {"reasoning_content": "thinking"}}]},
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "c1", "function": {"name": "Rea", "arguments": '{"pa'}}
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"name": "d", "arguments": 'th": "a.py"}'}}]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 1, "id": "c2", "function": {"name": "LS", "arguments": ""}}]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}},
        "[DONE]",
    )
    seen: list = []
    llm = LocalLLM(model="m", base_url="http://127.0.0.1:8080", opener=fake_opener(body, seen))
    chunks = await drain(llm, [{"type": "function"}])
    kinds = [c.kind for c in chunks]
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"
    assert [c.text for c in chunks if c.kind == "thinking"] == ["thinking"]
    calls = next(c.tool_calls for c in chunks if c.kind == "tool_calls")
    assert [(c.id, c.name, c.args) for c in calls] == [("c1", "Read", {"path": "a.py"}), ("c2", "LS", {})]
    usage = next(c for c in chunks if c.kind == "usage")
    assert (usage.prompt_tokens, usage.completion_tokens) == (11, 7)
    assert kinds[-1] == "finish" and chunks[-1].finish_reason == "tool_calls"
    payload = json.loads(seen[0][0].data)
    assert (
        payload["stream"] is True and payload["tools"] == [{"type": "function"}] and payload["model"] == "m"
    )


async def test_malformed_tool_arguments_are_flagged_not_crashed():
    body = sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "c", "function": {"name": "Read", "arguments": "{oops"}}
                        ]
                    }
                }
            ]
        },
        "[DONE]",
    )
    chunks = await drain(LocalLLM(base_url="http://127.0.0.1:1", opener=fake_opener(body)))
    call = next(c.tool_calls[0] for c in chunks if c.kind == "tool_calls")
    assert "__parse_error__" in call.args


async def test_garbage_sse_lines_are_ignored():
    body = io.BytesIO(
        b': keepalive\n\nevent: x\n\ndata: {broken\n\ndata: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
    )
    chunks = await drain(LocalLLM(base_url="http://127.0.0.1:1", opener=fake_opener(body)))
    assert "".join(c.text for c in chunks if c.kind == "text") == "ok"


@pytest.mark.parametrize(
    "code,retryable", [(503, True), (429, True), (400, False), (401, False), (500, True)]
)
async def test_http_errors_map_to_retryability(code, retryable):
    err = urllib.error.HTTPError("http://x", code, "boom", {}, io.BytesIO(b"details"))
    llm = LocalLLM(base_url="http://127.0.0.1:1", opener=fake_opener(None, exc=err))
    with pytest.raises(LLMError) as info:
        await drain(llm)
    assert info.value.retryable is retryable and str(code) in str(info.value)


async def test_connection_refused_is_retryable():
    llm = LocalLLM(
        base_url="http://127.0.0.1:1", opener=fake_opener(None, exc=urllib.error.URLError("refused"))
    )
    with pytest.raises(LLMError) as info:
        await drain(llm)
    assert info.value.retryable and "refused" in str(info.value)


async def test_midstream_failure_surfaces_as_llm_error():
    class Broken(io.BytesIO):
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n'
            raise ConnectionResetError("reset")

    llm = LocalLLM(base_url="http://127.0.0.1:1", opener=fake_opener(Broken()))
    got = []
    with pytest.raises(LLMError):
        async for c in llm.stream([], []):
            got.append(c)
    assert got and got[0].text == "a"


def test_discover_model_sets_model_and_tolerates_failure():
    body = io.BytesIO(json.dumps({"data": [{"id": "qwen-coder.gguf"}]}).encode())
    llm = LocalLLM(model="old", base_url="http://127.0.0.1:1", opener=fake_opener(body))
    assert llm.discover_model() == "qwen-coder.gguf" and llm.model == "qwen-coder.gguf"
    down = LocalLLM(
        model="old", base_url="http://127.0.0.1:1", opener=fake_opener(None, exc=urllib.error.URLError("x"))
    )
    assert down.discover_model() is None and down.model == "old"


def test_constructor_refuses_remote_base_url(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "http://api.example.com")
    with pytest.raises(ValueError):
        LocalLLM()
    assert urllib.request  # keep import used

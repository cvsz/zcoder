from __future__ import annotations

import pytest

from zcoder.agent.codeagent.llm import LLMChunk, ToolCallRequest
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.permissions import PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.workspace import Workspace


class FakeLLM:
    """Scripted LLM: each script entry is one model response (text and/or tool calls)."""

    model = "fake-model"

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[tuple[list, list]] = []

    async def stream(self, messages, tools):
        self.requests.append((list(messages), list(tools)))
        step = self.script.pop(0) if self.script else {"text": "done"}
        if isinstance(step, Exception):
            raise step
        for piece in step.get("chunks", [step["text"]] if step.get("text") else []):
            yield LLMChunk("text", text=piece)
        if step.get("calls"):
            yield LLMChunk(
                "tool_calls",
                tool_calls=[ToolCallRequest(f"c{i}", n, a) for i, (n, a) in enumerate(step["calls"])],
            )
        yield LLMChunk("usage", prompt_tokens=step.get("prompt", 10), completion_tokens=5)
        yield LLMChunk("finish", finish_reason="stop")


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZCODER_HOME", str(tmp_path / ".zhome"))


@pytest.fixture
def make_agent(ws, tmp_path):
    def _make(script, *, ask=None, mode=None, **kw):
        policy = PermissionPolicy(workspace=ws)
        if mode:
            policy.mode = mode
        return CodeAgent(
            FakeLLM(script),
            ws,
            policy=policy,
            ask=ask,
            store=SessionStore(tmp_path / "sess"),
            memory=[],
            **kw,
        )

    return _make


async def collect(agent, text):
    return [e async for e in agent.run(text)]

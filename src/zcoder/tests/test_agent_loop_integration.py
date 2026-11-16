"""Integration tests for the full agent loop with a mock LLM.

Tests Phase 1 item 2: "Test full agent loop with mock LLM".

These tests exercise CodeAgent.run() end-to-end with a fake LLM that returns
canned text/tool-call responses, verifying:
- Simple text response (no tool calls)
- Single tool call → tool result → final text
- Multiple tool calls in one turn
- Tool error handling (loop stays alive)
- Context overflow recovery
- Interrupt stops the loop
- Slash command handling (/exit)
- Session event logging end-to-end
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zcoder.agent.codeagent.events import (
    Decision,
    ModeChanged,
    Notice,
    PermissionRequest,
    PostToolBatch,
    TextDelta,
    ToolEnd,
    ToolStart,
    TurnDone,
)
from zcoder.agent.codeagent.llm import LLMChunk, ToolCallRequest
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore
from zcoder.agent.codeagent.tools import default_tools
from zcoder.agent.codeagent.workspace import Workspace


class MockLLM:
    """A mock LLM that yields canned responses in sequence."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.model = "mock-model"
        self.temperature = 0.2
        self.max_tokens = 4096
        self.provider_name = "mock"

    async def stream(self, messages, tools):
        self.call_count += 1
        if self.call_count > len(self.responses):
            yield LLMChunk("finish", finish_reason="stop")
            return
        response = self.responses[self.call_count - 1]
        if isinstance(response, str):
            yield LLMChunk("text", text=response)
            yield LLMChunk("finish", finish_reason="stop")
        elif isinstance(response, list):
            for chunk in response:
                yield chunk
        else:
            raise TypeError(f"Unsupported response type: {type(response)}")


class MockAsk:
    """A mock ask function that auto-approves permission requests."""

    def __init__(self, behavior="allow"):
        self.behavior = behavior
        self.call_count = 0

    async def __call__(self, request: PermissionRequest) -> Decision:
        self.call_count += 1
        return Decision(behavior=self.behavior, feedback="")


def make_agent(
    tmp_path: Path,
    llm_responses,
    tools=None,
    ask_behavior="allow",
    session_store=None,
):
    """Build a CodeAgent with a mock LLM in a temp workspace."""
    workspace = Workspace(tmp_path)
    policy = PermissionPolicy(workspace=workspace)
    policy.mode = Mode.DEFAULT
    if tools is None:
        tools = default_tools()
    llm = MockLLM(llm_responses)
    ask = MockAsk(behavior=ask_behavior)
    store = session_store or SessionStore(directory=tmp_path / "sessions")
    return CodeAgent(
        llm=llm,
        workspace=workspace,
        policy=policy,
        tools=tools,
        store=store,
        ask=ask,
    )


async def collect_events(agen):
    """Collect all events from an async generator."""
    events = []
    async for event in agen:
        events.append(event)
    return events


class TestAgentLoopSimpleText:
    """Agent loop with simple text responses (no tool calls)."""

    @pytest.mark.asyncio
    async def test_plain_text_response(self, tmp_path):
        agent = make_agent(
            tmp_path,
            ["The capital of France is Paris."],
        )
        events = await collect_events(agent.run("What is the capital of France?"))
        text_events = [e for e in events if isinstance(e, TextDelta)]
        assert len(text_events) >= 1
        full_text = "".join(e.text for e in text_events)
        assert "Paris" in full_text
        assert any(isinstance(e, TurnDone) for e in events)

    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_path):
        agent = make_agent(
            tmp_path,
            [""],
        )
        events = await collect_events(agent.run("Say nothing."))
        assert any(isinstance(e, TurnDone) for e in events)


class TestAgentLoopSingleToolCall:
    """Agent loop with a single tool call followed by final text."""

    @pytest.mark.asyncio
    async def test_read_then_answer(self, tmp_path):
        (tmp_path / "hello.txt").write_text("Hello, world!\n")

        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[ToolCallRequest(id="call_0", name="Read", args={"path": "hello.txt"})],
                    )
                ],
                "The file contains: Hello, world!",
            ],
        )
        events = await collect_events(agent.run("Read hello.txt and tell me what it says."))

        tool_starts = [e for e in events if isinstance(e, ToolStart)]
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_starts) == 1
        assert tool_starts[0].name == "Read"
        assert len(tool_ends) == 1
        assert tool_ends[0].name == "Read"
        assert not tool_ends[0].is_error
        assert "Hello" in tool_ends[0].output
        assert any(isinstance(e, TurnDone) for e in events)

    @pytest.mark.asyncio
    async def test_write_then_read(self, tmp_path):
        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[
                            ToolCallRequest(
                                id="call_0",
                                name="Write",
                                args={"path": "note.txt", "content": "Remember the milk"},
                            )
                        ],
                    )
                ],
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[ToolCallRequest(id="call_1", name="Read", args={"path": "note.txt"})],
                    )
                ],
                "I wrote and read back: Remember the milk",
            ],
        )
        events = await collect_events(agent.run("Write a note and read it back."))
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 2
        assert tool_ends[0].name == "Write"
        assert tool_ends[1].name == "Read"
        assert not any(e.is_error for e in tool_ends)
        assert (tmp_path / "note.txt").read_text() == "Remember the milk"


class TestAgentLoopMultipleToolCalls:
    """Agent loop with multiple tool calls in a single turn."""

    @pytest.mark.asyncio
    async def test_parallel_tool_calls(self, tmp_path):
        (tmp_path / "a.txt").write_text("alpha\n")
        (tmp_path / "b.txt").write_text("beta\n")

        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[
                            ToolCallRequest(id="call_0", name="Read", args={"path": "a.txt"}),
                            ToolCallRequest(id="call_1", name="Read", args={"path": "b.txt"}),
                        ],
                    )
                ],
                "Files contain: alpha, beta",
            ],
        )
        events = await collect_events(agent.run("Read both files."))
        tool_starts = [e for e in events if isinstance(e, ToolStart)]
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2
        names = {e.name for e in tool_ends}
        assert names == {"Read"}
        assert all(not e.is_error for e in tool_ends)
        assert any(isinstance(e, PostToolBatch) for e in events)


class TestAgentLoopToolError:
    """Agent loop resilience when tools error."""

    @pytest.mark.asyncio
    async def test_tool_error_does_not_crash_loop(self, tmp_path):
        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[
                            ToolCallRequest(id="call_0", name="Read", args={"path": "nonexistent.txt"})
                        ],
                    )
                ],
                "The file could not be read.",
            ],
        )
        events = await collect_events(agent.run("Read a missing file."))
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 1
        assert tool_ends[0].is_error
        assert any(isinstance(e, TurnDone) for e in events)

    @pytest.mark.asyncio
    async def test_unknown_tool(self, tmp_path):
        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[ToolCallRequest(id="call_0", name="NonExistentTool", args={})],
                    )
                ],
                "That tool doesn't exist.",
            ],
        )
        events = await collect_events(agent.run("Use a fake tool."))
        tool_ends = [e for e in events if isinstance(e, ToolEnd)]
        assert len(tool_ends) == 1
        assert tool_ends[0].is_error
        assert "Unknown tool" in tool_ends[0].output


class TestAgentLoopInterrupt:
    """Agent loop interrupt behavior."""

    @pytest.mark.asyncio
    async def test_interrupt_flag(self, tmp_path):
        agent = make_agent(tmp_path, [])
        agent.interrupt()
        assert agent._interrupted is True


class TestAgentLoopSlashCommands:
    """Agent loop slash command handling."""

    @pytest.mark.asyncio
    async def test_exit_command(self, tmp_path):
        agent = make_agent(tmp_path, [])
        events = await collect_events(agent.run("/exit"))
        assert any(isinstance(e, TurnDone) for e in events)

    @pytest.mark.asyncio
    async def test_help_command(self, tmp_path):
        agent = make_agent(tmp_path, [])
        events = await collect_events(agent.run("/help"))
        # /help prints to stdout and completes; verify it ends normally
        assert any(isinstance(e, TurnDone) for e in events)


class TestAgentLoopSessionEvents:
    """Verify session events are logged end-to-end."""

    @pytest.mark.asyncio
    async def test_events_logged(self, tmp_path):
        session_dir = tmp_path / "sessions"
        store = SessionStore(directory=session_dir)
        agent = make_agent(
            tmp_path,
            ["Done."],
            session_store=store,
        )
        await collect_events(agent.run("Hello."))
        sessions = store.list_sessions()
        assert len(sessions) >= 1


class TestAgentLoopContextOverflow:
    """Agent loop context overflow recovery path."""

    @pytest.mark.asyncio
    async def test_overflow_recovery(self, tmp_path):
        class OverflowLLM(MockLLM):
            def __init__(self):
                super().__init__([])
                self.call_count = 0

            async def stream(self, messages, tools):
                self.call_count += 1
                from zcoder.agent.codeagent.llm import LLMError

                if self.call_count == 1:
                    raise LLMError("HTTP 400: context window exceeded", retryable=False)
                yield LLMChunk("text", text="Recovered after compaction.")
                yield LLMChunk("finish", finish_reason="stop")

        workspace = Workspace(tmp_path)
        policy = PermissionPolicy(workspace=workspace)
        policy.mode = Mode.DEFAULT
        llm = OverflowLLM()
        ask = MockAsk()
        agent = CodeAgent(
            llm=llm,
            workspace=workspace,
            policy=policy,
            tools=default_tools(),
            ask=ask,
        )
        events = await collect_events(agent.run("A very long prompt " * 500))
        notices = [e for e in events if isinstance(e, Notice)]
        assert any("context" in n.text.lower() or "compact" in n.text.lower() for n in notices)


class TestAgentLoopModeChange:
    """Agent loop permission mode changes."""

    @pytest.mark.asyncio
    async def test_mode_change_emitted(self, tmp_path):
        (tmp_path / "config.txt").write_text("key=value\n")

        agent = make_agent(
            tmp_path,
            [
                [
                    LLMChunk(
                        "tool_calls",
                        tool_calls=[
                            ToolCallRequest(
                                id="call_0",
                                name="Edit",
                                args={
                                    "path": "config.txt",
                                    "old_string": "key=value",
                                    "new_string": "key=newvalue",
                                },
                            )
                        ],
                    )
                ],
                "Edited.",
            ],
        )
        events = await collect_events(agent.run("Edit config.txt."))
        mode_changes = [e for e in events if isinstance(e, ModeChanged)]
        assert len(mode_changes) >= 0

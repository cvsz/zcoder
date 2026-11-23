"""Tests for zcoder.agent.codeagent.loop - Agent loop module."""

from unittest.mock import MagicMock

from zcoder.agent.codeagent.loop import (
    CodeAgent,
    _TagFilter,
    looks_like_context_overflow,
    parse_text_tool_calls,
)
from zcoder.agent.codeagent.permissions import PermissionPolicy
from zcoder.agent.codeagent.workspace import Workspace


class TestLooksLikeContextOverflow:
    """Tests for looks_like_context_overflow function."""

    def test_overflow_detected(self):
        """Test that context overflow is detected."""
        assert looks_like_context_overflow("HTTP 400: context window exceeded") is True
        assert looks_like_context_overflow("HTTP 400: Input too long") is True
        assert looks_like_context_overflow("response too large") is False

    def test_no_overflow(self):
        """Test that normal text doesn't trigger overflow detection."""
        assert looks_like_context_overflow("Hello world") is False
        assert looks_like_context_overflow("") is False
        assert looks_like_context_overflow("Normal response text") is False


class TestParseTextToolCalls:
    """Tests for parse_text_tool_calls function."""

    def test_no_tool_calls(self):
        """Test that plain text returns empty list."""
        calls = parse_text_tool_calls("Hello world")
        assert calls == []

    def test_single_tool_call(self):
        """Test parsing a single tool call."""
        calls = parse_text_tool_calls(
            '<tool_call>{"name": "read_file", "arguments": {"path": "/etc/passwd"}}</tool_call>'
        )
        assert len(calls) == 1
        assert calls[0].id == "text_call_0"
        assert calls[0].name == "read_file"
        assert calls[0].args == {"path": "/etc/passwd"}

    def test_multiple_tool_calls(self):
        """Test parsing multiple tool calls."""
        text = (
            '<tool_call>{"name": "read_file", "arguments": {"path": "/a"}}</tool_call>'
            ' <tool_call>{"name": "write_file", "arguments": {"path": "/b"}}</tool_call>'
        )
        calls = parse_text_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "read_file"
        assert calls[1].name == "write_file"

    def test_invalid_json_ignored(self):
        """Test that invalid JSON in tool call format is skipped."""
        calls = parse_text_tool_calls('<tool_call>{"name": "test", "arguments": invalid}</tool_call>')
        assert calls == []


class TestTagFilter:
    """Tests for _TagFilter class."""

    def test_feed_no_tag(self):
        """Test feeding text without tags."""
        f = _TagFilter()
        result = f.feed("Hello world")
        assert result == "Hello world"

    def test_feed_with_tag(self):
        """Test feeding text with tool call tag."""
        f = _TagFilter()
        result = f.feed('Before <tool_call>{"name": "foo"}</tool_call> After')
        assert result == "Before "
        assert f.hidden == '<tool_call>{"name": "foo"}</tool_call> After'

    def test_feed_within_tag(self):
        """Test feeding content within tags."""
        f = _TagFilter()
        f.feed("Before <tool_call>")
        result = f.feed("inside tag")
        assert result == ""
        assert "inside tag" in f.hidden

    def test_flush(self):
        """Test flush method when partial tag prefix was buffered."""
        f = _TagFilter()
        out = f.feed("Before <tool")
        assert out == "Before "
        result = f.flush()
        assert result == "<tool"


class TestCodeAgent:
    """Tests for CodeAgent class."""

    def test_init(self, tmp_path):
        """Test CodeAgent initialization."""
        llm = MagicMock()
        workspace = Workspace(tmp_path)
        agent = CodeAgent(llm=llm, workspace=workspace)
        assert agent.llm is llm
        assert agent.ws is workspace
        assert agent.running is False
        assert agent._interrupted is False

    def test_init_with_params(self, tmp_path):
        """Test initialization with custom parameters."""
        llm = MagicMock()
        workspace = Workspace(tmp_path)
        policy = PermissionPolicy(workspace=workspace)
        from zcoder.agent.codeagent.tools import default_tools

        custom_tools = default_tools()
        agent = CodeAgent(
            llm=llm,
            workspace=workspace,
            policy=policy,
            tools=custom_tools,
        )
        assert agent.llm is llm
        assert agent.ws is workspace
        assert agent.policy is policy
        assert agent.tools == custom_tools

    def test_interrupt(self, tmp_path):
        """Test interrupt functionality."""
        llm = MagicMock()
        workspace = Workspace(tmp_path)
        agent = CodeAgent(llm=llm, workspace=workspace)
        agent.running = True
        agent.interrupt()
        assert agent._interrupted is True

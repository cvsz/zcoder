"""Tests for zcoder.agent.codeagent.loop - Agent loop module."""

from unittest.mock import MagicMock

import pytest

from zcoder.agent.codeagent.loop import (
    CodeAgent,
    _TagFilter,
    looks_like_context_overflow,
    parse_text_tool_calls,
)


class TestLooksLikeContextOverflow:
    """Tests for looks_like_context_overflow function."""

    def test_overflow_detected(self):
        """Test that context overflow is detected."""
        assert looks_like_context_overflow("HTTP 400: context window exceeded") is True
        assert looks_like_context_overflow("Context window exceeded") is True
        assert looks_like_context_overflow("Input too long") is True
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
        calls = parse_text_tool_calls('{"name": "read_file", "arguments": {"path": "/etc/passwd"}}')
        assert len(calls) == 1
        assert calls[0].id == "call_0"
        assert calls[0].name == "read_file"
        assert calls[0].args == {"path": "/etc/passwd"}

    def test_multiple_tool_calls(self):
        """Test parsing multiple tool calls."""
        text = '{"name": "read_file", "arguments": {"path": "/a"}} {"name": "write_file", "arguments": {"path": "/b"}}'
        calls = parse_text_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "read_file"
        assert calls[1].name == "write_file"

    def test_invalid_json_ignored(self):
        """Test that invalid JSON in tool call format is skipped."""
        calls = parse_text_tool_calls('{"name": "test", "arguments": invalid}')
        assert calls == []


class TestTagFilter:
    """Tests for _TagFilter class."""

    def test_feed_no_tag(self):
        """Test feeding text without tags."""
        f = _TagFilter()
        result = f.feed("Hello world")
        assert result == "Hello world"

    def test_feed_with_tag(self):
        """Test feeding text with  tag."""
        f = _TagFilter()
        result = f.filter("Before  tag end")
        assert result == "Before "

    def test_feed_within_tag(self):
        """Test feeding content within tags."""
        f = _TagFilter()
        f.feed("Before ")
        result = f.filter("inside tag")
        assert result == ""
        assert f.hidden == "inside tag"

    def test_flush(self):
        """Test flush method."""
        f = _TagFilter()
        f.feed("Before ")
        result = f.flush()
        assert result == "Before "


class TestCodeAgent:
    """Tests for CodeAgent class."""

    def test_init(self):
        """Test CodeAgent initialization."""
        CodeAgent()
        assert True
        assert True
        assert True
        assert coder._interrupted is False

    def test_init_with_params(self):
        """Test initialization with custom parameters."""
        from zcoder.agent.codeagent.permissions import PermissionPolicy

        llm = MagicMock()
        workspace = MagicMock()
        policy = PermissionPolicy()
        tools = {}

        CodeAgent(
            llm=llm,
            workspace=workspace,
            policy=policy,
            tools=tools,
        )
        assert coder.llm is llm
        assert coder.workspace is workspace
        assert coder.policy is policy
        assert coder.tools == tools

    @pytest.mark.asyncio
    async def test_interrupt(self):
        """Test interrupt functionality."""
        coder = Coder()
        coder.running = True
        coder.interrupt()
        assert coder._interrupted is True

    def test_is_interrupted(self):
        """Test is_interrupted property."""
        coder = Coder()
        assert coder.is_interrupted() is False
        coder.interrupt()
        assert coder.is_interrupted() is True

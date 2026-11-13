"""Tests for HookBus."""

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier


class TestHookContext:
    """Tests for HookContext."""

    def test_default_values(self):
        """Test default values."""
        ctx = HookContext(event=HookEvent.SESSION_START)
        assert ctx.event == HookEvent.SESSION_START
        assert ctx.tool == ""
        assert ctx.args == {}
        assert ctx.session_id == ""
        assert ctx.cwd == ""
        assert ctx.origin_tier == PluginTier.USER
        assert ctx.provider == ""
        assert ctx.approver == ""
        assert ctx.extra == {}

    def test_custom_values(self):
        """Test custom values."""
        ctx = HookContext(
            event=HookEvent.PRE_TOOL_USE,
            tool="read_file",
            args={"path": "/test.py"},
            session_id="sess_123",
            cwd="/home/user",
            origin_tier=PluginTier.PREPEND,
        )
        assert ctx.event == HookEvent.PRE_TOOL_USE
        assert ctx.tool == "read_file"
        assert ctx.args == {"path": "/test.py"}
        assert ctx.session_id == "sess_123"
        assert ctx.cwd == "/home/user"
        assert ctx.origin_tier == PluginTier.PREPEND


class TestHookResult:
    """Tests for HookResult."""

    def test_default_values(self):
        """Test default values."""
        result = HookResult()
        assert result.blocked is False
        assert result.message == ""
        assert result.warnings == ()
        assert result.modified_args is None
        assert result.deny_reason is None
        assert result.continue_past_user_tier is False

    def test_blocked_result(self):
        """Test blocked result."""
        result = HookResult(blocked=True, message="Access denied", deny_reason="policy")
        assert result.blocked is True
        assert result.message == "Access denied"
        assert result.deny_reason == "policy"

    def test_warnings(self):
        """Test warnings."""
        result = HookResult(warnings=("Warning 1", "Warning 2"))
        assert result.warnings == ("Warning 1", "Warning 2")

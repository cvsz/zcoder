"""Tests for zcoder.tools - tool registry, guard, and waterfall."""

import asyncio
from pathlib import Path

import pytest

from zcoder.agent.codeagent.tools import _delete
from zcoder.agent.codeagent.workspace import ToolError as WorkspaceToolError
from zcoder.agent.codeagent.workspace import Workspace
from zcoder.tools.definition import ToolError, ToolProtocol
from zcoder.tools.guard import GuardedToolExecutor, LoopGuard, TimeoutGuard
from zcoder.tools.registry import ToolRegistry
from zcoder.tools.types import ToolContext, ToolOutput, ToolResult
from zcoder.tools.waterfall import WaterfallListenerChain


class _FakeTool:
    """Fake tool implementing ToolProtocol."""

    def __init__(self, name: str = "fake", should_fail: bool = False):
        self._name = name
        self._should_fail = should_fail
        self.execute_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A fake tool for testing"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    @property
    def category(self) -> str:
        return "meta"

    async def execute(self, context: ToolContext, params: dict):
        self.execute_count += 1
        if self._should_fail:
            raise ValueError("fake tool failure")
        return ToolOutput(text=f"result from {self._name}", diff=None)


class TestToolProtocol:
    """Tests for ToolProtocol."""

    def test_fake_tool_implements_protocol(self):
        tool = _FakeTool()
        assert isinstance(tool, ToolProtocol)
        assert tool.name == "fake"
        assert tool.description == "A fake tool for testing"
        assert tool.category == "meta"

    def test_tool_error(self):
        err = ToolError("test error", tool="fake", details={"key": "val"})
        assert err.error_code == "TOOL_ERROR"
        assert err.tool == "fake"
        assert err.details == {"key": "val"}
        assert str(err) == "test error"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = _FakeTool("test-tool")
        reg.register_tool(tool)
        assert reg.get_tool("test-tool") is tool
        assert reg.has_tool("test-tool") is True
        assert "test-tool" in reg.list_tools()

    def test_register_duplicate_raises(self):
        reg = ToolRegistry()
        tool = _FakeTool("dup")
        reg.register_tool(tool)
        with pytest.raises(ToolError, match="already registered"):
            reg.register_tool(_FakeTool("dup"))

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get_tool("nonexistent") is None
        assert reg.has_tool("nonexistent") is False

    def test_unregister(self):
        reg = ToolRegistry()
        tool = _FakeTool("temp")
        reg.register_tool(tool)
        assert reg.unregister_tool("temp") is True
        assert reg.has_tool("temp") is False
        assert reg.unregister_tool("temp") is False

    def test_disposer_unregisters(self):
        reg = ToolRegistry()
        tool = _FakeTool("disposable")
        disposer = reg.register_tool(tool)
        assert reg.has_tool("disposable") is True
        disposer()
        assert reg.has_tool("disposable") is False

    def test_get_definitions(self):
        reg = ToolRegistry()
        tool = _FakeTool("def-tool")
        reg.register_tool(tool)
        defs = reg.get_definitions()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "def-tool"

    def test_global_registry_shared(self):
        from zcoder.tools.registry import registry as r1
        from zcoder.tools.registry import registry as r2

        assert r1 is r2


class TestLoopGuard:
    """Tests for LoopGuard."""

    def test_record_call_within_limits(self):
        guard = LoopGuard(max_calls_per_turn=5, max_calls_per_session=10)
        guard.start_turn()
        for _ in range(5):
            guard.record_call()
        assert guard.turn_calls == 5
        assert guard.session_calls == 5

    def test_turn_limit_exceeded(self):
        guard = LoopGuard(max_calls_per_turn=2, max_calls_per_session=100)
        guard.start_turn()
        guard.record_call()
        guard.record_call()
        with pytest.raises(ToolError, match="Tool call limit exceeded"):
            guard.record_call()

    def test_session_limit_exceeded(self):
        guard = LoopGuard(max_calls_per_turn=100, max_calls_per_session=2)
        guard.start_turn()
        guard.record_call()  # session_calls = 1
        guard.record_call()  # session_calls = 2 (at limit, OK)
        with pytest.raises(ToolError, match="Session tool call limit exceeded"):
            guard.record_call()  # session_calls = 3 (exceeds limit)

    def test_start_turn_resets_counter(self):
        guard = LoopGuard(max_calls_per_turn=2)
        guard.start_turn()
        guard.record_call()
        guard.record_call()
        guard.start_turn()
        assert guard.turn_calls == 0
        # Session counter persists
        assert guard.session_calls == 2


class TestTimeoutGuard:
    """Tests for TimeoutGuard."""

    def test_success_within_timeout(self):
        guard = TimeoutGuard(default_timeout=10.0)

        async def fast_op():
            await asyncio.sleep(0.01)
            return "done"

        result = asyncio.run(guard.run_with_timeout(fast_op(), timeout=5.0))
        assert result == "done"

    def test_timeout_raises(self):
        guard = TimeoutGuard(default_timeout=10.0)

        async def slow_op():
            await asyncio.sleep(60)

        with pytest.raises(ToolError, match="timed out"):
            asyncio.run(guard.run_with_timeout(slow_op(), timeout=0.1))


class TestGuardedToolExecutor:
    """Tests for GuardedToolExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        executor = GuardedToolExecutor()
        executor.start_turn()
        tool = _FakeTool("success-tool")
        context = ToolContext()

        result = await executor.execute(tool, context, {"key": "val"})

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.error is None
        assert tool.execute_count == 1

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        executor = GuardedToolExecutor()
        executor.start_turn()
        tool = _FakeTool("fail-tool", should_fail=True)
        context = ToolContext()

        result = await executor.execute(tool, context, {})

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.error == "fake tool failure"

    @pytest.mark.asyncio
    async def test_loop_guard_enforced(self):
        executor = GuardedToolExecutor(loop_guard=LoopGuard(max_calls_per_turn=2, max_calls_per_session=100))
        executor.start_turn()
        tool = _FakeTool("loop-tool")
        context = ToolContext()

        await executor.execute(tool, context, {})
        await executor.execute(tool, context, {})
        with pytest.raises(ToolError, match="Tool call limit exceeded"):
            await executor.execute(tool, context, {})

    @pytest.mark.asyncio
    async def test_timeout_guard_enforced(self):
        executor = GuardedToolExecutor(timeout_guard=TimeoutGuard(default_timeout=10.0))
        executor.start_turn()

        async def slow_execute(context, params):
            await asyncio.sleep(60)
            return ToolOutput(text="never", diff=None)

        tool = _FakeTool("slow-tool")
        tool.execute = slow_execute  # type: ignore
        context = ToolContext()

        result = await executor.execute(tool, context, {}, timeout=0.1)
        assert result.success is False
        assert result.error is not None


class TestWaterfallListenerChain:
    """Tests for WaterfallListenerChain."""

    @pytest.mark.asyncio
    async def test_chain_passes_value_through(self):
        chain = WaterfallListenerChain()

        async def listener1(value, next_):
            return await next_(value + "1")

        async def listener2(value, next_):
            return await next_(value + "2")

        async def listener3(value, next_):
            return await next_(value + "3")

        chain.add_listener(listener1)
        chain.add_listener(listener2)
        chain.add_listener(listener3)

        result = await chain.run("")
        assert result == "123"

    @pytest.mark.asyncio
    async def test_chain_short_circuit(self):
        chain = WaterfallListenerChain()

        async def listener1(value, next_):
            # Short-circuit: don't call next()
            return "short-circuited"

        async def listener2(value, next_):
            return await next_(value + "2")

        chain.add_listener(listener1)
        chain.add_listener(listener2)

        result = await chain.run("start")
        assert result == "short-circuited"

    @pytest.mark.asyncio
    async def test_chain_empty(self):
        chain = WaterfallListenerChain()
        result = await chain.run("initial")
        assert result == "initial"

    @pytest.mark.asyncio
    async def test_chain_transform(self):
        chain = WaterfallListenerChain()

        async def listener1(value, next_):
            return await next_(value.upper())

        async def listener2(value, next_):
            return await next_(value + "!")

        chain.add_listener(listener1)
        chain.add_listener(listener2)

        result = await chain.run("hello")
        assert result == "HELLO!"

    def test_chain_len_and_iter(self):
        chain = WaterfallListenerChain()
        assert len(chain) == 0

        async def l1(value, next_):
            return await next_(value)

        chain.add_listener(l1)
        assert len(chain) == 1
        assert l1 in chain


class TestDeleteTool:
    """Tests for the _delete tool function."""

    def _make_ctx(self, tmp_path: Path):
        ws = Workspace(tmp_path)
        return ToolContext(workspace=ws)

    def test_delete_existing_file(self, tmp_path):
        """Deleting an existing file removes it and returns a confirmation."""
        ctx = self._make_ctx(tmp_path)
        target = tmp_path / "to_delete.txt"
        target.write_text("temporary content\n")

        result = _delete(ctx, {"path": "to_delete.txt"})

        assert not target.exists()
        assert f"Deleted {target.name}" in result.text
        assert result.diff is None

    def test_delete_nonexistent_file_raises(self, tmp_path):
        """Deleting a file that does not exist raises ToolError."""
        ctx = self._make_ctx(tmp_path)
        with pytest.raises(WorkspaceToolError, match="does not exist"):
            _delete(ctx, {"path": "no_such_file.txt"})

    def test_delete_protected_path_raises(self, tmp_path):
        """Deleting inside .git is refused."""
        ctx = self._make_ctx(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n")

        with pytest.raises(WorkspaceToolError, match="inside .git"):
            _delete(ctx, {"path": ".git/config"})

    def test_delete_sensitive_file_raises(self, tmp_path):
        """Deleting sensitive files (.env, .pem, etc.) is refused."""
        ctx = self._make_ctx(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=abc\n")

        with pytest.raises(WorkspaceToolError, match="sensitive"):
            _delete(ctx, {"path": ".env"})

        pem_file = tmp_path / "id_rsa"
        pem_file.write_text("-----BEGIN KEY-----\n")
        with pytest.raises(WorkspaceToolError, match="sensitive"):
            _delete(ctx, {"path": "id_rsa"})

    def test_delete_directory_raises(self, tmp_path):
        """Deleting a directory is refused."""
        ctx = self._make_ctx(tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with pytest.raises(WorkspaceToolError, match="is a directory"):
            _delete(ctx, {"path": "subdir"})

    def test_delete_records_checkpoint(self, tmp_path):
        """Deletion records a checkpoint so it can be undone via /rewind."""
        ctx = self._make_ctx(tmp_path)
        target = tmp_path / "checkpoint_me.txt"
        target.write_text("content to be deleted\n")

        _delete(ctx, {"path": "checkpoint_me.txt"})

        # Checkpoint should be recorded on the workspace
        assert len(ctx.workspace.checkpoints) == 1
        cp = ctx.workspace.checkpoints[0]
        assert cp.path == target
        assert cp.previous == b"content to be deleted\n"

        # File should be gone
        assert not target.exists()
        # Read state should be cleared
        assert target not in ctx.workspace.read_state

    def test_delete_relative_path(self, tmp_path):
        """Deleting with a relative path works."""
        ctx = self._make_ctx(tmp_path)
        target = tmp_path / "relative_test.txt"
        target.write_text("relative path test\n")

        result = _delete(ctx, {"path": "relative_test.txt"})

        assert not target.exists()
        assert "Deleted relative_test.txt" in result.text

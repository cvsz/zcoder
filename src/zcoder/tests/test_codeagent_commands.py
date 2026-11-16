"""Unit tests for zcoder.agent.codeagent.commands - slash command registry and dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zcoder.agent.codeagent.commands import (
    _ALIASES,
    Command,
    CommandResult,
    command,
    command_names,
    dispatch,
    list_commands,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_defaults(self):
        result = CommandResult()
        assert result.output == ""
        assert result.action is None
        assert result.prompt is None
        assert result.is_error is False

    def test_full(self):
        result = CommandResult(
            output="done",
            action="clear",
            prompt="next prompt",
            is_error=True,
        )
        assert result.output == "done"
        assert result.action == "clear"
        assert result.prompt == "next prompt"
        assert result.is_error is True


class TestCommand:
    """Tests for Command dataclass."""

    def test_create(self):
        async def run(agent, arg):
            return CommandResult("ok")

        cmd = Command(name="test", help="test help", run=run, usage="<arg>")
        assert cmd.name == "test"
        assert cmd.help == "test help"
        assert cmd.usage == "<arg>"
        assert cmd.run is run


class TestCommandRegistry:
    """Tests for command registration and listing."""

    def test_list_commands_has_expected_commands(self):
        names = {c.name for c in list_commands()}
        expected = {"help", "clear", "compact", "mode", "plan", "model", "cost", "exit"}
        assert expected.issubset(names)

    def test_command_names_start_with_slash(self):
        names = command_names()
        assert all(n.startswith("/") for n in names)
        assert "/help" in names
        assert "/exit" in names

    def test_aliases(self):
        assert _ALIASES["new"] == "clear"
        assert _ALIASES["reset"] == "clear"
        assert _ALIASES["quit"] == "exit"
        assert _ALIASES["q"] == "exit"
        assert _ALIASES["h"] == "help"
        assert _ALIASES["?"] == "help"
        assert _ALIASES["rewind"] == "undo"
        # undo itself is not an alias (it's a registered command)
        assert "undo" not in _ALIASES

    def test_register_new_command(self):
        async def my_run(agent, arg):
            return CommandResult("my output")

        command("testcmd", "Test command", usage="<arg>")(my_run)
        try:
            names = {c.name for c in list_commands()}
            assert "testcmd" in names
        finally:
            # Clean up the global registry so other tests are unaffected.
            from zcoder.agent.codeagent.commands import _REGISTRY

            _REGISTRY.pop("testcmd", None)


class TestDispatch:
    """Tests for dispatch() function."""

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        agent = MagicMock()
        result = await dispatch(agent, "/unknown_command_xyz")
        assert result.is_error is True
        assert "Unknown command" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_uses_alias(self):
        agent = MagicMock()
        agent.clear = MagicMock()
        result = await dispatch(agent, "/new")
        assert result.action == "clear"
        agent.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_command(self):
        agent = MagicMock()
        result = await dispatch(agent, "/help")
        assert result.is_error is False
        assert "/help" in result.output
        assert "/exit" in result.output

    @pytest.mark.asyncio
    async def test_exit_command(self):
        agent = MagicMock()
        result = await dispatch(agent, "/exit")
        assert result.action == "exit"

    @pytest.mark.asyncio
    async def test_clear_command(self):
        agent = MagicMock()
        agent.clear = MagicMock()
        result = await dispatch(agent, "/clear")
        assert result.action == "clear"
        assert result.output == "New conversation started."
        agent.clear.assert_called_once()

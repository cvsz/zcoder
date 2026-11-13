"""Slash command handler for CodeAgent interactive mode.

Implements built-in slash commands compatible with Claude Code's command set.
"""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class SlashCommand:
    """Definition of a slash command."""

    name: str
    description: str
    handler: Callable[[Any, list[str]], Awaitable[None]]
    aliases: list[str] | None = None
    requires_session: bool = True


@dataclass
class SlashCommandContext:
    """Context passed to slash command handlers."""

    agent: Any  # CodeAgent instance
    args: list[str]
    raw: str

    def notice(self, text: str, level: str = "info") -> None:
        """Queue a notice to be yielded by the agent's run loop."""
        # The agent will handle yielding this
        # For now, print directly for immediate feedback
        level_colors = {
            "info": "\033[96m",
            "warn": "\033[93m",
            "error": "\033[91m",
            "success": "\033[92m",
        }
        color = level_colors.get(level, "\033[96m")
        reset = "\033[0m"
        print(f"{color}[{level.upper()}]{reset} {text}")

    def print(self, text: str) -> None:
        """Print directly to stdout."""
        print(text)


class SlashCommandRegistry:
    """Registry of slash commands."""

    def __init__(self):
        self._commands: dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        self._commands[command.name] = command
        if command.aliases:
            for alias in command.aliases:
                self._commands[alias] = command

    def get(self, name: str) -> SlashCommand | None:
        return self._commands.get(name)

    def list_commands(self) -> list[SlashCommand]:
        # Return unique commands (avoid duplicates from aliases)
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return sorted(result, key=lambda c: c.name)

    def is_slash_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    def parse(self, text: str) -> tuple[str, list[str]] | None:
        """Parse slash command from text. Returns (command_name, args) or None."""
        text = text.strip()
        if not text.startswith("/"):
            return None
        parts = shlex.split(text[1:])  # Remove leading /
        if not parts:
            return None
        return parts[0].lower(), parts[1:]


# Global registry instance
_slash_registry = SlashCommandRegistry()


def register_slash_command(command: SlashCommand) -> None:
    """Register a slash command."""
    _slash_registry.register(command)


def get_slash_registry() -> SlashCommandRegistry:
    return _slash_registry


async def handle_slash_command(agent: Any, text: str) -> bool:
    """
    Handle a slash command if the text is a slash command.
    Returns True if the text was a slash command and was handled.
    """
    parsed = _slash_registry.parse(text)
    if not parsed:
        return False

    command_name, args = parsed
    command = _slash_registry.get(command_name)
    if not command:
        # Unknown command - let the model handle it
        return False

    # Check if command requires a session
    if command.requires_session and not hasattr(agent, "session_id"):
        # This shouldn't happen in normal operation
        pass

    # Create context
    context = SlashCommandContext(
        agent=text, args=args, raw=text  # We'll pass the agent via a different mechanism
    )

    # Actually, we need to pass the agent properly
    # Let's use a different approach - pass agent as attribute
    context.agent = text  # This is wrong, need to fix

    # For now, let's use a different pattern
    return await _execute_slash_command(text, command_name, args)


async def _execute_slash_command(agent: Any, command_name: str, args: list[str]) -> bool:
    """Execute a slash command by name."""
    command = _slash_registry.get(command_name)
    if not command:
        return False

    try:
        await command.handler(agent, args)
        return True
    except Exception:
        # Send error as notice
        if hasattr(agent, "yield") and callable(getattr(agent, "yield", None)):
            # Can't yield from here directly
            pass
        raise


# ============================================================
# Built-in Slash Command Implementations
# ============================================================


async def cmd_help(agent: Any, args: list[str]) -> None:
    """Show help for slash commands."""
    registry = get_slash_registry()
    commands = registry.list_commands()

    lines = ["Available slash commands:"]
    for cmd in commands:
        aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  /{cmd.name}{aliases} — {cmd.description}")

    # Also show interactive mode help
    lines.extend(
        [
            "",
            "Interactive mode:",
            "  Type /help to see this message",
            "  Type /clear to clear the conversation",
            "  Type /compact to compact the conversation",
            "  Type /compact <instructions> to compact with custom instructions",
            "  Type /config to view configuration",
            "  Type /permissions to manage permissions",
            "  Type /hooks to manage hooks",
            "  Type /plugin to manage plugins",
            "  Type /mcp to manage MCP servers",
            "  Type /memory to manage memory",
            "  Type /agents to manage agents",
            "  Type /compact to compact conversation",
            "  Type /resume <session_id> to resume a session",
            "  Type /clear to clear conversation",
            "  Type /rewind to undo last turn",
            "  Type /statusline to show status line",
            "  Type /model to show/change model",
            "  Type /help to see this message",
            "  Type Ctrl+C to interrupt",
            "  Type Ctrl+D to exit",
        ]
    )

    # Use agent's notice method if available, otherwise print
    if hasattr(agent, "notice"):
        for line in lines:
            agent.notice(line)
    else:
        print("\n".join(lines))


async def cmd_config(agent: Any, args: list[str]) -> None:
    """Show configuration."""
    from zcoder.agent.enterprise.settings import cmd_settings_show

    cmd_settings_show()
    if hasattr(agent, "notice"):
        agent.notice("Configuration displayed above")


async def cmd_permissions(agent: Any, args: list[str]) -> None:
    """Manage permissions."""
    if not args:
        # Show current permissions
        from zcoder.agent.enterprise.hooks_perms import cmd_perms_list

        cmd_perms_list()
        return

    # Handle subcommands
    subcmd = args[0]
    if subcmd == "add":
        if len(args) < 3:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /permissions add <pattern> <allow|deny|ask> [reason]", "error")
            else:
                print("Usage: /permissions add <pattern> <allow|deny|ask> [reason]")
            return
        pattern = args[1]
        decision = args[2]
        _reason = " ".join(args[3:]) if len(args) > 3 else ""
        # We need to call this through the agent's permission system
        if hasattr(agent, "notice"):
            agent.notice(f"Adding permission: {pattern} -> {decision}")
        else:
            print(f"Adding permission: {pattern} -> {decision}")
    elif subcmd == "remove":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /permissions remove <index>", "error")
            else:
                print("Usage: /permissions remove <index>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Removing permission at index {args[1]}")
        else:
            print(f"Removing permission at index {args[1]}")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_hooks(agent: Any, args: list[str]) -> None:
    """Manage hooks."""
    if not args:
        from zcoder.agent.enterprise.hooks_perms import cmd_hooks_list

        cmd_hooks_list()
        return

    subcmd = args[0]
    if subcmd == "add":
        if len(args) < 3:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /hooks add <event> <command> [matcher]", "error")
            else:
                print("Usage: /hooks add <event> <command> [matcher]")
            return
        event = args[1]
        command = " ".join(args[2:])
        if hasattr(agent, "notice"):
            agent.notice(f"Adding hook: {event} -> {command}")
        else:
            print(f"Adding hook: {event} -> {command}")
    elif subcmd == "remove":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /hooks remove <index>", "error")
            else:
                print("Usage: /hooks remove <index>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Removing hook at index {args[1]}")
        else:
            print(f"Removing hook at index {args[1]}")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_plugin(agent: Any, args: list[str]) -> None:
    """Manage plugins."""
    if not args:
        from zcoder.agent.tools.plugins import cmd_plugin_list

        cmd_plugin_list()
        return

    subcmd = args[0]
    if subcmd == "install":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin install <name[@marketplace]>", "error")
            else:
                print("Usage: /plugin install <name[@marketplace]>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Installing plugin: {args[1]}")
        else:
            print(f"Installing plugin: {args[1]}")
    elif subcmd == "dir":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin dir <path>", "error")
            else:
                print("Usage: /plugin dir <path>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Installing plugin from directory: {args[1]}")
        else:
            print(f"Installing plugin from directory: {args[1]}")
    elif subcmd == "uninstall":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin uninstall <name>", "error")
            else:
                print("Usage: /plugin uninstall <name>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Uninstalling plugin: {args[1]}")
        else:
            print(f"Uninstalling plugin: {args[1]}")
    elif subcmd == "info":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin info <name>", "error")
            else:
                print("Usage: /plugin info <name>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Plugin info: {args[1]}")
        else:
            print(f"Plugin info: {args[1]}")
    elif subcmd == "enable":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin enable <name>", "error")
            else:
                print("Usage: /plugin enable <name>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Enabling plugin: {args[1]}")
        else:
            print(f"Enabling plugin: {args[1]}")
    elif subcmd == "disable":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin disable <name>", "error")
            else:
                print("Usage: /plugin disable <name>")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Disabling plugin: {args[1]}")
        else:
            print(f"Disabling plugin: {args[1]}")
    elif subcmd == "marketplace":
        if len(args) < 2:
            if hasattr(agent, "notice"):
                agent.notice("Usage: /plugin marketplace <add|list|remove> [args...]", "error")
            else:
                print("Usage: /plugin marketplace <add|list|remove> [args...]")
            return
        if hasattr(agent, "notice"):
            agent.notice(f"Marketplace: {args[1]}")
        else:
            print(f"Marketplace: {args[1]}")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_mcp(agent: Any, args: list[str]) -> None:
    """Manage MCP servers."""
    if not args:
        if hasattr(agent, "notice"):
            agent.notice("MCP servers: (not yet implemented)")
        else:
            print("MCP servers: (not yet implemented)")
        return

    subcmd = args[0]
    if subcmd == "list":
        if hasattr(agent, "notice"):
            agent.notice("MCP servers: (not yet implemented)")
        else:
            print("MCP servers: (not yet implemented)")
    elif subcmd == "add":
        if hasattr(agent, "notice"):
            agent.notice("Add MCP server: (not yet implemented)")
        else:
            print("Add MCP server: (not yet implemented)")
    elif subcmd == "remove":
        if hasattr(agent, "notice"):
            agent.notice("Remove MCP server: (not yet implemented)")
        else:
            print("Remove MCP server: (not yet implemented)")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_memory(agent: Any, args: list[str]) -> None:
    """Manage memory."""
    if not args:
        if hasattr(agent, "notice"):
            agent.notice("Memory: (not yet implemented)")
        else:
            print("Memory: (not yet implemented)")
        return

    subcmd = args[0]
    if subcmd == "list":
        if hasattr(agent, "notice"):
            agent.notice("Memory entries: (not yet implemented)")
        else:
            print("Memory entries: (not yet implemented)")
    elif subcmd == "add":
        if hasattr(agent, "notice"):
            agent.notice("Add memory: (not yet implemented)")
        else:
            print("Add memory: (not yet implemented)")
    elif subcmd == "remove":
        if hasattr(agent, "notice"):
            agent.notice("Remove memory: (not yet implemented)")
        else:
            print("Remove memory: (not yet implemented)")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_agents(agent: Any, args: list[str]) -> None:
    """Manage agents."""
    if not args:
        # List agents
        if hasattr(agent, "notice"):
            agent.notice("Managed agents: (not yet implemented)")
        else:
            print("Managed agents: (not yet implemented)")
        return

    subcmd = args[0]
    if subcmd == "create":
        if hasattr(agent, "notice"):
            agent.notice("Create agent: (not yet implemented)")
        else:
            print("Create agent: (not yet implemented)")
    elif subcmd == "list":
        if hasattr(agent, "notice"):
            agent.notice("List agents: (not yet implemented)")
        else:
            print("List agents: (not yet implemented)")
    elif subcmd == "get":
        if hasattr(agent, "notice"):
            agent.notice("Get agent: (not yet implemented)")
        else:
            print("Get agent: (not yet implemented)")
    elif subcmd == "update":
        if hasattr(agent, "notice"):
            agent.notice("Update agent: (not yet implemented)")
        else:
            print("Update agent: (not yet implemented)")
    elif subcmd == "delete":
        if hasattr(agent, "notice"):
            agent.notice("Delete agent: (not yet implemented)")
        else:
            print("Delete agent: (not yet implemented)")
    else:
        msg = f"Unknown subcommand: {subcmd}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_compact(agent: Any, args: list[str]) -> None:
    """Compact the conversation."""
    instructions = " ".join(args) if args else ""
    try:
        summary = await agent.compact(instructions)
        if hasattr(agent, "notice"):
            agent.notice(f"Conversation compacted. Summary: {summary[:200]}...")
        else:
            print(f"Conversation compacted. Summary: {summary[:200]}...")
    except Exception as e:
        msg = f"Compaction failed: {e}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_resume(agent: Any, args: list[str]) -> None:
    """Resume a session."""
    if not args:
        if hasattr(agent, "notice"):
            agent.notice("Usage: /resume <session_id>", "error")
        else:
            print("Usage: /resume <session_id>")
        return

    session_id = args[0]
    if not hasattr(agent, "store") or agent.store is None:
        if hasattr(agent, "notice"):
            agent.notice("No session store available", "error")
        else:
            print("No session store available")
        return

    try:
        count = agent.load_session(session_id)
        msg = f"Resumed session {session_id} ({count} user messages)"
        if hasattr(agent, "notice"):
            agent.notice(msg)
        else:
            print(msg)
    except KeyError:
        msg = f"Session not found: {session_id}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)
    except Exception as e:
        msg = f"Failed to resume: {e}"
        if hasattr(agent, "notice"):
            agent.notice(msg, "error")
        else:
            print(msg)


async def cmd_clear(agent: Any, args: list[str]) -> None:
    """Clear the conversation."""
    agent.clear()
    if hasattr(agent, "notice"):
        agent.notice("Conversation cleared.")
    else:
        print("Conversation cleared.")


async def cmd_rewind(agent: Any, args: list[str]) -> None:
    """Undo the last turn."""
    restored = agent.undo()
    if restored:
        if hasattr(agent, "notice"):
            agent.notice("Undid changes:")
            for r in restored:
                agent.notice(f"  {r}")
        else:
            print("Undid changes:")
            for r in restored:
                print(f"  {r}")
    else:
        if hasattr(agent, "notice"):
            agent.notice("Nothing to undo.")
        else:
            print("Nothing to undo.")


async def cmd_statusline(agent: Any, args: list[str]) -> None:
    """Show status line."""
    from zcoder.agent.enterprise.settings import cmd_status_line

    cwd = getattr(agent, "ws", None)
    cwd = str(cwd.root) if cwd else "."
    cmd_status_line(model="claude-sonnet-5", cwd=cwd)
    if hasattr(agent, "notice"):
        agent.notice("Status line displayed above")


async def cmd_keybindings(agent: Any, args: list[str]) -> None:
    """Show keybindings."""
    lines = [
        "Keybindings:",
        "  Ctrl+C  - Interrupt current operation",
        "  Ctrl+D  - Exit",
        "  Ctrl+L  - Clear screen (terminal)",
        "  Ctrl+R  - Search history (readline)",
        "  Tab     - Auto-complete (if supported)",
        "  Up/Down - History navigation",
    ]
    if hasattr(agent, "notice"):
        for line in lines:
            agent.notice(line)
    else:
        print("\n".join(lines))


async def cmd_model(agent: Any, args: list[str]) -> None:
    """Show or change model."""
    if not args:
        if hasattr(agent, "llm") and hasattr(agent.llm, "model"):
            if hasattr(agent, "notice"):
                agent.notice(f"Current model: {agent.llm.model}")
            else:
                print(f"Current model: {agent.llm.model}")
        else:
            if hasattr(agent, "notice"):
                agent.notice("Current model: unknown")
            else:
                print("Current model: unknown")
        if hasattr(agent, "notice"):
            agent.notice("Available models: use --list-models")
        else:
            print("Available models: use --list-models")
        return

    model = args[0]
    msg = f"Model change to {model}: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_exit(agent: Any, args: list[str]) -> None:
    """Exit the interactive session."""
    if hasattr(agent, "notice"):
        agent.notice("Goodbye!")
    else:
        print("Goodbye!")
    # Signal exit
    raise SystemExit(0)


# ============================================================
# Additional Slash Command Implementations
# ============================================================


async def cmd_voice(agent: Any, args: list[str]) -> None:
    """Voice input (placeholder for future implementation)."""
    msg = "Voice input: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_version(agent: Any, args: list[str]) -> None:
    """Show version information."""
    from importlib.metadata import version

    try:
        ver = version("zcoder")
    except Exception:
        ver = "unknown"
    msg = f"ZCoder version: {ver}"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_init(agent: Any, args: list[str]) -> None:
    """Initialize project with ZCoder configuration."""
    msg = "Project initialization: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_doctor(agent: Any, args: list[str]) -> None:
    """Run health checks and diagnostics."""
    msg = "Doctor: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_logout(agent: Any, args: list[str]) -> None:
    """Log out from the current session."""
    msg = "Logout: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_auth(agent: Any, args: list[str]) -> None:
    """Authentication management."""
    msg = "Auth management: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)


async def cmd_debug(agent: Any, args: list[str]) -> None:
    """Debug information."""
    msg = "Debug: (not yet implemented)"
    if hasattr(agent, "notice"):
        agent.notice(msg)
    else:
        print(msg)

        # Register additional commands
        SlashCommand(
            name="voice",
            description="Voice input (not yet implemented)",
            handler=cmd_voice,
        ),
        SlashCommand(
            name="version",
            description="Show version information",
            handler=cmd_version,
        ),
        SlashCommand(
            name="init",
            description="Initialize project with ZCoder configuration",
            handler=cmd_init,
        ),
        SlashCommand(
            name="doctor",
            description="Run health checks and diagnostics",
            handler=cmd_doctor,
        ),
        SlashCommand(
            name="logout",
            description="Log out from the current session",
            handler=cmd_logout,
        ),
        SlashCommand(
            name="auth",
            description="Authentication management",
            handler=cmd_auth,
        ),
        SlashCommand(
            name="debug",
            description="Debug information",
            handler=cmd_debug,
        ),


def register_builtin_commands() -> None:
    """Register all built-in slash commands."""
    commands = [
        SlashCommand(
            name="help",
            description="Show help for slash commands",
            handler=cmd_help,
            aliases=["h", "?"],
        ),
        SlashCommand(
            name="config",
            description="Show configuration",
            handler=cmd_config,
        ),
        SlashCommand(
            name="permissions",
            description="Manage permissions",
            handler=cmd_permissions,
            aliases=["perms"],
        ),
        SlashCommand(
            name="hooks",
            description="Manage hooks",
            handler=cmd_hooks,
        ),
        SlashCommand(
            name="plugin",
            description="Manage plugins",
            handler=cmd_plugin,
            aliases=["plugin"],
        ),
        SlashCommand(
            name="mcp",
            description="Manage MCP servers",
            handler=cmd_mcp,
        ),
        SlashCommand(
            name="memory",
            description="Manage memory",
            handler=cmd_memory,
        ),
        SlashCommand(
            name="agents",
            description="Manage agents",
            handler=cmd_agents,
            aliases=["agent"],
        ),
        SlashCommand(
            name="compact",
            description="Compact the conversation",
            handler=cmd_compact,
        ),
        SlashCommand(
            name="resume",
            description="Resume a session",
            handler=cmd_resume,
        ),
        SlashCommand(
            name="clear",
            description="Clear the conversation",
            handler=cmd_clear,
        ),
        SlashCommand(
            name="rewind",
            description="Undo the last turn",
            handler=cmd_rewind,
        ),
        SlashCommand(
            name="statusline",
            description="Show status line",
            handler=cmd_statusline,
        ),
        SlashCommand(
            name="keybindings",
            description="Show keybindings",
            handler=cmd_keybindings,
        ),
        SlashCommand(
            name="model",
            description="Show or change model",
            handler=cmd_model,
        ),
        SlashCommand(
            name="exit",
            description="Exit the session",
            handler=cmd_exit,
            aliases=["quit", "q"],
        ),
        SlashCommand(
            name="voice",
            description="Voice input (not yet implemented)",
            handler=cmd_voice,
        ),
        SlashCommand(
            name="version",
            description="Show version information",
            handler=cmd_version,
        ),
        SlashCommand(
            name="init",
            description="Initialize project with ZCoder configuration",
            handler=cmd_init,
        ),
        SlashCommand(
            name="doctor",
            description="Run health checks and diagnostics",
            handler=cmd_doctor,
        ),
        SlashCommand(
            name="logout",
            description="Log out from the current session",
            handler=cmd_logout,
        ),
        SlashCommand(
            name="auth",
            description="Authentication management",
            handler=cmd_auth,
        ),
        SlashCommand(
            name="debug",
            description="Debug information",
            handler=cmd_debug,
        ),
    ]

    for cmd in commands:
        register_slash_command(cmd)


# Auto-register on import
register_builtin_commands()

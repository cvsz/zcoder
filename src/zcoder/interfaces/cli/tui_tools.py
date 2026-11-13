"""Tool execution for TUI with approval dialogs.

This module provides tool execution capabilities for the TUI interface,
integrating with the existing tool functions and approval dialogs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from zcoder.agent.codeagent.events import Decision
from zcoder.agent.codeagent.permissions import PermissionPolicy
from zcoder.agent.codeagent.tools import (
    ToolContext,
    Workspace,
    default_tools,
    preview,
    validate_args,
)
from zcoder.agent.codeagent.workspace import ToolError as WorkspaceToolError


@dataclass
class ToolCall:
    """A tool call request from the model."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool execution."""

    call_id: str
    tool_name: str
    output: str
    is_error: bool
    diff: str | None = None
    decision: str = (
        "auto"  # auto, user_allow, user_allow_session, user_deny, policy_deny, hook_block, invalid_args, exec_error
    )


class TUIToolExecutor:
    """Executes tools for the TUI with approval dialogs."""

    def __init__(
        self,
        tui_app: Any,  # ZCoderTUI instance
        workspace: Workspace,
        hooks: Any = None,  # Hooks instance
        policy: Any = None,  # PermissionPolicy instance
        ask_fn: Callable[[Any], Awaitable[Decision]] | None = None,
        scrub_env: bool = True,
        pass_env: tuple[str, ...] = (),
    ):
        self.tui_app = tui_app
        self.workspace = workspace
        self.hooks = hooks
        self.policy = policy or PermissionPolicy(workspace=workspace)
        self.policy.workspace = workspace
        self.ask_fn = ask_fn

        # Tool context for execution
        self.ctx = ToolContext(
            workspace=workspace,
            scrub_env=scrub_env,
            pass_env=pass_env,
        )

        # Register tools
        self.tools = default_tools()
        self._pending_approval: asyncio.Future | None = None
        self._approval_result: tuple[str, Any] | None = None
        self._approval_future: asyncio.Future[tuple[str, Any]] | None = None

    async def execute_tool(self, call: ToolCall) -> ToolResult:
        """Execute a tool call with approval if needed."""
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=f"Unknown tool '{call.name}'",
                is_error=True,
                decision="unknown_tool",
            )

        # Validate arguments
        try:
            validate_args(tool, call.args)
        except WorkspaceToolError as exc:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=str(exc),
                is_error=True,
                decision="invalid_args",
            )

        # Check if tool requires approval
        verdict = self.policy.check(tool, call.args)
        if verdict.action == "deny":
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=verdict.reason,
                is_error=True,
                decision="policy_deny",
            )

        # Run pre-tool hooks
        if self.hooks:
            pre_result = await self._run_pre_hooks(call.name, call.args)
            if pre_result.blocked:
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    output=pre_result.message or "Blocked by hook",
                    is_error=True,
                    decision="hook_block",
                )

        if verdict.action == "ask":
            # Show approval dialog
            decision = await self._request_approval(call.name, call.args, verdict.reason)
            if decision == "deny":
                return ToolResult(
                    call_id=call.id,
                    tool_name=call.name,
                    output="User denied the tool call.",
                    is_error=True,
                    decision="user_deny",
                )
            elif decision == "allow_session":
                # Remember this tool as allowed for the session
                self.policy.remember(tool, call.args)
            # else: allow (single use)

        # Execute the tool
        try:
            out = await asyncio.to_thread(tool.func, self.ctx, call.args)
        except Exception as e:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=f"{type(e).__name__}: {e}",
                is_error=True,
                decision="exec_error",
            )

        # Run post-tool hooks
        if self.hooks:
            await self._run_post_hooks(call.name, call.args, out.text, False)

        return ToolResult(
            call_id=call.id,
            tool_name=call.name,
            output=out.text,
            is_error=False,
            diff=out.diff,
            decision="user_allow" if verdict.action == "ask" else "auto",
        )

    async def _run_pre_hooks(self, tool_name: str, args: dict) -> Any:
        """Run pre-tool hooks."""
        if not self.hooks:
            return type("obj", (object,), {"blocked": False})()
        return await self.hooks.pre_tool(tool_name, args)

    async def _run_post_hooks(self, tool_name: str, args: dict, output: str, is_error: bool) -> None:
        """Run post-tool hooks."""
        if self.hooks:
            await self.hooks.post_tool(tool_name, args, output, is_error)

    async def _request_approval(self, tool_name: str, args: dict, reason: str) -> str:
        """Show approval dialog and wait for user decision."""
        # Create preview for the dialog
        tool = self.tools[tool_name]
        summary, diff = preview(self.ctx, tool, args)

        # Show dialog in TUI
        self._approval_future = asyncio.Future()

        def show_dialog():
            # This will be called from the main thread
            self.tui_app.call_from_thread(self._show_approval_dialog, tool_name, args, summary, diff, reason)

        # Show dialog in main thread
        self.tui_app.call_from_thread(show_dialog)

        # Wait for user decision
        decision, _ = await self._approval_future
        return decision

    def _show_approval_dialog(self, tool_name: str, args: dict, summary: str, diff: str | None, reason: str):
        """Show approval dialog in TUI."""
        self._approval_future = asyncio.Future()
        self.tui_app._show_approval_dialog(
            tool_name=tool_name, args=args, summary=summary, diff=diff or "", reason=reason
        )

    def _resolve_approval(self, decision: str):
        """Resolve the approval future with user decision."""
        if self._approval_future is not None and not self._approval_future.done():
            self._approval_future.set_result((decision, None))

    async def execute_tool_call(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
        return await self.execute_tool(call)


# Simplified version for TUI integration
class SimpleTUIToolExecutor:
    """Simplified tool executor for TUI."""

    def __init__(self, tui_app: Any, workspace: Workspace):
        self.tui_app = tui_app
        self.workspace = workspace
        self.tools = default_tools()
        self.ctx = ToolContext(workspace=workspace)

    async def execute_tool(self, call: ToolCall) -> ToolResult:
        """Execute a tool call with TUI approval."""
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=f"Unknown tool '{call.name}'",
                is_error=True,
                decision="unknown_tool",
            )

        # Validate arguments
        try:
            validate_args(tool, call.args)
        except WorkspaceToolError as exc:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=str(exc),
                is_error=True,
                decision="invalid_args",
            )

        # For now, just execute without approval (will add approval later)
        try:
            out = await asyncio.to_thread(tool.func, self.ctx, call.args)
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=out.text,
                is_error=False,
                diff=out.diff,
                decision="auto",
            )
        except Exception as e:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                output=f"{type(e).__name__}: {e}",
                is_error=True,
                decision="exec_error",
            )

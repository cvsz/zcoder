"""Hook event bus for zcoder plugin system.

Manages hook dispatch with tier precedence, blocking semantics,
and deny-rules-hold double-dispatch logic.
"""

import asyncio
import json
import logging
import os
import shlex
import subprocess  # nosec B404 - user/org configured hook commands
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.events import BLOCKING_EVENTS, HookEvent
from zcoder.agent.plugin.loader import LoadedHook
from zcoder.agent.plugin.manager import LoadedPlugin, PluginManager
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)

# Safe environment variables for hooks
_SAFE_ENV = frozenset(("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL"))

# Shell operators that require shell=True
_SHELL_OPS = frozenset("|&;$`><()")
_SHELL_BUILTINS = frozenset({
    "exit", "echo", "cd", "export", "unset", "alias", "unalias",
    "source", "exec", "eval", "printf", "read", "test", "true", "false",
    "type", "jobs", "fg", "bg", "kill", "wait", "trap", "umask", "ulimit",
    "shift", "set", "shopt",
})


@dataclass
class HookContext:
    """Context passed to hooks."""
    event: HookEvent
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    cwd: str = ""
    origin_tier: PluginTier = PluginTier.USER
    provider: str = ""
    approver: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """Result of hook execution."""
    blocked: bool = False
    message: str = ""
    warnings: tuple[str, ...] = ()
    modified_args: dict[str, Any] | None = None
    deny_reason: str | None = None
    continue_past_user_tier: bool = False


class HookBus:
    """Event bus for hook dispatch with tier precedence."""

    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._hook_cache: dict[str, list[tuple[LoadedPlugin, LoadedHook]]] = {}
        self._builtin_hooks: dict[str, list[tuple[PluginTier, Any]]] = {}  # event -> list of (tier, handler)
        self._trace: list[tuple[PluginTier, HookEvent, str]] = []  # For deny-rules-hold

    def register(self, event: HookEvent, handler: Any, tier: PluginTier = PluginTier.BUILTIN) -> None:
        """Register a built-in hook handler.
        
        Built-in hooks run at the specified tier (default BUILTIN).
        """
        event_name = event.value
        if event_name not in self._builtin_hooks:
            self._builtin_hooks[event_name] = []
        self._builtin_hooks[event_name].append((tier, handler))

    def _get_cached_hooks(self, event: str) -> list[tuple[LoadedPlugin, LoadedHook]]:
        """Get hooks for event with caching."""
        if event not in self._hook_cache:
            self._hook_cache[event] = self.plugin_manager.get_hooks_for_event(event)
        return self._hook_cache[event]

    def _get_all_hooks(self, event: str) -> list[tuple[PluginTier, Any]]:
        """Get all hooks (plugin + builtin) for event, sorted by tier."""
        # Get plugin hooks
        plugin_hooks = self._get_cached_hooks(event)
        all_hooks = [(PluginTier.from_string(p.manifest.tier), h) for p, h in plugin_hooks]
        
        # Add builtin hooks
        if event in self._builtin_hooks:
            all_hooks.extend(self._builtin_hooks[event])
        
        # Sort by tier precedence (lower value = higher precedence)
        all_hooks.sort(key=lambda x: x[0].value)
        return all_hooks

    def invalidate_cache(self) -> None:
        """Invalidate hook cache (call after plugin reload)."""
        self._hook_cache.clear()

    async def fire(self, context: HookContext) -> HookResult:
        """Fire hooks for an event with tier precedence and deny-rules-hold."""
        self._trace.clear()
        hooks = self._get_all_hooks(context.event.value)
        if not hooks:
            return HookResult()

        warnings: list[str] = []
        blocked = False
        message = ""
        modified_args = None
        deny_reason = None
        continue_past_user = False

        # First pass: run all hooks in tier order
        for tier, hook in hooks:
            self._trace.append((tier, context.event, "builtin" if tier == PluginTier.BUILTIN else ""))

            try:
                result = await self._run_hook(hook, context, tier)
                if result.blocked:
                    blocked = True
                    message = result.message or "Blocked by hook"
                    deny_reason = result.deny_reason
                    break
                if result.warnings:
                    warnings.extend(result.warnings)
                if result.modified_args:
                    modified_args = result.modified_args
                if result.continue_past_user_tier:
                    continue_past_user = True
            except Exception as e:
                logger.error(f"Hook error: {context.event}: {e}")
                if context.event in BLOCKING_EVENTS:
                    warnings.append(f"Hook error: {e}")

        # Deny-rules-hold: if user-tier plugin rewrote a blocking decision,
        # re-run without user tier and compare
        if blocked and context.event in BLOCKING_EVENTS:
            if self._user_tier_rewrote_blocking():
                org_result = await self._fire_without_user_tier(context)
                if org_result.blocked and org_result.message != message:
                    # Org deny rule holds
                    blocked = True
                    message = org_result.message
                    deny_reason = org_result.deny_reason
                    logger.info(f"Deny rule holds for {context.event}: {deny_reason}")

        return HookResult(
            blocked=blocked,
            message=message,
            warnings=tuple(warnings),
            modified_args=modified_args,
            deny_reason=deny_reason,
            continue_past_user_tier=continue_past_user,
        )

    def _user_tier_rewrote_blocking(self) -> bool:
        """Check if user tier participated in blocking decision."""
        return any(tier == PluginTier.USER for tier, _, _ in self._trace)

    async def _fire_without_user_tier(self, context: HookContext) -> HookResult:
        """Re-run hooks excluding user tier for deny-rules-hold."""
        # Create filtered context
        filtered_context = HookContext(
            event=context.event,
            tool=context.tool,
            args=context.args.copy(),
            session_id=context.session_id,
            cwd=context.cwd,
            origin_tier=context.origin_tier,
            provider=context.provider,
            approver=context.approver,
            extra=context.extra.copy(),
        )

        # Get all hooks excluding user tier
        all_hooks = self._get_all_hooks(context.event.value)
        filtered_hooks = [(tier, hook) for tier, hook in all_hooks if tier != PluginTier.USER]

        warnings: list[str] = []
        blocked = False
        message = ""
        deny_reason = None

        for tier, hook in filtered_hooks:
            try:
                result = await self._run_hook(hook, filtered_context, tier)
                if result.blocked:
                    blocked = True
                    message = result.message or "Blocked by hook"
                    deny_reason = result.deny_reason
                    break
                if result.warnings:
                    warnings.extend(result.warnings)
            except Exception as e:
                logger.error(f"Hook error (org pass): {context.event}: {e}")

        return HookResult(
            blocked=blocked,
            message=message,
            warnings=tuple(warnings),
            deny_reason=deny_reason,
        )

    async def _run_hook(
        self,
        hook: Any,
        context: HookContext,
        tier: PluginTier,
    ) -> HookResult:
        """Run a single hook with timeout and env sanitization.
        
        Args:
            hook: Either a LoadedHook (plugin hook) or a callable (builtin hook)
            context: Hook execution context
            tier: Plugin tier for this hook
        """
        # Build payload
        payload = {
            "event": context.event.value,
            "tool": context.tool,
            "args": context.args,
            "session_id": context.session_id,
            "cwd": context.cwd,
            **context.extra,
        }

        # Check if it's a LoadedHook (plugin hook) or a builtin callable
        from zcoder.agent.plugin.loader import LoadedHook
        is_loaded_hook = isinstance(hook, LoadedHook)

        if is_loaded_hook:
            # Plugin hook: run as subprocess
            cmd = hook.config.command
            first_word = cmd.split()[0] if cmd.split() else ""
            use_shell = any(ch in cmd for ch in _SHELL_OPS) or first_word in _SHELL_BUILTINS

            if use_shell:
                argv: str | list[str] = cmd
            else:
                argv = shlex.split(cmd)

            # Build sanitized environment
            env = {k: os.environ[k] for k in _SAFE_ENV if k in os.environ}
            env.update({
                "ZCODER_HOOK_EVENT": context.event.value,
                "ZCODER_PROJECT_DIR": context.cwd,
            })
            if context.tool:
                env["ZCODER_TOOL_NAME"] = context.tool

            # Run hook as subprocess
            try:
                process = await asyncio.to_thread(
                    subprocess.run,  # nosec B603,B604 - user/org configured hook commands, shell only for shell ops
                    argv,
                    shell=use_shell,
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    cwd=context.cwd,
                    env=env,
                    timeout=hook.config.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return HookResult(
                    blocked=(context.event in BLOCKING_EVENTS),
                    message=f"Hook timed out after {hook.config.timeout}s: {cmd[:80]}",
                    deny_reason="timeout",
                )
            except OSError as e:
                return HookResult(
                    blocked=(context.event in BLOCKING_EVENTS),
                    message=f"Hook failed to start: {e}",
                    deny_reason="exec_error",
                )

            # Process result
            returncode = process.returncode
            stderr = process.stderr.strip()

            # Blocking events: non-zero exit = block
            blocked = (context.event in BLOCKING_EVENTS and returncode != 0)

            if blocked:
                return HookResult(
                    blocked=True,
                    message=stderr or f"Hook exited with {returncode}",
                    deny_reason="hook_blocked",
                )

            # Non-blocking: warnings for non-zero
            warnings = []
            if returncode != 0:
                warnings.append(stderr or f"Hook exited with {returncode}")

            return HookResult(
                blocked=False,
                message="",
                warnings=tuple(warnings),
                modified_args=None,  # Could parse stdout for modified args in future
            )
        else:
            # Builtin hook: call directly as async function
            try:
                if asyncio.iscoroutinefunction(hook):
                    result = await hook(context)
                else:
                    result = hook(context)
                
                if not isinstance(result, HookResult):
                    return HookResult(
                        blocked=False,
                        message="Builtin hook must return HookResult",
                        deny_reason="invalid_result",
                    )
                return result
            except Exception as e:
                logger.error(f"Builtin hook error: {e}")
                return HookResult(
                    blocked=(context.event in BLOCKING_EVENTS),
                    message=f"Builtin hook error: {e}",
                    deny_reason="hook_error",
                )

    # Convenience methods for common events
    async def session_start(self, session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.SESSION_START,
            session_id=session_id,
            cwd=cwd,
        ))

    async def user_prompt_submit(self, prompt: str, session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.USER_PROMPT_SUBMIT,
            session_id=session_id,
            cwd=cwd,
            args={"prompt": prompt},
            extra={"prompt": prompt},
        ))

    async def pre_tool_use(self, tool: str, args: dict[str, Any], session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.PRE_TOOL_USE,
            tool=tool,
            args=args,
            session_id=session_id,
            cwd=cwd,
        ))

    async def post_tool_use(
        self,
        tool: str,
        args: dict[str, Any],
        output: str,
        is_error: bool,
        session_id: str,
        cwd: str,
    ) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.POST_TOOL_USE,
            tool=tool,
            args=args,
            session_id=session_id,
            cwd=cwd,
            extra={"output": output[:4000], "is_error": is_error},
        ))

    async def tool_check(self, tool: str, args: dict[str, Any], session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.TOOL_CHECK,
            tool=tool,
            args=args,
            session_id=session_id,
            cwd=cwd,
        ))

    async def env_get(self, name: str, session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.ENV_GET,
            args={"name": name},
            session_id=session_id,
            cwd=cwd,
        ))

    async def env_set(self, name: str, value: str, session_id: str, cwd: str) -> HookResult:
        return await self.fire(HookContext(
            event=HookEvent.ENV_SET,
            args={"name": name, "value": value},
            session_id=session_id,
            cwd=cwd,
        ))
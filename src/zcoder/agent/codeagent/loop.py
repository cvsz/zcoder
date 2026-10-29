"""CodeAgent — the streaming tool-use loop shared by the TUI and the web GUI."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.audit import AuditLog, summarize_args
from zcoder.agent.codeagent.events import (
    Decision,
    ModeChanged,
    Notice,
    PermissionRequest,
    TextDelta,
    TodoUpdate,
    ToolEnd,
    ToolStart,
    TurnDone,
    Usage,
    UsageUpdate,
)
from zcoder.agent.codeagent.hooks import Hooks
from zcoder.agent.codeagent.llm import LLM, LLMChunk, LLMError, ToolCallRequest
from zcoder.agent.codeagent.memory import build_system_prompt, expand_mentions, load_project_memory
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy
from zcoder.agent.codeagent.sessions import SessionStore, new_session_id
from zcoder.agent.codeagent.tools import Tool, ToolContext, default_tools, preview, truncate, validate_args
from zcoder.agent.codeagent.workspace import ToolError, Workspace

AskFn = Callable[[PermissionRequest], Awaitable[Decision]]
_TAG = "<tool_call>"
_TAG_RX = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


class _TagFilter:
    """Hides Qwen-style ``<tool_call>`` text from the visible stream (fallback for models without native tools)."""

    def __init__(self) -> None:
        self.buf = ""
        self.hidden = ""

    def feed(self, s: str) -> str:
        if self.hidden:
            self.hidden += s
            return ""
        self.buf += s
        i = self.buf.find(_TAG)
        if i >= 0:
            out, self.hidden, self.buf = self.buf[:i], self.buf[i:], ""
            return out
        for k in range(min(len(_TAG) - 1, len(self.buf)), 0, -1):
            if _TAG.startswith(self.buf[-k:]):
                out, self.buf = self.buf[:-k], self.buf[-k:]
                return out
        out, self.buf = self.buf, ""
        return out

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return out


_OVERFLOW = re.compile(r"(?i)(exceed|too (long|large)|larger than|context (length|size|window))")


def looks_like_context_overflow(message: str) -> bool:
    return "HTTP 400" in message and bool(_OVERFLOW.search(message))


def parse_text_tool_calls(text: str) -> list[ToolCallRequest]:
    calls: list[ToolCallRequest] = []
    for n, m in enumerate(_TAG_RX.finditer(text)):
        try:
            obj = json.loads(m.group(1))
            args = obj.get("arguments", obj.get("parameters", {}))
            if isinstance(args, str):
                args = json.loads(args)
            if isinstance(obj.get("name"), str) and isinstance(args, dict):
                calls.append(ToolCallRequest(f"text_call_{n}", obj["name"], args))
        except (ValueError, AttributeError):
            continue
    return calls


class CodeAgent:
    def __init__(
        self,
        llm: LLM,
        workspace: Workspace,
        policy: PermissionPolicy | None = None,
        tools: dict[str, Tool] | None = None,
        store: SessionStore | None = None,
        ask: AskFn | None = None,
        context_window: int = 32768,
        max_steps: int = 40,
        memory: list[tuple[str, str]] | None = None,
        audit: AuditLog | None = None,
        hooks: Hooks | None = None,
        scrub_env: bool = True,
        pass_env: tuple[str, ...] = (),
        retry_delays: tuple[float, ...] = (1.0, 2.0, 4.0),
    ) -> None:
        self.llm, self.ws = llm, workspace
        self.policy = policy or PermissionPolicy(workspace=workspace)
        self.policy.workspace = workspace
        self.tools = tools or default_tools()
        self.ctx = ToolContext(workspace, scrub_env=scrub_env, pass_env=tuple(pass_env))
        self.store, self.ask = store, ask
        self.context_window, self.max_steps = context_window, max_steps
        self.memory = memory if memory is not None else load_project_memory(workspace.root)
        self.messages: list[dict[str, Any]] = []
        self.session_id = new_session_id()
        self.audit = audit or AuditLog(None, self.session_id)
        self.audit.session_id = self.session_id
        self.hooks = hooks or Hooks(None, workspace.root, self.session_id)
        self.hooks.session_id = self.session_id
        self.retry_delays = retry_delays
        self.last_stop = ""
        self.settings: Any = None
        self.usage = Usage()
        self._interrupted = False
        self.running = False

    # --- state -----------------------------------------------------------
    @property
    def todos(self) -> list[dict[str, Any]]:
        return self.ctx.todos

    @property
    def mode(self) -> Mode:
        return self.policy.mode

    def interrupt(self) -> None:
        self._interrupted = True
        self.ctx.cancel.set()

    def clear(self) -> None:
        self.messages.clear()
        self.ctx.todos.clear()
        self.ws.read_state.clear()
        self._set_session(new_session_id())
        self.usage = Usage()

    def load_session(self, session_id: str) -> int:
        if self.store is None:
            raise KeyError(session_id)
        doc = self.store.load(session_id)
        self.messages = list(doc.get("messages", []))
        self._set_session(doc["id"])
        self.ctx.todos.clear()
        self.ws.read_state.clear()
        return sum(m.get("role") == "user" for m in self.messages)

    def _set_session(self, session_id: str) -> None:
        self.session_id = session_id
        self.audit.session_id = session_id
        self.hooks.session_id = session_id

    def _done(self, reason: str) -> TurnDone:
        self.last_stop = reason
        self.audit.record(
            "turn_end",
            stop_reason=reason,
            requests=self.usage.requests,
            prompt_tokens=self.usage.prompt_tokens,
            completion_tokens=self.usage.completion_tokens,
        )
        return TurnDone(reason)

    def undo(self) -> list[str]:
        return self.ws.undo_last_turn()

    def _save(self) -> None:
        if self.store and self.messages:
            try:
                self.store.save(
                    self.session_id,
                    str(self.ws.root),
                    self.messages,
                    {"prompt": self.usage.prompt_tokens, "completion": self.usage.completion_tokens},
                )
            except OSError:
                pass  # persistence must never break a turn

    # --- prompt assembly -------------------------------------------------
    def _wire_messages(self) -> list[dict[str, Any]]:
        system = build_system_prompt(self.ws, self.policy.mode.value, self.memory, list(self.tools))
        return [{"role": "system", "content": system}, *self.messages]

    def estimate_tokens(self) -> int:
        chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in self.messages) + 3000
        return max(int(chars / 3.5), self.usage.last_prompt_tokens)

    # --- compaction ------------------------------------------------------
    def _render_transcript(self, msgs: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for m in msgs:
            role = m.get("role")
            if role == "tool":
                lines.append(f"[tool result] {str(m.get('content', ''))[:500]}")
                continue
            if m.get("content"):
                lines.append(f"{role}: {str(m['content'])[:2000]}")
            for tc in m.get("tool_calls") or []:
                lines.append(f"[tool call] {tc['function']['name']} {tc['function']['arguments'][:300]}")
        return "\n".join(lines)[-24_000:]

    async def compact(self, instructions: str = "") -> str:
        last_user = max((i for i, m in enumerate(self.messages) if m.get("role") == "user"), default=0)
        head, tail = self.messages[:last_user], self.messages[last_user:]
        if not head:
            raise LLMError("Nothing to compact yet.")
        prompt = (
            "Summarize this coding session so work can continue from the summary alone. Include: the user's goals, "
            "decisions made, files created/changed (with paths), commands run and their outcomes, open problems, and "
            "next steps. Be dense and factual." + (f"\nExtra focus: {instructions}" if instructions else "")
        )
        msgs = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": self._render_transcript(head)},
        ]
        summary = ""
        async with aclosing(self.llm.stream(msgs, [])) as stream:
            async for chunk in stream:
                if chunk.kind == "text":
                    summary += chunk.text
        if not summary.strip():
            raise LLMError("The model returned an empty summary.")
        self.messages = [
            {"role": "user", "content": f"[Summary of earlier conversation]\n{summary.strip()}"},
            {"role": "assistant", "content": "Understood. I have the context and will continue from here."},
            *tail,
        ]
        return summary.strip()

    async def _chat(self) -> AsyncGenerator[LLMChunk, None]:
        """One model request, retried with backoff on transient failures that happen before any output."""
        delays = list(self.retry_delays)
        definitions = [t.definition() for t in self.tools.values()]
        attempt = 0
        while True:
            started = False
            try:
                async with aclosing(self.llm.stream(self._wire_messages(), definitions)) as stream:
                    async for chunk in stream:
                        started = True
                        yield chunk
                return
            except LLMError as exc:
                if started or not exc.retryable or not delays or self._interrupted:
                    raise
                attempt += 1
                wait = delays.pop(0)
                self.audit.record("llm_retry", attempt=attempt, wait=wait, message=str(exc)[:200])
                yield LLMChunk(
                    "retry", text=f"Model server not ready ({exc}); retrying in {wait:g}s ({attempt})…"
                )
                await asyncio.sleep(wait)

    # --- the loop --------------------------------------------------------
    async def run(self, text: str) -> AsyncGenerator[Any, None]:
        if self.running:
            yield Notice("The agent is already working. Interrupt it first.", "warn")
            yield self._done("error")
            return
        self.running, self._interrupted = True, False
        self.ctx.cancel.clear()
        self.ws.begin_turn()
        self.audit.record("turn_start", chars=len(text), mode=self.policy.mode.value, model=self.llm.model)
        try:
            prompt, attached = expand_mentions(text, self.ws)
            if attached:
                yield Notice("Attached: " + ", ".join(attached))
            self.messages.append({"role": "user", "content": prompt})
            recent: list[str] = []
            overflow_retried = False
            for _ in range(self.max_steps):
                if self._interrupted:
                    yield self._done("interrupted")
                    return
                if self.estimate_tokens() > int(self.context_window * 0.8) and len(self.messages) > 4:
                    try:
                        await self.compact()
                        yield Notice("Context was nearly full; earlier messages were summarized.", "warn")
                    except LLMError:
                        pass
                visible, calls = "", []
                filt = _TagFilter()
                try:
                    async with aclosing(self._chat()) as stream:
                        async for chunk in stream:
                            if self._interrupted:
                                break
                            if chunk.kind == "retry":
                                yield Notice(chunk.text, "warn")
                            elif chunk.kind == "text":
                                out = filt.feed(chunk.text)
                                if out:
                                    visible += out
                                    yield TextDelta(out)
                            elif chunk.kind == "tool_calls":
                                calls = chunk.tool_calls
                            elif chunk.kind == "usage":
                                self.usage.add(chunk.prompt_tokens, chunk.completion_tokens)
                                yield UsageUpdate(self.usage.prompt_tokens, self.usage.completion_tokens)
                except LLMError as exc:
                    if (
                        looks_like_context_overflow(str(exc))
                        and not overflow_retried
                        and len(self.messages) > 2
                    ):
                        overflow_retried = True
                        try:
                            await self.compact()
                            yield Notice(
                                "The model rejected the prompt as too long; earlier messages were summarized.",
                                "warn",
                            )
                            continue
                        except LLMError:
                            pass
                    self.audit.record("llm_error", message=str(exc)[:300])
                    yield Notice(str(exc), "error")
                    yield self._done("error")
                    return
                overflow_retried = False
                tail = filt.flush()
                if tail:
                    visible += tail
                    yield TextDelta(tail)
                if not calls and filt.hidden:
                    calls = parse_text_tool_calls(filt.hidden)
                if self._interrupted:
                    if visible:
                        self.messages.append({"role": "assistant", "content": visible})
                    yield self._done("interrupted")
                    return
                assistant: dict[str, Any] = {"role": "assistant", "content": visible or None}
                if calls:
                    assistant["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.args)},
                        }
                        for c in calls
                    ]
                self.messages.append(assistant)
                if not calls:
                    yield self._done("end")
                    return
                for idx, call in enumerate(calls):
                    if self._interrupted:
                        for rest in calls[idx:]:
                            self.messages.append(
                                {"role": "tool", "tool_call_id": rest.id, "content": "Interrupted by user."}
                            )
                        yield self._done("interrupted")
                        return
                    yield ToolStart(call.id, call.name, call.args)
                    sig = call.name + json.dumps(call.args, sort_keys=True, default=str)
                    recent = (recent + [sig])[-3:]
                    if len(recent) == 3 and len(set(recent)) == 1:
                        end = ToolEnd(
                            call.id,
                            call.name,
                            "You've made this exact call 3 times in a row. "
                            "Try a different approach or ask the user.",
                            True,
                        )
                    else:
                        before = self.policy.mode
                        end = await self._execute(call)
                        if self.policy.mode != before:
                            yield ModeChanged(self.policy.mode.value)
                    yield end
                    self.messages.append({"role": "tool", "tool_call_id": call.id, "content": end.output})
                    if call.name == "TodoWrite" and not end.is_error:
                        yield TodoUpdate(list(self.ctx.todos))
            yield Notice(f"Stopped after {self.max_steps} steps. Send a message to continue.", "warn")
            yield self._done("max_turns")
        finally:
            self.running = False
            self._save()

    async def _execute(self, call: ToolCallRequest) -> ToolEnd:
        started = time.monotonic()
        raw_args = call.args if isinstance(call.args, dict) else {}

        def done(end: ToolEnd, decision: str) -> ToolEnd:
            self.audit.record(
                "tool",
                tool=call.name,
                args=summarize_args(call.name, raw_args),
                decision=decision,
                error=end.is_error,
                ms=int((time.monotonic() - started) * 1000),
                mode=self.policy.mode.value,
            )
            return end

        def fail(msg: str, decision: str) -> ToolEnd:
            return done(ToolEnd(call.id, call.name, msg, True), decision)

        tool = self.tools.get(call.name)
        if tool is None:
            return fail(f"Unknown tool '{call.name}'. Available: {', '.join(self.tools)}", "unknown_tool")
        try:
            args = validate_args(tool, call.args)
        except ToolError as exc:
            return fail(str(exc), "invalid_args")
        pre = await self.hooks.pre_tool(tool.name, args)
        if pre.blocked:
            return fail(f"Blocked by a PreToolUse hook: {pre.message}", "hook_block")
        verdict = self.policy.check(tool, args)
        if verdict.action == "deny":
            return fail(verdict.reason, "policy_deny")
        decision = "auto"
        if verdict.action == "ask":
            if self.ask is None:
                return fail(
                    "This action needs user approval but no interactive prompt is available.", "no_prompt"
                )
            summary, diff = preview(self.ctx, tool, args)
            try:
                answer = await self.ask(
                    PermissionRequest(call.id, tool.name, args, summary, diff, verdict.reason)
                )
            except Exception as exc:  # a broken prompt (closed socket, crashed UI) must fail closed
                return fail(
                    f"Approval prompt failed ({type(exc).__name__}); the call was not run.", "ask_failed"
                )
            if self._interrupted:
                return fail("Interrupted by user.", "interrupted")
            if answer.behavior == "deny":
                fb = f" User feedback: {answer.feedback}" if answer.feedback else ""
                return fail("The user denied this tool call." + fb, "user_deny")
            decision = "user_allow_session" if answer.behavior == "allow_session" else "user_allow"
            if tool.category == "plan":
                self.policy.mode = Mode.ACCEPT_EDITS if answer.behavior == "allow_session" else Mode.DEFAULT
            elif answer.behavior == "allow_session":
                self.policy.remember(tool, args)
        try:
            out = await asyncio.to_thread(tool.func, self.ctx, args)
        except ToolError as exc:
            return fail(str(exc), decision)
        except Exception as exc:  # unexpected tool bug: report to the model, keep the loop alive
            return fail(f"{type(exc).__name__}: {exc}", decision)
        text = truncate(out.text)
        post = await self.hooks.post_tool(tool.name, args, text, False)
        if post.blocked:
            text += f"\n[PostToolUse hook feedback] {post.message}"
        return done(ToolEnd(call.id, call.name, text, False, out.diff), decision)


def workspace_for(path: str | Path | None = None) -> Workspace:
    return Workspace(Path(path or ".").resolve())

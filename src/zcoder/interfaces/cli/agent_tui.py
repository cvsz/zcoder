"""agent_tui.py — full-screen agentic coding UI (Claude Code-style) built on Textual.

Pure presentation over :class:`zcoder.agent.codeagent.CodeAgent`: streaming transcript, collapsible tool
cards with coloured diffs, an approval dialog for every edit/command, a live task list, permission-mode
cycling (Shift+Tab), ``/`` command and ``@file`` completion, persistent prompt history and session resume.

    python -m zcoder.agent.codeagent            # launches this UI
"""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import aclosing
from typing import Any

try:
    from rich.markdown import Markdown as RichMarkdown
    from rich.text import Text
    from textual import work  # noqa: F401  (kept for subclass use)
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.suggester import Suggester
    from textual.widgets import Button, Collapsible, Footer, Input, Label, Static
except ImportError as exc:  # pragma: no cover - exercised only without textual
    raise ImportError(
        "The agent TUI needs the 'textual' package.\n  Install it with:  pip install 'textual>=0.80.0'"
    ) from exc

from zcoder.agent.codeagent.commands import command_names, dispatch
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
    UsageUpdate,
)
from zcoder.agent.codeagent.loop import CodeAgent
from zcoder.agent.codeagent.memory import git_branch, mention_candidates, zcoder_home
from zcoder.agent.codeagent.permissions import rule_for
from zcoder.agent.codeagent.tools import describe_call

HISTORY_LIMIT = 500
MAX_CARD_LINES = 40
_TODO_ICON = {"pending": "☐", "in_progress": "◐", "completed": "☑"}


# --------------------------------------------------------------------------- pure helpers
def render_diff(diff: str, max_lines: int = 200) -> Text:
    """Colour a unified diff. Returns a Text so file content is never parsed as markup."""
    out = Text()
    lines = diff.splitlines()
    for ln in lines[:max_lines]:
        if ln.startswith(("+++", "---")):
            style = "bold"
        elif ln.startswith("+"):
            style = "green"
        elif ln.startswith("-"):
            style = "red"
        elif ln.startswith("@@"):
            style = "cyan"
        else:
            style = "dim"
        out.append(ln + "\n", style=style)
    if len(lines) > max_lines:
        out.append(f"… {len(lines) - max_lines} more lines\n", style="dim italic")
    return out


def render_output(text: str, max_lines: int = MAX_CARD_LINES) -> Text:
    lines = text.splitlines()
    shown = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        shown += f"\n… +{len(lines) - max_lines} lines"
    return Text(shown or "(no output)")


def status_line(agent: CodeAgent, branch: str, busy: bool) -> str:
    pct = min(99, int(100 * agent.estimate_tokens() / max(agent.context_window, 1)))
    parts = [
        f"⏵⏵ {agent.mode.label}",
        agent.llm.model,
        *([f"⎇ {branch}"] if branch else []),
        f"ctx {pct}%",
        f"↑{agent.usage.prompt_tokens} ↓{agent.usage.completion_tokens}",
    ]
    if busy:
        parts.append("working… (Esc to interrupt)")
    return "  ·  ".join(parts)


class AgentSuggester(Suggester):
    """Inline completion for ``/commands`` and ``@file`` mentions (accept with →)."""

    def __init__(self, agent: CodeAgent) -> None:
        super().__init__(use_cache=False, case_sensitive=True)
        self.agent = agent
        self._files: list[str] = []
        self._stamp = 0.0

    async def _file_list(self) -> list[str]:
        if time.monotonic() - self._stamp > 5:
            self._files = await asyncio.to_thread(mention_candidates, self.agent.ws, "", 5000)
            self._stamp = time.monotonic()
        return self._files

    async def get_suggestion(self, value: str) -> str | None:
        if value.startswith("/") and " " not in value:
            return next((n for n in command_names() if n.startswith(value) and n != value), None)
        m = re.search(r"(?<![\w@])@([\w./\-]*)$", value)
        if m and m.group(1):
            wanted = m.group(1).lower()
            for rel in await self._file_list():
                if rel.lower().startswith(wanted) and rel.lower() != wanted:
                    return value[: m.start()] + "@" + rel
        return None


# --------------------------------------------------------------------------- widgets
class PromptInput(Input):
    """Input with shell-style history (↑/↓) persisted under ~/.zcoder/history."""

    BINDINGS = [Binding("up", "history_prev", show=False), Binding("down", "history_next", show=False)]

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.history: list[str] = []
        self._pos = 0
        self._draft = ""

    def remember(self, text: str) -> None:
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
            del self.history[:-HISTORY_LIMIT]
        self._pos = len(self.history)

    def action_history_prev(self) -> None:
        if not self.history or self._pos == 0:
            return
        if self._pos == len(self.history):
            self._draft = self.value
        self._pos -= 1
        self.value = self.history[self._pos]
        self.cursor_position = len(self.value)

    def action_history_next(self) -> None:
        if self._pos >= len(self.history):
            return
        self._pos += 1
        self.value = self._draft if self._pos == len(self.history) else self.history[self._pos]
        self.cursor_position = len(self.value)


class AssistantMessage(Static):
    """Streams markdown; repaints are throttled so fast token streams don't flood the terminal."""

    def __init__(self) -> None:
        super().__init__("", classes="assistant")
        self.text = ""
        self._last = 0.0

    def append(self, chunk: str) -> None:
        self.text += chunk
        now = time.monotonic()
        if now - self._last > 0.07:
            self.paint()

    def paint(self) -> None:
        self._last = time.monotonic()
        self.update(RichMarkdown(self.text) if self.text.strip() else "")


class ToolCard(Collapsible):
    def __init__(self, call: ToolStart) -> None:
        self.call = call
        self.body = Static("running…", classes="tool-body")
        super().__init__(self.body, title=self._heading("⏺"), collapsed=True, classes="tool-card")

    def _heading(self, mark: str) -> str:
        return f"{mark} {self.call.name}  {describe_call(self.call.name, self.call.args)}".rstrip()

    def finish(self, end: ToolEnd) -> None:
        self.title = self._heading("✗" if end.is_error else "✓")
        if end.is_error:
            self.add_class("error")
        if end.diff:
            self.body.update(render_diff(end.diff))
        else:
            self.body.update(render_output(end.output))
        self.collapsed = not (end.is_error or end.diff)


class PermissionScreen(ModalScreen[Decision]):
    """Approval dialog shown before any edit or command runs."""

    BINDINGS = [
        Binding("y", "choose('allow')", "Yes"),
        Binding("a", "choose('allow_session')", "Always"),
        Binding("n", "choose('deny')", "No"),
        Binding("f", "feedback", "No + tell me why"),
        Binding("escape", "choose('deny')", "No", show=False),
    ]

    def __init__(self, request: PermissionRequest, session_rule: str | None) -> None:
        super().__init__()
        self.request = request
        self.session_rule = session_rule
        self.is_plan = request.tool == "ExitPlanMode"

    def compose(self) -> ComposeResult:
        r = self.request
        with Vertical(id="dialog"):
            yield Label(
                ("Ready to code?" if self.is_plan else f"Allow {r.tool}?")
                + (f"  ({r.reason})" if r.reason else ""),
                id="dlg-title",
            )
            yield Static(Text(r.summary if not self.is_plan else "Review the plan below"), id="dlg-summary")
            if r.diff:
                with VerticalScroll(id="dlg-diff"):
                    yield Static(Text(r.diff) if self.is_plan else render_diff(r.diff))
            with Horizontal(id="dlg-buttons"):
                yield Button(
                    "Yes, auto-accept edits [a]" if self.is_plan else "Yes [y]",
                    id="btn-allow_session" if self.is_plan else "btn-allow",
                    variant="success",
                )
                if self.is_plan:
                    yield Button("Yes, ask before edits [y]", id="btn-allow")
                elif self.session_rule:
                    yield Button(f"Always: {self.session_rule} [a]", id="btn-allow_session")
                yield Button("No [n]", id="btn-deny", variant="error")
            yield Input(placeholder="Tell the agent what to do instead, then press Enter", id="dlg-feedback")

    def on_mount(self) -> None:
        self.query_one("#dlg-feedback").display = False
        self.query_one("#dlg-buttons Button", Button).focus()

    def action_choose(self, behavior: str) -> None:
        if behavior == "allow_session" and not (self.is_plan or self.session_rule):
            return
        self.dismiss(Decision(behavior))

    def action_feedback(self) -> None:
        box = self.query_one("#dlg-feedback", Input)
        box.display = True
        box.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(Decision("deny", event.value.strip()))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(Decision((event.button.id or "btn-deny").removeprefix("btn-")))


# --------------------------------------------------------------------------- app
class AgentTUI(App):
    TITLE = "ZCoder"
    SUB_TITLE = "agentic coding assistant"

    CSS = """
    #transcript { height: 1fr; padding: 0 2; }
    .welcome { border: round $primary; padding: 1 2; margin: 1 0; height: auto; color: $text-muted; }
    .user { margin: 1 0 0 0; color: $accent; text-style: bold; }
    .assistant { margin: 1 0 0 0; }
    .notice { margin: 1 0 0 0; color: $warning; }
    .notice.error { color: $error; }
    .notice.info { color: $text-muted; }
    .tool-card { margin: 1 0 0 0; border: none; padding: 0; }
    .tool-card.error { color: $error; }
    .tool-body { padding: 0 2; }
    #todos { height: auto; max-height: 9; padding: 0 2; border-top: solid $primary-darken-2; display: none; }
    #status { height: 1; padding: 0 2; color: $text-muted; background: $boost; }
    #prompt { border: round $primary; margin: 0 1; }
    PermissionScreen { align: center middle; }
    #dialog { width: 90%; max-width: 120; height: auto; max-height: 90%; border: thick $warning; background: $surface; padding: 1 2; }
    #dlg-title { text-style: bold; color: $warning; }
    #dlg-summary { margin: 1 0; }
    #dlg-diff { max-height: 24; border: round $primary-darken-2; margin-bottom: 1; }
    #dlg-buttons { height: auto; }
    #dlg-buttons Button { margin-right: 2; }
    """

    BINDINGS = [
        Binding("shift+tab", "cycle_mode", "Mode", priority=True),
        Binding("escape", "interrupt", "Interrupt"),
        Binding("ctrl+t", "toggle_todos", "Tasks"),
        Binding("ctrl+n", "new_session", "New"),
        Binding("ctrl+q", "quit_app", "Quit"),
    ]

    def __init__(self, agent: CodeAgent) -> None:
        super().__init__()
        self.agent = agent
        self.agent.ask = self._ask
        self.busy = False
        self.branch = ""
        self._assistant: AssistantMessage | None = None
        self._cards: dict[str, ToolCard] = {}
        self._show_todos = True
        self._history_path = zcoder_home() / "history"

    # ----- composition
    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="transcript")
        yield Static("", id="todos")
        yield Static("", id="status")
        yield PromptInput(
            placeholder="Message ZCoder…  (/ for commands · @ to attach a file)",
            id="prompt",
            suggester=AgentSuggester(self.agent),
        )
        yield Footer()

    async def on_mount(self) -> None:
        prompt = self.query_one(PromptInput)
        prompt.history = self._load_history()
        prompt._pos = len(prompt.history)
        prompt.focus()
        self._welcome()
        self.branch = await asyncio.to_thread(git_branch, self.agent.ws.root)
        self._refresh_status()
        if self.agent.messages:
            self._replay()

    @property
    def transcript(self) -> VerticalScroll:
        return self.query_one("#transcript", VerticalScroll)

    def _welcome(self) -> None:
        a = self.agent
        self.transcript.mount(
            Static(
                Text.assemble(
                    ("✳ ZCoder agent\n", "bold"),
                    f"model {a.llm.model}\ndirectory {a.ws.root}\n",
                    "/help commands · @file attach · Shift+Tab permission mode · Esc interrupt · Ctrl+Q quit",
                ),
                classes="welcome",
            )
        )

    # ----- history persistence (best effort)
    def _load_history(self) -> list[str]:
        try:
            return self._history_path.read_text(encoding="utf-8").splitlines()[-HISTORY_LIMIT:]
        except OSError:
            return []

    def _save_history(self, history: list[str]) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text("\n".join(history[-HISTORY_LIMIT:]) + "\n", encoding="utf-8")
            self._history_path.chmod(0o600)
        except OSError:
            pass

    # ----- rendering helpers
    def _scroll(self) -> None:
        self.transcript.scroll_end(animate=False)

    def _say(self, text: str, level: str = "info") -> None:
        self.transcript.mount(Static(Text(text), classes=f"notice {level}"))
        self._scroll()

    def _refresh_status(self) -> None:
        self.query_one("#status", Static).update(status_line(self.agent, self.branch, self.busy))

    def _refresh_todos(self) -> None:
        panel = self.query_one("#todos", Static)
        todos = self.agent.todos
        if not todos or not self._show_todos:
            panel.display = False
            return
        panel.update(Text("\n".join(f"{_TODO_ICON.get(t['status'], '☐')} {t['content']}" for t in todos)))
        panel.display = True

    def _replay(self) -> None:
        """Render a resumed conversation's history."""
        self.transcript.remove_children()
        self._welcome()
        for m in self.agent.messages:
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                self.transcript.mount(
                    Static(Text("❯ " + m["content"].split("\n\n<file path=")[0]), classes="user")
                )
            elif m.get("role") == "assistant":
                if m.get("content"):
                    msg = AssistantMessage()
                    msg.text = str(m["content"])
                    self.transcript.mount(msg)
                    msg.paint()
                for tc in m.get("tool_calls") or []:
                    self.transcript.mount(Static(Text(f"⏺ {tc['function']['name']}"), classes="notice info"))
        self._scroll()

    # ----- permission prompts (called from the agent loop's worker)
    async def _ask(self, req: PermissionRequest) -> Decision:
        tool = self.agent.tools.get(req.tool)
        rule = rule_for(tool, req.args) if tool else None
        self._assistant = None
        return await self.push_screen_wait(PermissionScreen(req, rule))

    # ----- input handling
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "prompt":
            return
        text = event.value.strip()
        if not text:
            return
        if self.busy:
            self._say("The agent is working — press Esc to interrupt, then resend.", "warn")
            return
        prompt = self.query_one(PromptInput)
        prompt.value = ""
        prompt.remember(text)
        self._save_history(prompt.history)
        if text.startswith("/"):
            self.run_worker(self._run_command(text), name="command", exclusive=True)
        else:
            self.run_worker(self._run_turn(text), name="turn", exclusive=True)

    async def _run_command(self, line: str) -> None:
        result = await dispatch(self.agent, line)
        if result.action == "exit":
            self.exit()
            return
        if result.action == "clear":
            await self._reset_view()
        elif result.action == "resumed":
            self._replay()
        if result.output:
            self._say(result.output, "error" if result.is_error else "info")
        if result.action == "prompt" and result.prompt:
            await self._run_turn(result.prompt, display=line)
        self._refresh_todos()
        self._refresh_status()

    async def _reset_view(self) -> None:
        await self.transcript.remove_children()
        self._cards.clear()
        self._assistant = None
        self._welcome()
        self._refresh_todos()

    async def _run_turn(self, text: str, display: str | None = None) -> None:
        self.busy = True
        self._refresh_status()
        self.transcript.mount(Static(Text("❯ " + (display or text)), classes="user"))
        self._assistant = None
        self._scroll()
        try:
            async with aclosing(self.agent.run(text)) as events:
                async for ev in events:
                    self._on_event(ev)
        except Exception as exc:  # keep the UI alive no matter what
            self._say(f"Unexpected error: {type(exc).__name__}: {exc}", "error")
        finally:
            if self._assistant:
                self._assistant.paint()
            self._assistant = None
            self.busy = False
            self.branch = await asyncio.to_thread(git_branch, self.agent.ws.root)
            self._refresh_todos()
            self._refresh_status()
            self._scroll()

    def _on_event(self, ev: Any) -> None:
        if isinstance(ev, TextDelta):
            if self._assistant is None:
                self._assistant = AssistantMessage()
                self.transcript.mount(self._assistant)
            self._assistant.append(ev.text)
        elif isinstance(ev, ToolStart):
            if self._assistant:
                self._assistant.paint()
            self._assistant = None
            card = ToolCard(ev)
            self._cards[ev.id] = card
            self.transcript.mount(card)
        elif isinstance(ev, ToolEnd):
            found = self._cards.get(ev.id)
            if found is not None:
                found.finish(ev)
                del self._cards[ev.id]
        elif isinstance(ev, TodoUpdate):
            self._refresh_todos()
        elif isinstance(ev, UsageUpdate | ModeChanged):
            self._refresh_status()
        elif isinstance(ev, Notice):
            self._say(ev.text, ev.level)
        elif isinstance(ev, TurnDone) and ev.stop_reason == "interrupted":
            self._say("Interrupted.", "warn")
        self._scroll()

    # ----- actions
    def action_cycle_mode(self) -> None:
        mode = self.agent.policy.cycle_mode()
        self._say(f"Permission mode: {mode.label}", "info")
        self._refresh_status()

    def action_interrupt(self) -> None:
        if self.busy:
            self.agent.interrupt()

    def action_toggle_todos(self) -> None:
        self._show_todos = not self._show_todos
        self._refresh_todos()

    async def action_new_session(self) -> None:
        if self.busy:
            self._say("Interrupt the agent first (Esc).", "warn")
            return
        self.agent.clear()
        await self._reset_view()
        self._say("New conversation started.", "info")
        self._refresh_status()

    def action_quit_app(self) -> None:
        self.agent.interrupt()
        self.exit()


def run_agent_tui(agent: CodeAgent) -> None:
    AgentTUI(agent).run()

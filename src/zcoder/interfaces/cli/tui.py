"""
tui.py — Full interactive terminal UI for zcoder, built on Textual.

Launched via `python main.py --tui` (see main.py). This is a second front
end alongside the plain-argparse CLI and the FastAPI web console
(webapp/), reusing the exact same core the other two do:

    llama-server              -> local chat/generation over its OpenAI-
                                  compatible loopback endpoint
    personalities.py          -> PersonalityManager
    skills.py                 -> SkillManager
    main.py                   -> AGENT_SYSTEM_PROMPTS, VERSION

No business logic lives here -- this module is purely presentation, same
principle webapp/backend/server.py documents for itself.

`textual` is an optional dependency (see requirements.txt): importing
this module raises a clear, actionable ImportError if it isn't
installed, rather than an ugly traceback, matching the pattern used by
claude_excel.py / claude_powerpoint.py for their own optional deps.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.events import Key
    from textual.message import Message
    from textual.reactive import reactive
    from textual.widgets import (
        Button,
        Collapsible,
        Footer,
        Header,
        Input,
        Label,
        ProgressBar,
        Select,
        Static,
        Switch,
        TabbedContent,
        TabPane,
        Tree,
    )
except ImportError as e:  # pragma: no cover - exercised only w/o textual installed
    raise ImportError(
        "The --tui flag needs the 'textual' package, which isn't installed.\n"
        "Install it with:  pip install textual>=0.80.0\n"
        "(or: pip install -r requirements.txt, it's an optional extra there)"
    ) from e

from zcoder.agent.personalities import AGENT_SYSTEM_PROMPTS, PersonalityManager
from zcoder.interfaces.cli.streaming import StreamRenderGate
from zcoder.interfaces.cli.tui_tools import ToolCall, ToolResult, TUIToolExecutor
from zcoder.services.skills import SkillManager

DEFAULT_MODEL = "zcoder-7b"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"


@dataclass
class UIHookContext:
    """Context passed to UI hooks."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class UIHookEvent(Message):
    """UI Hook event for extension points."""

    def __init__(self, hook_name: str, context: UIHookContext):
        super().__init__()
        self.hook_name = hook_name
        self.context = context


class ToolProgressUpdate(Message):
    """Tool progress update for display."""

    def __init__(self, tool_name: str, progress: float, message: str = ""):
        super().__init__()
        self.tool_name = tool_name
        self.progress = progress
        self.message = message


class TokenUsageUpdate(Message):
    """Token usage update for display."""

    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        super().__init__()
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class ErrorDisplay(Message):
    """Error display message."""

    def __init__(self, error_type: str, message: str, recoverable: bool = True):
        super().__init__()
        self.error_type = error_type
        self.message = message
        self.recoverable = recoverable


def _local_server_base_url() -> str:
    """Return a loopback-only llama-server URL; never allow hosted egress."""
    base_url = os.getenv("ZCODER_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("ZCODER_BASE_URL must point to a local llama-server on loopback.")
    return base_url


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent a local server response from redirecting inference off-loopback."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _open_local(request, *, timeout: float):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def _local_server_endpoint(path: str) -> str:
    base_url = _local_server_base_url()
    if base_url.endswith("/v1"):
        return f"{base_url}/{path.lstrip('/')}"
    return f"{base_url}/v1/{path.lstrip('/')}"


def _agent_prompts() -> dict:
    return AGENT_SYSTEM_PROMPTS


class ChatMessage(Static):
    """A single rendered turn in the transcript."""

    def __init__(self, role: str, text: str = ""):
        super().__init__(self._format(role, text), markup=False)
        self.role = role
        self.raw_text = text
        self.add_class(f"msg-{role}")

    @staticmethod
    def _format(role: str, text: str) -> str:
        sym = {"user": "$", "assistant": ">", "error": "!", "system": "·"}.get(role, ">")
        return f"{sym} {text}"

    def update_text(self, text: str) -> None:
        self.raw_text = text
        self.update(self._format(self.role, text))


class SessionSidebar(Vertical):
    """Collapsible settings panel: loaded GGUF / personality / agent /
    skill / temperature / streaming toggle. Mirrors webapp/frontend so
    the two front ends stay conceptually in sync."""

    def compose(self) -> ComposeResult:
        model_options = [("Detecting local GGUF…", DEFAULT_MODEL)]
        personality_options = [("none", "")] + [
            (p["name"], p["name"]) for p in PersonalityManager().list_personalities()
        ]
        agent_options = [("none", "")] + [(name, name) for name in _agent_prompts().keys()]
        skill_options = [("none", "")] + [(s["name"], s["name"]) for s in SkillManager().list_skills()]

        yield Label("loaded GGUF model", classes="side-label")
        yield Select(model_options, value=DEFAULT_MODEL, id="model_select", disabled=True)
        yield Label("personality", classes="side-label")
        yield Select(personality_options, value="", id="personality_select")
        yield Label("agent role", classes="side-label")
        yield Select(agent_options, value="", id="agent_select")
        yield Label("skill focus", classes="side-label")
        yield Select(skill_options, value="", id="skill_select")
        yield Label("temperature: 0.3", id="temp_label", classes="side-label")
        yield Input(value="0.3", id="temp_input", placeholder="0.0 - 1.0")
        with Horizontal(classes="stream-row"):
            yield Label("stream", classes="side-label")
            yield Switch(value=True, id="stream_switch")


class ZCoderTUI(App):
    """Interactive chat UI that sends requests only to loopback llama-server."""

    TITLE = "ZCoder"
    SUB_TITLE = "Coding assistant"

    CSS = """
    #main { height: 1fr; width: 1fr; padding: 0 1; }
    #welcome-card {
        width: 72;
        max-width: 100%;
        height: auto;
        margin: 1 0;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #welcome-title { color: $text; text-style: bold; }
    #welcome-meta { color: $text-muted; margin-top: 1; }
    #welcome-hints { color: $text-muted; margin-top: 1; }
    #transcript { height: 1fr; padding: 0 2; }
    #sidebar { height: auto; max-height: 14; padding: 0 1; overflow-y: auto; }
    .side-label { color: $text-muted; text-style: bold; margin-top: 1; }
    .stream-row { height: 3; align: left middle; }
    #session_status { height: 1; color: $text-muted; padding: 0 1; }
    #input_row {
        height: 5;
        min-height: 5;
        margin: 0 0 1 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
    }
    #prompt_input { width: 1fr; border: none; background: transparent; }
    #send_btn { min-width: 10; height: 3; margin: 0 1; }
    .msg-user { color: $accent; margin: 1 0 0 0; }
    .msg-assistant { color: $success; margin: 1 0 0 0; }
    .msg-error { color: $error; margin: 1 0 0 0; }
    .msg-system { color: $text-muted; margin: 1 0 0 0; }
    
    /* Multi-pane layout */
    #content_area { height: 1fr; width: 1fr; }
    #left_pane { width: 30; min-width: 25; max-width: 40; border-right: solid $primary; }
    #main_pane { width: 1fr; }
    #right_pane { width: 35; min-width: 30; max-width: 50; border-left: solid $primary; }
    
    /* Pane headers */
    .pane-header { 
        height: 2; 
        padding: 0 1; 
        background: $surface; 
        border-bottom: solid $primary;
        text-style: bold;
        color: $accent;
    }
    
    /* Session tree */
    #session_tree { height: 1fr; padding: 0 1; }
    
    /* Tool execution panel */
    #tool_progress_panel { height: auto; max-height: 20; padding: 1; }
    .tool-progress-item { 
        height: auto; 
        margin: 1 0; 
        padding: 1; 
        border: round $primary; 
        background: $surface;
    }
    .tool-progress-label { color: $accent; text-style: bold; }
    .tool-progress-bar { height: 1; margin-top: 1; }
    .tool-progress-message { color: $text-muted; margin-top: 1; }
    
    /* Token usage panel */
    #token_usage_panel { height: auto; padding: 1; }
    .token-usage-row { height: 2; align: left middle; }
    .token-usage-label { color: $text-muted; width: 18; }
    .token-usage-value { color: $success; }
    
    /* Status panel */
    #status_panel { height: auto; padding: 1; }
    .status-row { height: 2; align: left middle; }
    .status-label { color: $text-muted; width: 16; }
    .status-value { color: $text; }
    
    /* Model/Provider panel */
    #model_panel { height: auto; padding: 1; }
    .model-info-row { height: 2; align: left middle; }
    .model-info-label { color: $text-muted; width: 14; }
    .model-info-value { color: $text; }
    
    /* Error panel */
    #error_panel { height: auto; padding: 1; display: none; }
    .error-panel.visible { display: block; }
    .error-message { color: $error; margin: 1 0; }
    .error-recoverable { color: $warning; margin-top: 1; }
    
    /* Welcome card */
    #welcome-card {
        width: 72;
        max-width: 100%;
        height: auto;
        margin: 1 0;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #welcome-title { color: $text; text-style: bold; }
    #welcome-meta { color: $text-muted; margin-top: 1; }
    #welcome-hints { color: $text-muted; margin-top: 1; }
    
    /* Transcript */
    #transcript { height: 1fr; padding: 0 2; }
    #sidebar { height: auto; max-height: 14; padding: 0 1; overflow-y: auto; }
    .side-label { color: $text-muted; text-style: bold; margin-top: 1; }
    .stream-row { height: 3; align: left middle; }
    #session_status { height: 1; color: $text-muted; padding: 0 1; }
    #input_row {
        height: 5;
        min-height: 5;
        margin: 0 0 1 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
    }
    #prompt_input { width: 1fr; border: none; background: transparent; }
    #send_btn { min-width: 10; height: 3; margin: 0 1; }
    .msg-user { color: $accent; margin: 1 0 0 0; }
    .msg-assistant { color: $success; margin: 1 0 0 0; }
    .msg-error { color: $error; margin: 1 0 0 0; }
    .msg-system { color: $text-muted; margin: 1 0 0 0; }
    
    /* Approval Dialog */
    #approval_dialog {
        align: center middle;
        width: 80;
        max-width: 90%;
        height: auto;
        padding: 2;
        border: thick $primary;
        background: $surface;
    }
    #approval_title { color: $warning; text-style: bold; margin-bottom: 1; }
    #approval_tool { color: $accent; text-style: bold; }
    #approval_args { color: $text; margin: 1 0; }
    #approval_reason { color: $warning; margin: 1 0; }
    #approval_diff { color: $text-muted; margin: 1 0; }
    #approval_buttons { height: 3; margin-top: 1; }
    .approval_btn { min-width: 12; margin: 0 1; }
    .approval_btn_allow { background: $success; }
    .approval_btn_allow_session { background: $success; }
    .approval_btn_deny { background: $error; }
    .approval_dialog {
        display: none;
    }
    
    /* Tabbed content for right pane */
    #right_tabs { height: 1fr; }
    .tab-pane { height: 1fr; padding: 1; }
    """

    BINDINGS = [
        ("ctrl+n", "new_session", "New session"),
        ("ctrl+o", "toggle_settings", "Settings"),
        ("ctrl+l", "focus_prompt", "Focus prompt"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+t", "toggle_dark", "Toggle theme"),
        ("ctrl+p", "toggle_panes", "Toggle panes"),
    ]

    def __init__(self, api_key: str | None = None):
        super().__init__()
        # Retain the historical constructor signature without using credentials.
        del api_key
        self.history: list = []
        self.working_directory = os.getcwd()
        self.loaded_model: str | None = None
        self.local_server_error: str | None = None
        self._generation_active = False
        self._session_revision = 0
        self._panes_visible = True
        self._tool_progress: dict[str, dict] = {}
        self._token_usage = {"prompt": 0, "completion": 0, "total": 0}
        self._model_info: dict[str, Any] = {}
        self._status_info: dict[str, Any] = {}
        self._error_display: ErrorDisplay | None = None
        self._ui_hooks: dict[str, list[Callable]] = {
            "view_render": [],
            "view_close": [],
            "dialog_open": [],
            "dialog_close": [],
            "panel_register": [],
            "input_focus": [],
            "input_scroll": [],
            "state_change": [],
        }
        try:
            self.local_server_url = _local_server_base_url()
        except ValueError:
            self.local_server_url = "invalid loopback ZCODER_BASE_URL"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Horizontal(id="content_area"):
                # Left pane - Sessions, Files, Tools
                with Vertical(id="left_pane"):
                    yield Label("📂 Sessions & Files", classes="pane-header")
                    yield Tree("Sessions", id="session_tree")
                    yield Static("Tools", classes="pane-header")
                    yield Static("Available tools will appear here", id="tools_list", classes="pane-content")

                # Main pane - Transcript
                with Vertical(id="main_pane"):
                    with Vertical(id="welcome-card"):
                        yield Label("✳  ZCoder", id="welcome-title")
                        yield Static("Your coding assistant", id="welcome-subtitle")
                        yield Static(self._welcome_meta(), id="welcome-meta")
                        yield Static(
                            "Try /help for commands · /status for session details · /model for loaded model",
                            id="welcome-hints",
                        )
                    yield VerticalScroll(id="transcript")

                # Right pane - Tool Progress, Token Usage, Status, Model Info
                with Vertical(id="right_pane"):
                    yield Label("⚙️ Execution & Status", classes="pane-header")
                    with TabbedContent(id="right_tabs"):
                        with TabPane("Tools", id="tab_tools"):
                            yield Label("Tool Execution Progress", classes="pane-header")
                            yield VerticalScroll(id="tool_progress_panel")
                        with TabPane("Tokens", id="tab_tokens"):
                            yield Label("Token Usage", classes="pane-header")
                            yield Vertical(id="token_usage_panel")
                        with TabPane("Status", id="tab_status"):
                            yield Label("Session Status", classes="pane-header")
                            yield Vertical(id="status_panel")
                        with TabPane("Model", id="tab_model"):
                            yield Label("Model Info", classes="pane-header")
                            yield Vertical(id="model_panel")
                        with TabPane("Errors", id="tab_errors"):
                            yield Label("Errors & Warnings", classes="pane-header")
                            yield Vertical(id="error_panel")

            # Settings panel (collapsible)
            with Collapsible(title="Session settings  ·  Ctrl+O", collapsed=True, id="settings_panel"):
                yield SessionSidebar(id="sidebar")

            yield Static(self._status_text(), id="session_status")
            with Horizontal(id="input_row"):
                yield Input(
                    placeholder="Describe a coding task or ask a question…",
                    id="prompt_input",
                    name="prompt_input",
                )
                yield Button("Send", id="send_btn", variant="primary")

        yield Footer()

        # Approval dialog (hidden by default via CSS)
        with Vertical(id="approval_dialog", classes="approval_dialog"):
            yield Label("", id="approval_title")
            yield Label("", id="approval_tool")
            yield Label("", id="approval_args")
            yield Label("", id="approval_reason")
            yield Label("", id="approval_diff")
            with Horizontal(id="approval_buttons"):
                yield Button("Allow", id="btn_allow", variant="success", classes="approval_btn")
                yield Button(
                    "Allow Session", id="btn_allow_session", variant="success", classes="approval_btn"
                )
                yield Button("Deny", id="btn_deny", variant="error", classes="approval_btn")

    def _welcome_meta(self) -> str:
        return f"model: {self._selected_model()}  ·  /model for details\ndirectory: {self._short_directory()}"

    def _short_directory(self) -> str:
        home = os.path.expanduser("~")
        if self.working_directory == home:
            return "~"
        if self.working_directory.startswith(home + os.sep):
            return "~" + self.working_directory[len(home) :]
        return self.working_directory

    def _selected_model(self) -> str:
        return self.loaded_model or DEFAULT_MODEL

    def _status_text(self) -> str:
        if self.local_server_error:
            return f"llama-server unavailable at {self.local_server_url} · check local model service"
        return f"GGUF: {self._selected_model()}  ·  {self._short_directory()}  ·  local inference"

    def on_mount(self) -> None:
        self.query_one("#prompt_input").focus()
        self._load_server_model()

        # Initialize tool executor
        from zcoder.agent.codeagent.workspace import Workspace

        self.tool_executor = TUIToolExecutor(self, Workspace(Path(self.working_directory)))

        # Initialize session tree
        self._init_session_tree()

        # Initialize tools list
        self._init_tools_list()

        # Initialize status and model displays
        self._update_status_display()
        self._update_model_display()
        self._update_token_usage_display()

    def _init_session_tree(self) -> None:
        """Initialize the session tree in the left pane."""
        try:
            tree = self.query_one("#session_tree", Tree)
            tree.root.expand()
            # Add a placeholder session node
            session_node = tree.root.add("Current Session", expand=True)
            session_node.add_leaf("Messages: 0")
            session_node.add_leaf(f"Dir: {self._short_directory()}")
        except Exception:
            pass  # Tree might not be ready yet

    def _init_tools_list(self) -> None:
        """Initialize the tools list in the left pane."""
        try:
            tools_list = self.query_one("#tools_list", Static)
            if hasattr(self, "tool_executor") and self.tool_executor:
                tool_names = list(self.tool_executor.tools.keys())
                tools_list.update("Available Tools:\n" + "\n".join(f"• {name}" for name in tool_names[:10]))
            else:
                tools_list.update("Tools will be loaded after model connects")
        except Exception:
            pass

    @work(exclusive=True, thread=True)
    def _load_server_model(self) -> None:
        try:
            request = urllib.request.Request(
                _local_server_endpoint("models"),
                headers={"Accept": "application/json"},
            )
            with _open_local(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("data", [])
            model_id = next((item.get("id") for item in models if item.get("id")), None)
            if not model_id:
                raise RuntimeError("llama-server returned no loaded model.")
            self.call_from_thread(self._set_server_model, model_id)
        except Exception as exc:
            self.call_from_thread(self._set_server_error, str(exc))

    def _set_server_model(self, model_id: str) -> None:
        self.loaded_model = model_id
        self.local_server_error = None
        model_select = self.query_one("#model_select", Select)
        model_select.set_options([(model_id, model_id)])
        model_select.value = model_id
        self._refresh_session_labels()

    def _set_server_error(self, message: str) -> None:
        self.local_server_error = message
        self._refresh_session_labels()

    def action_toggle_panes(self) -> None:
        """Toggle visibility of left and right panes."""
        self._panes_visible = not self._panes_visible
        left_pane = self.query_one("#left_pane", Vertical)
        right_pane = self.query_one("#right_pane", Vertical)
        left_pane.display = self._panes_visible
        right_pane.display = self._panes_visible
        self._fire_ui_hook("state_change", {"panes_visible": self._panes_visible})

    def action_focus_prompt(self) -> None:
        self.query_one("#prompt_input", Input).focus()
        self._fire_ui_hook("input_focus", {"widget": "prompt_input"})

    def action_new_session(self) -> None:
        self._session_revision += 1
        self.history = []
        transcript = self.query_one("#transcript")
        transcript.remove_children()
        transcript.mount(ChatMessage("system", "new session started."))
        self.query_one("#welcome-card", Vertical).display = True
        self._fire_ui_hook("view_render", {"view": "transcript", "action": "new_session"})

    def action_toggle_dark(self) -> None:
        # textual >= 0.80 replaced the boolean `.dark` attribute with a
        # named `theme` property; toggle between the two builtin themes
        # rather than relying on the removed attribute.
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        self._fire_ui_hook("state_change", {"theme": self.theme})

    def action_toggle_settings(self) -> None:
        """Toggle the collapsible session settings panel (Ctrl+O)."""
        settings_panel = self.query_one("#settings_panel", Collapsible)
        settings_panel.collapsed = not settings_panel.collapsed
        self._fire_ui_hook("state_change", {"settings_collapsed": settings_panel.collapsed})

    # ========== UI Hook System ==========

    def register_ui_hook(self, hook_name: str, callback: Callable) -> None:
        """Register a UI hook callback."""
        if hook_name in self._ui_hooks:
            self._ui_hooks[hook_name].append(callback)

    def unregister_ui_hook(self, hook_name: str, callback: Callable) -> None:
        """Unregister a UI hook callback."""
        if hook_name in self._ui_hooks and callback in self._ui_hooks[hook_name]:
            self._ui_hooks[hook_name].remove(callback)

    def _fire_ui_hook(self, hook_name: str, data: dict[str, Any]) -> None:
        """Fire a UI hook with the given data."""
        context = UIHookContext(event_type=hook_name, data=data)
        for callback in self._ui_hooks.get(hook_name, []):
            try:
                callback(context)
            except Exception:
                pass  # Hook errors should not break the UI

        # Also post as a message for async handlers
        self.post_message(UIHookEvent(hook_name, context))

    # ========== Tool Progress Display ==========

    def on_tool_progress_update(self, message: ToolProgressUpdate) -> None:
        """Handle tool progress update message."""
        tool_name = message.tool_name
        if tool_name not in self._tool_progress:
            self._tool_progress[tool_name] = {"progress": 0.0, "message": "", "widget": None}

        self._tool_progress[tool_name]["progress"] = message.progress
        self._tool_progress[tool_name]["message"] = message.message

        # Update or create progress widget
        panel = self.query_one("#tool_progress_panel", VerticalScroll)
        if self._tool_progress[tool_name]["widget"] is None:
            # Create new progress widget
            widget = Vertical(classes="tool-progress-item")
            widget.mount(Label(f"🔧 {message.tool_name}", classes="tool-progress-label"))
            progress_bar = ProgressBar(total=100, show_eta=False, id=f"progress_{tool_name}")
            widget.mount(progress_bar)
            message_label = Label(message.message, classes="tool-progress-message")
            widget.mount(message_label)
            panel.mount(widget)
            self._tool_progress[tool_name]["widget"] = widget
            self._tool_progress[tool_name]["progress_bar"] = progress_bar
            self._tool_progress[tool_name]["message_label"] = message_label
        else:
            widget = self._tool_progress[tool_name]["widget"]
            progress_bar = self._tool_progress[tool_name]["progress_bar"]
            message_label = self._tool_progress[tool_name]["message_label"]

        # Update progress
        if progress_bar:
            progress_bar.progress = message.progress
        if message_label:
            message_label.update(message.message)

        # Scroll to bottom
        panel.scroll_end(animate=False)

    # ========== Token Usage Display ==========

    def on_token_usage_update(self, message: TokenUsageUpdate) -> None:
        """Handle token usage update message."""
        self._token_usage = {
            "prompt": message.prompt_tokens,
            "completion": message.completion_tokens,
            "total": message.total_tokens,
        }
        self._update_token_usage_display()

    def _update_token_usage_display(self) -> None:
        """Update the token usage display panel."""
        try:
            panel = self.query_one("#token_usage_panel", Vertical)
        except Exception:
            return

        try:
            panel.remove_children()
        except Exception:
            return

        try:
            panel.mount(Static(f"Prompt: {self._token_usage['prompt']:,}", classes="token-usage-row"))
            panel.mount(Static(f"Completion: {self._token_usage['completion']:,}", classes="token-usage-row"))
            panel.mount(Static(f"Total: {self._token_usage['total']:,}", classes="token-usage-row"))

            # Add cost estimate if available
            if self._token_usage["total"] > 0:
                cost_estimate = self._token_usage["total"] * 0.0001  # Rough estimate
                panel.mount(Static(f"Est. Cost: ${cost_estimate:.4f}", classes="token-usage-row"))
        except Exception:
            pass

    # ========== Status Display ==========

    def _update_status_display(self) -> None:
        """Update the status display panel."""
        try:
            panel = self.query_one("#status_panel", Vertical)
        except Exception:
            return

        try:
            panel.remove_children()
        except Exception:
            return

        status_items = [
            ("Model", self._selected_model()),
            ("Directory", self._short_directory()),
            ("Turns", str(len(self.history) // 2)),
            ("Server", "Connected" if not self.local_server_error else "Error"),
            ("Theme", self.theme),
            ("Panes", "Visible" if self._panes_visible else "Hidden"),
        ]

        for label, value in status_items:
            try:
                row = Horizontal(classes="status-row")
                row.mount(Label(label + ":", classes="status-label"))
                row.mount(Label(value, classes="status-value"))
                panel.mount(row)
            except Exception:
                continue

    # ========== Model Info Display ==========

    def _update_model_display(self) -> None:
        """Update the model info display panel."""
        try:
            panel = self.query_one("#model_panel", Vertical)
        except Exception:
            return

        try:
            panel.remove_children()
        except Exception:
            return

        model_items = [
            ("Loaded Model", self._selected_model()),
            ("Base URL", self.local_server_url),
            ("Temperature", str(self._temperature())),
            ("Streaming", str(self.query_one("#stream_switch", Switch).value)),
        ]

        for label, value in model_items:
            try:
                row = Horizontal(classes="model-info-row")
                row.mount(Label(label + ":", classes="model-info-label"))
                row.mount(Label(value, classes="model-info-value"))
                panel.mount(row)
            except Exception:
                continue

    # ========== Error Display ==========

    def on_error_display(self, message: ErrorDisplay) -> None:
        """Handle error display message."""
        self._error_display = message
        self._update_error_display()

        # Show the errors tab
        tabs = self.query_one("#right_tabs", TabbedContent)
        tabs.active = "tab_errors"

    def _update_error_display(self) -> None:
        """Update the error display panel."""
        panel = self.query_one("#error_panel", Vertical)
        panel.remove_children()

        if self._error_display:
            panel.display = True
            panel.add_class("visible")
            panel.mount(Label(f"⚠ {self._error_display.error_type}", classes="error-message"))
            panel.mount(Label(self._error_display.message, classes="error-message"))
            if self._error_display.recoverable:
                panel.mount(Label("Press Ctrl+R to retry or Esc to dismiss", classes="error-recoverable"))
        else:
            panel.display = False
            panel.remove_class("visible")

    def action_dismiss_error(self) -> None:
        """Dismiss the current error display."""
        self._error_display = None
        self._update_error_display()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt_input":
            self._send()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle tab completion for slash commands."""
        if event.input.id != "prompt_input":
            return

        value = event.value
        if not value.startswith("/"):
            return

        # Get the current word being completed
        parts = value.split()
        if not parts:
            return

        current_word = parts[-1]
        if not current_word.startswith("/"):
            return

        # Get available slash commands
        from zcoder.agent.codeagent.slash_commands import get_slash_registry

        registry = get_slash_registry()

        # Find matching commands
        prefix = current_word[1:]  # Remove leading /
        matches = [cmd for cmd in registry.list_commands() if cmd.name.startswith(prefix)]

        if len(matches) == 1:
            # Exact match - complete it
            cmd = matches[0]
            # Replace the last word with the completed command
            new_value = " ".join(parts[:-1] + [f"/{cmd.name}"])
            if len(parts) == 1:
                new_value += " "
            event.input.value = new_value
            event.input.cursor_position = len(new_value)
        elif len(matches) > 1:
            # Multiple matches - show them in a tooltip or status
            match_names = [f"/{m.name}" for m in matches]
            self.notify(f"Matches: {', '.join(match_names)}", timeout=2.0)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send_btn":
            self._send()
        elif event.button.id == "btn_allow":
            self._on_approval_allow(event)
        elif event.button.id == "btn_allow_session":
            self._on_approval_allow_session(event)
        elif event.button.id == "btn_deny":
            self._on_approval_deny(event)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id in {"model_select", "agent_select", "skill_select", "personality_select"}:
            self._refresh_session_labels()

    def _selected(self, widget_id: str) -> str:
        val = self.query_one(f"#{widget_id}", Select).value
        return val if isinstance(val, str) and val != Select.BLANK else ""

    def _temperature(self) -> float:
        raw = self.query_one("#temp_input", Input).value.strip()
        try:
            t = float(raw)
        except ValueError:
            t = 0.3
        return max(0.0, min(1.0, t))

    def _build_system_prompt(self) -> str | None:
        parts = []
        agent = self._selected("agent_select")
        if agent:
            parts.append(_agent_prompts().get(agent, ""))
        skill = self._selected("skill_select")
        if skill:
            info = SkillManager().get_skill(skill)
            if info:
                parts.append(f"Apply the '{info['name']}' skill: {info['description']}")
        personality = self._selected("personality_select")
        if personality:
            parts.append(PersonalityManager().build_prompt_addition(personality))
        return "\n\n".join(p for p in parts if p) or None

    def _send(self) -> None:
        if self._generation_active:
            return
        prompt_input = self.query_one("#prompt_input", Input)
        text = prompt_input.value.strip()
        if not text:
            return
        prompt_input.value = ""
        if text.startswith("/") and self._handle_command(text):
            return
        self._dismiss_welcome()
        transcript = self.query_one("#transcript")
        transcript.mount(ChatMessage("user", text))
        transcript.scroll_end(animate=False)

        model = self._selected_model()
        system = self._build_system_prompt()
        temperature = self._temperature()
        streaming = self.query_one("#stream_switch", Switch).value

        reply_widget = ChatMessage("assistant", "…")
        transcript.mount(reply_widget)
        transcript.scroll_end(animate=False)
        self._generation_active = True
        prompt_input.disabled = True
        self.query_one("#send_btn", Button).disabled = True
        session_revision = self._session_revision

        self._run_generation(text, model, system, temperature, streaming, reply_widget, session_revision)

    def _show_message(self, role: str, text: str) -> None:
        self._dismiss_welcome()
        transcript = self.query_one("#transcript")
        transcript.mount(ChatMessage(role, text))
        transcript.scroll_end(animate=False)

    def _dismiss_welcome(self) -> None:
        welcome = self.query_one("#welcome-card", Vertical)
        welcome.display = False

    def _handle_command(self, raw: str) -> bool:
        command, _, argument = raw.partition(" ")
        argument = argument.strip()
        if command == "/help":
            self._show_message(
                "system",
                "Commands: /help, /status, /clear, /settings, /model [id], /agent [name], /skill [name]. "
                "Ctrl+N starts a new chat; Ctrl+O opens settings; Ctrl+L focuses the prompt.",
            )
            return True
        if command == "/status":
            server_state = self.local_server_error or "connected"
            self._show_message(
                "system",
                f"provider: local llama.cpp · model: {self._selected_model()} · "
                f"server: {server_state} · directory: {self.working_directory} · "
                f"turns: {len(self.history) // 2}",
            )
            return True
        if command == "/clear":
            self.action_new_session()
            return True
        if command == "/settings":
            self.action_toggle_settings()
            self._show_message("system", "Session settings toggled. Use Ctrl+O to toggle them again.")
            return True
        if command == "/model":
            if argument and argument != self._selected_model():
                self._show_message(
                    "error",
                    "llama-server loads one GGUF at a time. Restart it with the desired GGUF, "
                    "then start a new TUI session.",
                )
            else:
                self._show_message(
                    "system",
                    f"Loaded GGUF: {self._selected_model()}. To change it, restart llama-server "
                    "with the other GGUF, then reopen the TUI.",
                )
            return True
        if command in {"/agent", "/skill"}:
            widget_id = "agent_select" if command == "/agent" else "skill_select"
            options = (
                _agent_prompts().keys()
                if command == "/agent"
                else (item["name"] for item in SkillManager().list_skills())
            )
            names = list(options)
            if not argument:
                self._show_message("system", f"Available {command[1:]} options: {', '.join(names)}")
            elif argument not in names:
                self._show_message("error", f"Unknown {command[1:]}: {argument}")
            else:
                self.query_one(f"#{widget_id}", Select).value = argument
                self._refresh_session_labels()
                self._show_message("system", f"{command[1:].capitalize()} set to {argument}.")
            return True
        self._show_message("error", f"Unknown command: {command}. Type /help for available commands.")
        return True

    # ========== Approval Dialog Methods ==========

    def _show_approval_dialog(self, tool_name: str, args: dict, summary: str, diff: str, reason: str) -> None:
        """Show the approval dialog for a tool call."""
        dialog = self.query_one("#approval_dialog", Vertical)
        dialog.remove_class("approval_dialog")

        self.query_one("#approval_title", Label).update("⚠  Tool Execution Requires Approval")
        self.query_one("#approval_tool", Label).update(f"Tool: {tool_name}")
        self.query_one("#approval_args", Label).update(f"Arguments: {args}")
        self.query_one("#approval_reason", Label).update(f"Reason: {reason}")
        self.query_one("#approval_diff", Label).update(
            f"Changes:\n{diff}" if diff else "No changes to preview"
        )

        # Focus the deny button by default (safer default)
        self.query_one("#btn_deny", Button).focus()

    def _hide_approval_dialog(self) -> None:
        """Hide the approval dialog."""
        dialog = self.query_one("#approval_dialog", Vertical)
        dialog.add_class("approval_dialog")

    def _on_approval_allow(self, event: Button.Pressed) -> None:
        """Handle Allow button press."""
        self._approval_result = ("allow", None)
        self._hide_approval_dialog()
        self.query_one("#prompt_input", Input).focus()

    def _on_approval_allow_session(self, event: Button.Pressed) -> None:
        """Handle Allow Session button press."""
        self._approval_result = ("allow_session", None)
        self._hide_approval_dialog()
        self.query_one("#prompt_input", Input).focus()

    def _on_approval_deny(self, event: Button.Pressed) -> None:
        """Handle Deny button press."""
        self._approval_result = ("deny", None)
        self._hide_approval_dialog()
        self.query_one("#prompt_input", Input).focus()

    def _refresh_session_labels(self) -> None:
        try:
            self.query_one("#welcome-meta", Static).update(self._welcome_meta())
        except Exception:
            pass
        try:
            self.query_one("#session_status", Static).update(self._status_text())
        except Exception:
            pass
        try:
            self._update_status_display()
        except Exception:
            pass
        try:
            self._update_model_display()
        except Exception:
            pass
        try:
            self._update_token_usage_display()
        except Exception:
            pass

    @work(exclusive=False, thread=True)
    def _run_generation(
        self, prompt, model, system, temperature, streaming, reply_widget, session_revision
    ) -> None:
        history_snapshot = list(self.history)
        failed = False
        try:
            if streaming:
                full_text = self._stream_reply(
                    prompt, model, system, temperature, history_snapshot, reply_widget
                )
            else:
                full_text = self._complete_local(prompt, model, system, temperature, history_snapshot)
                self.call_from_thread(reply_widget.update_text, full_text)
        except Exception as e:  # keep the TUI alive on any generation failure
            full_text = f"[LOCAL MODEL ERROR] {e}"
            failed = True
            self.call_from_thread(reply_widget.update_text, full_text)
            self.call_from_thread(reply_widget.add_class, "msg-error")

        self.call_from_thread(
            self._finish_generation,
            prompt,
            full_text,
            history_snapshot,
            session_revision,
            failed,
        )

    def _finish_generation(self, prompt, response, history_snapshot, session_revision, failed) -> None:
        if not failed and session_revision == self._session_revision:
            self.history = history_snapshot + [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
        self._generation_active = False
        self.query_one("#prompt_input", Input).disabled = False
        self.query_one("#send_btn", Button).disabled = False
        if failed:
            self.local_server_error = "The local model request failed. Check llama-server and retry."
        self._refresh_session_labels()

    def _messages(self, prompt: str, system: str | None, history: list[dict]) -> list[dict]:
        messages = list(history)
        if system:
            messages.insert(0, {"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _local_request(self, prompt, model, system, temperature, history, *, stream):
        payload = {
            "model": model,
            "messages": self._messages(prompt, system, history),
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": stream,
        }
        request = urllib.request.Request(
            _local_server_endpoint("chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            },
            method="POST",
        )
        try:
            return _open_local(request, timeout=300)
        except urllib.error.HTTPError as exc:
            body = exc.read(500).decode("utf-8", errors="replace")
            raise RuntimeError(f"llama-server returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot connect to local llama-server at {self.local_server_url}: {exc.reason}"
            ) from exc

    def _complete_local(self, prompt, model, system, temperature, history) -> str:
        with self._local_request(prompt, model, system, temperature, history, stream=False) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("llama-server returned no completion choices.")
        content = (choices[0].get("message") or {}).get("content", "")
        if not isinstance(content, str):
            raise RuntimeError("llama-server returned an unsupported response format.")
        return content

    def _stream_reply(self, prompt, model, system, temperature, history, reply_widget) -> str:
        full_text = ""
        render_gate = StreamRenderGate()
        with self._local_request(prompt, model, system, temperature, history, stream=True) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}).get("content", "")
                if isinstance(delta, list):
                    delta = "".join(item.get("text", "") for item in delta if isinstance(item, dict))
                if not isinstance(delta, str) or not delta:
                    continue
                full_text += delta
                # Coalesce UI updates to avoid excessive terminal redraws.
                if render_gate.should_render(delta, time.monotonic()):
                    self.call_from_thread(reply_widget.update_text, full_text)
                    self.call_from_thread(self.query_one("#transcript").scroll_end, animate=False)
        if not full_text:
            raise RuntimeError("llama-server returned an empty streamed response.")
        # Flush the final unpainted delta so the transcript matches history.
        self.call_from_thread(reply_widget.update_text, full_text)
        self.call_from_thread(self.query_one("#transcript").scroll_end, animate=False)
        return full_text


def run_tui(api_key: str | None = None) -> None:
    """Entry point used by main.py's --tui flag; API keys are ignored."""
    del api_key
    ZCoderTUI().run()


if __name__ == "__main__":  # pragma: no cover
    run_tui()

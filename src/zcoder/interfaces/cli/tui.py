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

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import (
        Button,
        Collapsible,
        Footer,
        Header,
        Input,
        Label,
        Select,
        Static,
        Switch,
    )
except ImportError as e:  # pragma: no cover - exercised only w/o textual installed
    raise ImportError(
        "The --tui flag needs the 'textual' package, which isn't installed.\n"
        "Install it with:  pip install textual>=0.80.0\n"
        "(or: pip install -r requirements.txt, it's an optional extra there)"
    ) from e

from zcoder.agent.personalities import AGENT_SYSTEM_PROMPTS, PersonalityManager
from zcoder.interfaces.cli.streaming import StreamRenderGate
from zcoder.services.skills import SkillManager

DEFAULT_MODEL = "zqwen2.5-coder-7b-instruct-q4_k_m"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"


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
    #main { height: 1fr; width: 1fr; padding: 0 2; }
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
    """

    BINDINGS = [
        ("ctrl+n", "new_session", "New session"),
        ("ctrl+o", "toggle_settings", "Settings"),
        ("ctrl+l", "focus_prompt", "Focus prompt"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+t", "toggle_dark", "Toggle theme"),
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
        try:
            self.local_server_url = _local_server_base_url()
        except ValueError:
            self.local_server_url = "invalid loopback ZCODER_BASE_URL"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Vertical(id="welcome-card"):
                yield Label("✳  ZCoder", id="welcome-title")
                yield Static("Your coding assistant", id="welcome-subtitle")
                yield Static(self._welcome_meta(), id="welcome-meta")
                yield Static(
                    "Try /help for commands · /status for session details · /model for loaded model",
                    id="welcome-hints",
                )
            yield VerticalScroll(id="transcript")
            with Collapsible(title="Session settings  ·  Ctrl+O", collapsed=True, id="settings_panel"):
                yield SessionSidebar(id="sidebar")
            yield Static(self._status_text(), id="session_status")
            with Horizontal(id="input_row"):
                yield Input(placeholder="Describe a coding task or ask a question…", id="prompt_input")
                yield Button("Send", id="send_btn", variant="primary")
        yield Footer()

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

    def action_toggle_settings(self) -> None:
        panel = self.query_one("#settings_panel", Collapsible)
        panel.collapsed = not panel.collapsed

    def action_focus_prompt(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def action_new_session(self) -> None:
        self._session_revision += 1
        self.history = []
        transcript = self.query_one("#transcript")
        transcript.remove_children()
        transcript.mount(ChatMessage("system", "new session started."))
        self.query_one("#welcome-card", Vertical).display = True

    def action_toggle_dark(self) -> None:
        # textual >= 0.80 replaced the boolean `.dark` attribute with a
        # named `theme` property; toggle between the two builtin themes
        # rather than relying on the removed attribute.
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt_input":
            self._send()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send_btn":
            self._send()

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

    def _refresh_session_labels(self) -> None:
        self.query_one("#welcome-meta", Static).update(self._welcome_meta())
        self.query_one("#session_status", Static).update(self._status_text())

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

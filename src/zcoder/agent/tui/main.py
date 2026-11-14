"""Main TUI Application for Phase 17.

Provides a Textual-based terminal user interface with collaboration
presence, an agent list, and a broadcast console backed by the local
agent registry and the JSON-RPC 2.0 protocol.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, Log, Static

from zcoder.agent.communication import create_notification, get_registry

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """TUI collaboration modes."""

    SOLITARY = "solitary"
    OBSERVE = "observe"
    EDIT = "edit"
    SHARE = "share"


class CollaborationApp(App):
    """TUI application with collaboration presence and an agent list."""

    title = "ZCoder TUI - Phase 17 Collaboration"

    BINDINGS = [
        Binding("q", "quit", "Quit application"),
        Binding("c", "toggle_collab", "Toggle collaboration mode"),
        Binding("r", "refresh", "Refresh agent list"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.registry = get_registry()
        self.mode = CollaborationMode.SOLITARY
        self.agent_names: dict[str, str] = {}
        self._refresh_task: asyncio.Task | None = None

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self._refresh_task = asyncio.create_task(self._periodic_registry_refresh())

    def on_unmount(self) -> None:
        """Cancel background work when the app unmounts."""
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    async def _periodic_registry_refresh(self) -> None:
        """Periodically refresh the agent list from the registry."""
        while True:
            try:
                await asyncio.sleep(5)
                agents = self.registry.list_agents()
                self.agent_names = {a.agent_id: a.name or f"Agent {a.agent_id[:8]}" for a in agents}
                self.refresh_agents_display()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Registry refresh failed")

    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()
        with Vertical():
            yield Label("ZCoder TUI - Phase 17 Collaboration", id="title")
            yield Log(id="log", classes="log")
            with Horizontal():
                yield Label("Agents:", id="agents-label")
                yield Static("No agents connected", id="agents-display", classes="agents-display")
            yield Input(placeholder="Enter prompt...", id="prompt-input")
        yield Footer()

    def action_toggle_collab(self) -> None:
        """Cycle the collaboration mode."""
        order = [
            CollaborationMode.SOLITARY,
            CollaborationMode.OBSERVE,
            CollaborationMode.EDIT,
            CollaborationMode.SHARE,
        ]
        idx = order.index(self.mode)
        self.mode = order[(idx + 1) % len(order)]
        self.refresh_agents_display()

    def action_refresh(self) -> None:
        """Refresh the agent list now."""
        agents = self.registry.list_agents()
        self.agent_names = {a.agent_id: a.name or f"Agent {a.agent_id[:8]}" for a in agents}
        self.refresh_agents_display()

    def refresh_agents_display(self) -> None:
        """Refresh the agents display widget."""
        agents_display = self.query_one("#agents-display", Static)
        count = len(self.agent_names)
        labels = {
            CollaborationMode.SOLITARY: "Local mode - no collaboration",
            CollaborationMode.OBSERVE: f"Observing {count} connected agents",
            CollaborationMode.EDIT: f"Collaborative edit mode - {count} agents",
            CollaborationMode.SHARE: f"Shared mode - {count} agents editing",
        }
        agents_display.update(labels[self.mode])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        prompt = event.value
        self.query_one("#prompt-input", Input).value = ""
        self.append_log(f"> {prompt}")

        if self.mode != CollaborationMode.SOLITARY:
            asyncio.create_task(self._send_collab_message(prompt))

    async def _send_collab_message(self, content: str) -> None:
        """Build and broadcast a collaboration message."""
        create_notification(
            "sync_state",
            {"type": "user_input", "content": content},
        )
        self.append_log(f"[Broadcast] {content[:50]}")

    def append_log(self, message: str) -> None:
        """Append a message to the log widget."""
        self.query_one("#log", Log).write_line(message)

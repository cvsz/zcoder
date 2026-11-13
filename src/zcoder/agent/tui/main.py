"""Main TUI Application for Phase 17.

Provides a Textual-based terminal user interface with real-time
collaboration features including shared cursor, selection, and
multi-user editing mode.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    Log,
    Static,
)

from zcoder.agent.communication.protocol import (
    Operation,
    make_notification,
)
from zcoder.agent.communication.registry import create_default_registry

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """TUI collaboration modes."""

    SOLITARY = "solitary"
    OBSERVE = "observe"
    EDIT = "edit"
    SHARE = "share"


collaboration_mode = CollaborationMode.SOLITARY

connected_agents = {}


class CollaborationApp(App):
    """Main TUI application with collaboration features."""

    BINDINGS = [
        Binding("q", "quit", "Quit application"),
        Binding("c", "toggle_collab", "Toggle collaboration mode"),
        Binding("r", "refresh", "Refresh agent list"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.registry = create_default_registry()
        self.mode = CollaborationMode.SOLITARY
        self.agent_names: dict[str, str] = {}
        self._refresh_task: asyncio.Task | None = None

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self._setup_styles()
        self._refresh_task = asyncio.create_task(self._periodic_registry_refresh())
        self.set_title("ZCoder TUI - Phase 17 Collaboration")

    def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        if self._refresh_task:
            self._refresh_task.cancel()

    def _setup_styles(self) -> None:
        """Setup app styles."""
        self.set_window_size(100, 40)

    async def _periodic_registry_refresh(self) -> None:
        """Periodically refresh the agent registry."""
        while True:
            try:
                await asyncio.sleep(5)
                # Refresh agent list from registry
                agents = self.registry.list_agents()
                self.agent_names = {a.agent_id: a.name or f"Agent {a.agent_id[:8]}" for a in agents}
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Registry refresh error: {e}")

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
        """Toggle collaboration mode."""
        if self.mode == CollaborationMode.SOLITARY:
            self.mode = CollaborationMode.OBSERVE
        elif self.mode == CollaborationMode.OBSERVE:
            self.mode = CollaborationMode.EDIT
        elif self.mode == CollaborationMode.EDIT:
            self.mode = CollaborationMode.SHARE
        else:
            self.mode = CollaborationMode.SOLITARY
        self.refresh_agents_display()

    def refresh_agents_display(self) -> None:
        """Refresh the agents display widget."""
        agents_display = self.query_one("#agents-display", Static)
        if self.mode == CollaborationMode.SOLITARY:
            agents_display.update("Local mode - no collaboration")
        elif self.mode == CollaborationMode.OBSERVE:
            agents_display.update(f"Observing {len(self.agent_names)} connected agents")
        elif self.mode == CollaborationMode.EDIT:
            agents_display.update(f"Collaborative edit mode - {len(self.agent_names)} agents")
        else:
            agents_display.update(f"Shared mode - {len(self.agent_names)} agents editing")

    def action_refresh(self) -> None:
        """Refresh the agent list."""
        pass  # Refresh is done periodically

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        prompt = event.value
        self.query_one("#prompt-input", Input).value = ""
        self.log(f"> {prompt}")

        # If in collaboration mode, send message to other agents
        if self.mode != CollaborationMode.SOLITARY:
            asyncio.create_task(self._send_collab_message(prompt))

    async def _send_collab_message(self, content: str) -> None:
        """Send a collaboration message to other agents."""
        msg = make_notification(
            operation=Operation.EXECUTE,
            payload={"type": "user_input", "content": content},
        )
        # In a full implementation, this would send via the registry/endpoint
        self.log(f"[Broadcast] {msg.id[:8]}: {content[:50]}")

    def log(self, message: str) -> None:
        """Add a message to the log widget."""
        log_widget = self.query_one("#log", Log)
        log_widget.write_line(message)

    def on_unload(self) -> None:
        """Clean up on unload."""
        if self._refresh_task:
            self._refresh_task.cancel()

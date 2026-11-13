"""Real-time Collaboration Components for Phase 17 TUI.

Provides shared cursor, selection, and collaborative editing
features for the Textual-based TUI.
"""

from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from typing import Any

from textual.reactive import reactive
from textual.widget import Widget

from zcoder.agent.communication.protocol import AgentMessage

logger = logging.getLogger(__name__)


class SharedCursorInfo:
    """Information about a shared cursor position."""

    agent_id: str
    name: str
    position: tuple[int, int]  # (line, col)
    color: str = "#ff0000"  # Red by default


class CollaborationState(Enum):
    """State of the collaboration session."""

    IDLE = "idle"
    EDITING = "editing"
    SYNCING = "syncing"


@reactive
def collaboration_state() -> CollaborationState:
    """Current collaboration state."""
    return CollaborationState.IDLE


class CollaborativePane(Widget):
    """A widget that supports real-time collaborative editing."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cursor_positions: dict[str, SharedCursorInfo] = {}
        self._selection: tuple[int, int, int, int] | None = None  # (start_line, start_col, end_line, end_col)
        self._local_cursor: tuple[int, int] = (0, 0)
        self._agent_colors: dict[str, str] = {}
        self._next_color_index = 0
        self._color_palette: list[str] = [
            "#ff0000",
            "#00ff00",
            "#0000ff",
            "#ffff00",
            "#ff00ff",
            "#00ffff",
        ]

    def on_mount(self) -> None:
        """Called when widget is mounted."""
        self._register_local_cursor()
        self._start_cursor_sync()

    def _register_local_cursor(self) -> None:
        """Register the local agent's cursor position."""
        local_agent_id = os.environ.get("ZCODER_AGENT_ID", "local")
        color = self._get_next_color()
        self._agent_colors[local_agent_id] = color

        cursor_info = SharedCursorInfo(
            agent_id=local_agent_id,
            name=local_agent_id,
            position=self._local_cursor,
            color=color,
        )
        self._cursor_positions[local_agent_id] = cursor_info

        # Notify other agents about our presence
        msg = AgentMessage(
            type="notification",
            operation="sync",
            payload={
                "type": "cursor_update",
                "position": list(self._local_cursor),
                "agent_id": local_agent_id,
            },
        )
        self._broadcast_cursor(msg)

    def _get_next_color(self) -> str:
        """Get the next available color for a new agent."""
        color = self._color_palette[self._next_color_index % len(self._color_palette)]
        self._next_color_index += 1
        return color

    def _start_cursor_sync(self) -> None:
        """Start the cursor synchronization task."""
        asyncio.create_task(self._cursor_sync_loop())

    async def _cursor_sync_loop(self) -> None:
        """Periodically sync cursor positions with other agents."""
        while True:
            try:
                await asyncio.sleep(0.1)  # 100ms sync interval
                self._sync_cursor_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cursor sync error: {e}")

    def _sync_cursor_positions(self) -> None:
        """Sync cursor positions from the registry/other agents."""
        # In a full implementation, this would receive updates from other agents
        # For now, just update the local cursor position display
        pass

    def _broadcast_cursor(self, msg: Any) -> None:
        """Broadcast cursor position to other agents."""
        # In a full implementation, this would send via the communication protocol
        pass

    def update_cursor(
        self,
        agent_id: str,
        position: tuple[int, int],
        name: str | None = None,
    ) -> None:
        """Update a remote agent's cursor position."""
        color = self._agent_colors.get(agent_id)
        if color is None:
            color = self._get_agent_color(agent_id)

        self._cursor_positions[agent_id] = SharedCursorInfo(
            agent_id=agent_id,
            name=name or agent_id,
            position=position,
            color=color,
        )
        self.refresh()

    def _get_agent_color(self, agent_id: str) -> str:
        """Get or assign a color for an agent."""
        if agent_id in self._agent_colors:
            return self._agent_colors[agent_id]

        color = self._get_next_color()
        self._agent_colors[agent_id] = color
        return color

    def set_selection(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        """Set the selection range."""
        self._selection = (*start, *end)
        self.refresh()

    def get_selection(self) -> tuple[int, int, int, int] | None:
        """Get the current selection range."""
        return self._selection

    def handle_key(self, key: str) -> bool:
        """Handle key presses for collaborative editing."""
        # Process key and update selection
        if key in ("enter", "backspace", "delete", "\t"):
            # Broadcast the editing action
            self._broadcast_editing_action(key)
        return super().handle_key(key)

    def _broadcast_editing_action(self, action: str) -> None:
        """Broadcast an editing action to other agents."""
        # In a full implementation, this would send via the communication protocol
        pass

    def render(self) -> str:
        """Render the collaborative pane."""
        # Simple rendering - in a full implementation this would show
        # the document with shared cursors and selections
        lines: list[str] = []
        for i in range(20):  # 20 lines of display
            if i == self._local_cursor[0]:
                lines.append(">" + " " * self._local_cursor[1] + "<")
            else:
                lines.append(" " * (1 + self._local_cursor[1] + 1))
        return "\n".join(lines)

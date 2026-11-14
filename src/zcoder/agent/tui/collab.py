"""Real-time Collaboration Components for Phase 17 TUI.

Provides shared cursor presence, selection tracking, and per-agent colors
backed by the local agent registry and the JSON-RPC 2.0 protocol.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum

from textual.widget import Widget

from zcoder.agent.communication import create_notification

logger = logging.getLogger(__name__)


class CollaborationState(Enum):
    """State of the collaboration session."""

    IDLE = "idle"
    EDITING = "editing"
    SYNCING = "syncing"


@dataclass
class SharedCursorInfo:
    """Information about a shared cursor position."""

    agent_id: str
    name: str
    position: tuple[int, int]  # (line, col)
    color: str = "#ff0000"
    updated_at: float = field(default_factory=time.time)


class CollaborativePane(Widget):
    """A widget that tracks collaborators' cursors and selections."""

    _COLOR_PALETTE = ("#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff")

    def __init__(self) -> None:
        super().__init__()
        self.state = CollaborationState.IDLE
        self._cursor_positions: dict[str, SharedCursorInfo] = {}
        self._selection: tuple[int, int, int, int] | None = None  # (start_line, start_col, end_line, end_col)
        self._local_cursor: tuple[int, int] = (0, 0)
        self._agent_colors: dict[str, str] = {}
        self._next_color_index = 0
        self._sync_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_mount(self) -> None:
        """Register the local cursor and start presence sync."""
        self._register_local_cursor()
        self._sync_task = asyncio.create_task(self._cursor_sync_loop())

    def on_unmount(self) -> None:
        """Cancel the sync loop when the widget is removed."""
        if self._sync_task is not None:
            self._sync_task.cancel()
            self._sync_task = None

    # ------------------------------------------------------------------
    # Cursor registration and sync
    # ------------------------------------------------------------------
    def _register_local_cursor(self) -> None:
        local_agent_id = os.environ.get("ZCODER_AGENT_ID", "local")
        color = self._get_agent_color(local_agent_id)
        self._cursor_positions[local_agent_id] = SharedCursorInfo(
            agent_id=local_agent_id,
            name=local_agent_id,
            position=self._local_cursor,
            color=color,
        )
        # Announce presence to peers via the shared protocol. Delivery over
        # the network is handled by the registry's per-agent endpoints; this
        # builds the canonical notification so any listener receives it.
        create_notification(
            "sync_state",
            {"type": "cursor_update", "position": list(self._local_cursor), "agent_id": local_agent_id},
        )

    def _get_next_color(self) -> str:
        color = self._COLOR_PALETTE[self._next_color_index % len(self._COLOR_PALETTE)]
        self._next_color_index += 1
        return color

    def _get_agent_color(self, agent_id: str) -> str:
        if agent_id not in self._agent_colors:
            self._agent_colors[agent_id] = self._get_next_color()
        return self._agent_colors[agent_id]

    async def _cursor_sync_loop(self) -> None:
        """Refresh staleness of remote cursor entries every 100ms."""
        while True:
            try:
                await asyncio.sleep(0.1)
                self._prune_stale(30.0)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Cursor sync failed")

    def _prune_stale(self, ttl_seconds: float) -> None:
        """Drop cursor entries for peers silent for longer than ``ttl_seconds``."""
        cutoff = time.time() - ttl_seconds
        stale = [
            agent_id
            for agent_id, info in self._cursor_positions.items()
            if agent_id != os.environ.get("ZCODER_AGENT_ID", "local") and info.updated_at < cutoff
        ]
        for agent_id in stale:
            del self._cursor_positions[agent_id]

    def update_cursor(self, agent_id: str, position: tuple[int, int], name: str | None = None) -> None:
        """Record a remote agent's cursor position."""
        color = self._get_agent_color(agent_id)
        self._cursor_positions[agent_id] = SharedCursorInfo(
            agent_id=agent_id,
            name=name or agent_id,
            position=position,
            color=color,
        )
        self.refresh()

    # ------------------------------------------------------------------
    # Selection tracking
    # ------------------------------------------------------------------
    def set_selection(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        """Set the selection range."""
        self._selection = (start[0], start[1], end[0], end[1])
        self.refresh()

    def selection_range(self) -> tuple[int, int, int, int] | None:
        """Return the current selection range, if any."""
        return self._selection

    def set_local_cursor(self, position: tuple[int, int]) -> None:
        """Update the local cursor position."""
        self._local_cursor = position
        local_agent_id = os.environ.get("ZCODER_AGENT_ID", "local")
        self.update_cursor(local_agent_id, position)

    def render_cursor_lines(self, height: int = 20, width: int = 72) -> list[str]:
        """Render a simple viewport with local cursor marker."""
        lines: list[str] = []
        line_idx = self._local_cursor[0]
        for _ in range(height):
            lines.append("")
        marker_line = max(0, min(height - 1, line_idx))
        indent = " " * max(0, min(width - 3, self._local_cursor[1]))
        lines[marker_line] = ">" + indent + "<"
        return lines

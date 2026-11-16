"""
panes.py — TUI Split-Pane Components

Provides split-pane layout components for the Textual-based TUI interface.
Supports collapsible panes, shared state, and real-time collaboration features.

ZCoder CLI v1.60.3
"""

from __future__ import annotations

import logging
from typing import Any, cast

from textual.containers import Vertical
from textual.widget import Widget

from zcoder.agent.tui.collab import CollaborationState, CollaborativePane

logger = logging.getLogger(__name__)


class PaneManager:
    """Manages split-pane layout and state for the TUI interface."""

    def __init__(
        self,
        panes: list[dict[str, Any]] | None = None,
        min_width: int = 20,
        min_height: int = 5,
    ):
        self.panes: list[dict[str, Any]] = panes or self._default_panes()
        self.min_width = min_width
        self.min_height = min_height
        self._focus_index = 0

    @property
    def focus_index(self) -> int:
        return self._focus_index

    @focus_index.setter
    def focus_index(self, index: int) -> None:
        self._focus_index = max(0, min(index, len(self.panes) - 1))

    def _default_panes(self) -> list[dict[str, Any]]:
        """Default pane configuration for TUI interface."""
        return [
            {"id": "transcript", "label": "Transcript", "size": "60%", "collapsible": False},
            {"id": "tools", "label": "Tools", "size": "20%", "collapsible": True},
            {"id": "status", "label": "Status", "size": "20%", "collapsible": True},
        ]

    def rebalance(self, container_size: tuple[int, int]) -> list[dict[str, Any]]:
        """Rebalance pane sizes based on container dimensions."""
        width, height = container_size
        result: list[dict[str, Any]] = []

        # Calculate available space
        available_width = max(width - sum(p.get("min_width", self.min_width) for p in self.panes), 100)
        available_height = height

        for i, pane in enumerate(self.panes):
            # Base size calculation
            base_size = pane.get("size", "33%")
            if isinstance(base_size, str) and base_size.endswith("%"):
                # Percentage-based sizing
                pct = int(float(base_size.rstrip("%")) / 100 * available_width)
                pct = max(
                    self.min_width,
                    min(
                        pct,
                        available_width - self.min_width * (len(self.panes) - 1 - i),
                    ),
                )
                result.append(
                    cast(
                        dict[str, Any],
                        {
                            "id": pane["id"],
                            "label": pane["label"],
                            "width": pct,
                            "height": available_height,
                            "collapsible": pane.get("collapsible", False),
                        },
                    )
                )
            else:
                # Fixed size
                result.append(
                    cast(
                        dict[str, Any],
                        {
                            "id": pane["id"],
                            "label": pane["label"],
                            "width": max(self.min_width, int(base_size)),
                            "height": available_height,
                            "collapsible": pane.get("collapsible", False),
                        },
                    )
                )

        return result


class TUILayout(Widget):
    """Main TUI layout combining panes with collaboration support."""

    def __init__(
        self,
        panes_config: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.pane_manager = PaneManager(panes_config)
        self.collaboration_state = CollaborationState.IDLE

    def compose(self):
        """Compose the TUI layout with panes."""
        pane_configs = self.pane_manager.panes
        total_panes = len(pane_configs)

        if total_panes == 0:
            # Default single pane if no config provided
            yield Vertical(Widget(), id="main-layout")
            return

        if total_panes == 1:
            yield Vertical(
                self._create_pane(pane_configs[0]),
                id="main-layout",
            )
        else:
            # Build horizontal split with panes
            for i, config in enumerate(pane_configs):
                pane = self._create_pane(config)
                yield pane
                # Add collaborative pane support for multi-user editing
                if i < total_panes - 1:
                    # Yield a separator/indicator between panes
                    yield Widget()

    def _create_pane(self, config: dict[str, Any]) -> Widget:
        """Create a pane widget from configuration."""
        # Use CollaborativePane for collaboration-enabled panes
        is_collaborative = config.get("collapsible", False)
        pane_id = config.get("id", "pane")

        if is_collaborative:
            # For collaborative panes, use CollaborativePane from collab module
            return CollaborativePane()
        else:
            # Regular pane as a Vertical container
            return Vertical(Widget(), id=pane_id)

    def on_mount(self) -> None:
        """Called when the layout is mounted, setup pane focus."""
        # Set initial focus to first pane
        if self.pane_manager.panes:
            self.pane_manager.focus_index = 0

    def rebuild(self) -> None:
        """Rebuild the layout with current pane manager configuration."""
        self.remove()
        # Re-compose children
        for child in self.compose():
            self.mount(child)

    def update_collaboration_state(self, state: CollaborationState) -> None:
        """Update collaboration state across the layout."""
        self.collaboration_state = state
        # Propagate state to all collaborative panes
        for pane in self._find_collaborative_panes():
            pane.update_collaboration_state(state)

    def _find_collaborative_panes(self) -> list[CollaborativePane]:
        """Find all CollaborativePane children in the layout."""
        panes: list[CollaborativePane] = []
        for child in self.children:
            if isinstance(child, CollaborativePane):
                panes.append(child)
        return panes

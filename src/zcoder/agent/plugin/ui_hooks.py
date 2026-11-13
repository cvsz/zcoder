"""UI Pane/Dialog hooks for zcoder plugin system.

Provides diff pane, scroll, focus, and close event handling
compatible with claude-code's UI hook system.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult

logger = logging.getLogger(__name__)


@dataclass
class DiffHunk:
    """A single diff hunk."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]


@dataclass
class DiffFile:
    """A file with diffs."""
    path: str
    status: str  # added, modified, deleted, renamed
    hunks: list[DiffHunk] = field(default_factory=list)
    old_path: str | None = None  # For renames


@dataclass
class DiffPane:
    """Diff pane state for docked or dialog mode."""
    repo_path: str
    session_id: str
    base: str = "HEAD"
    files: list[DiffFile] = field(default_factory=list)
    selected_index: int = 0
    mode: str = "docked"  # docked, dialog
    viewport_height: int = 20

    def get_selected_file(self) -> DiffFile | None:
        """Get currently selected file."""
        if 0 <= self.selected_index < len(self.files):
            return self.files[self.selected_index]
        return None

    def scroll(self, delta: int) -> None:
        """Scroll file list or hunks."""
        if delta > 0:
            self.selected_index = min(len(self.files) - 1, self.selected_index + delta)
        elif delta < 0:
            self.selected_index = max(0, self.selected_index + delta)

    def set_mode(self, mode: str) -> None:
        """Set pane mode (docked or dialog)."""
        if mode in ("docked", "dialog"):
            self.mode = mode

    def to_dict(self) -> dict[str, Any]:
        """Serialize for UI rendering."""
        return {
            "repo_path": self.repo_path,
            "session_id": self.session_id,
            "base": self.base,
            "files": [
                {
                    "path": f.path,
                    "status": f.status,
                    "old_path": f.old_path,
                    "hunk_count": len(f.hunks),
                }
                for f in self.files
            ],
            "selected_index": self.selected_index,
            "mode": self.mode,
        }


class UIPaneManager:
    """Manages UI panes for the session."""

    def __init__(self, hook_bus: HookBus):
        self.hook_bus = hook_bus
        self.panes: dict[str, DiffPane] = {}  # pane_id -> DiffPane

    async def handle_ui_render(self, context: HookContext) -> HookResult:
        """Handle ui.render event for panes."""
        pane_id = context.args.get("pane_id", "default")
        pane = self.panes.get(pane_id)
        if not pane:
            return HookResult()

        # Return pane data for rendering
        return HookResult(
            modified_args={"pane_data": pane.to_dict()},
        )

    async def handle_ui_scroll(self, context: HookContext) -> HookResult:
        """Handle ui.scroll event."""
        pane_id = context.args.get("pane_id", "default")
        delta = context.args.get("delta", 0)
        pane = self.panes.get(pane_id)
        if pane:
            pane.scroll(delta)
        return HookResult()

    async def handle_ui_focus(self, context: HookContext) -> HookResult:
        """Handle ui.focus event."""
        pane_id = context.args.get("pane_id", "default")
        index = context.args.get("index", 0)
        pane = self.panes.get(pane_id)
        if pane and 0 <= index < len(pane.files):
            pane.selected_index = index
        return HookResult()

    async def handle_ui_close(self, context: HookContext) -> HookResult:
        """Handle ui.close event - back out of detail view or close pane."""
        pane_id = context.args.get("pane_id", "default")
        pane = self.panes.get(pane_id)
        if not pane:
            return HookResult()

        # In dialog mode, Escape backs out of detail view first
        if pane.mode == "dialog" and pane.selected_index >= 0:
            # Signal to back out of detail view
            return HookResult(modified_args={"action": "back_out"})
        else:
            # Actually close the pane
            del self.panes[pane_id]
            return HookResult(modified_args={"action": "closed"})

    async def handle_command_diff(
        self,
        context: HookContext,
        repo_path: str,
        session_id: str,
    ) -> HookResult:
        """Handle /diff command - open or close diff pane."""
        pane_id = context.args.get("pane_id", "default")

        if pane_id in self.panes:
            # Close existing pane
            del self.panes[pane_id]
            return HookResult(modified_args={"action": "closed", "message": "Diff pane closed"})

        # Create new diff pane
        pane = DiffPane(repo_path=repo_path, session_id=session_id)
        self.panes[pane_id] = pane

        # Fetch initial diff
        files = await self._fetch_diff(repo_path)
        pane.files = files

        if not files:
            del self.panes[pane_id]
            return HookResult(modified_args={"action": "none", "message": "No changes to show"})

        return HookResult(
            modified_args={
                "action": "opened",
                "pane_data": pane.to_dict(),
                "message": "Diff pane opened",
            }
        )

    async def _fetch_diff(self, repo_path: str) -> list[DiffFile]:
        """Fetch git diff for repo."""
        import subprocess
        try:
            # Get file list with status
            result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return []

            files = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                status, path = parts
                diff_file = DiffFile(path=path, status=status)

                # Get hunks for this file
                hunk_result = subprocess.run(
                    ["git", "diff", "HEAD", "--", path],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if hunk_result.returncode == 0 and hunk_result.stdout:
                    diff_file.hunks = self._parse_hunks(hunk_result.stdout)

                files.append(diff_file)

            return files
        except Exception as e:
            logger.error(f"Failed to fetch diff: {e}")
            return []

    def _parse_hunks(self, diff_output: str) -> list[DiffHunk]:
        """Parse unified diff output into hunks."""
        hunks = []
        lines = diff_output.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("@@"):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                import re
                match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1

                    # Collect hunk lines
                    hunk_lines = [line]
                    i += 1
                    while i < len(lines) and not lines[i].startswith("@@"):
                        hunk_lines.append(lines[i])
                        i += 1
                    i -= 1  # Adjust for outer loop

                    hunks.append(DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=hunk_lines,
                    ))
            i += 1
        return hunks


def register_ui_hooks(hook_bus: HookBus, pane_manager: UIPaneManager) -> None:
    """Register UI hook handlers with the hook bus."""
    # The hook bus fires events, but UI hooks need to be callable from the UI layer
    # This is a registration point for the UI to call into
    pass
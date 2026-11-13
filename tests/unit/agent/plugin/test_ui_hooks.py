"""Tests for UI hooks."""

from zcoder.agent.plugin.ui_hooks import DiffFile, DiffHunk, DiffPane, UIPaneManager


class TestDiffHunk:
    """Tests for DiffHunk."""

    def test_basic(self):
        """Test basic hunk."""
        hunk = DiffHunk(
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=6,
            lines=["@@ -10,5 +10,6 @@", " line1", "+line2", " line3"],
        )
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 10
        assert hunk.new_count == 6
        assert len(hunk.lines) == 4


class TestDiffFile:
    """Tests for DiffFile."""

    def test_basic(self):
        """Test basic diff file."""
        hunk = DiffHunk(old_start=1, old_count=1, new_start=1, new_count=1, lines=["@@ -1,1 +1,1 @@", "+new"])
        file = DiffFile(path="test.py", status="modified", hunks=[hunk])
        assert file.path == "test.py"
        assert file.status == "modified"
        assert len(file.hunks) == 1

    def test_rename(self):
        """Test renamed file."""
        file = DiffFile(path="new.py", status="renamed", old_path="old.py")
        assert file.old_path == "old.py"
        assert file.status == "renamed"


class TestDiffPane:
    """Tests for DiffPane."""

    def test_basic(self):
        """Test basic diff pane."""
        pane = DiffPane(repo_path="/repo", session_id="sess_1")
        assert pane.repo_path == "/repo"
        assert pane.session_id == "sess_1"
        assert pane.base == "HEAD"
        assert pane.files == []
        assert pane.selected_index == 0
        assert pane.mode == "docked"

    def test_scroll(self):
        """Test scrolling."""
        pane = DiffPane(repo_path="/repo", session_id="sess_1")
        file1 = DiffFile(path="a.py", status="modified")
        file2 = DiffFile(path="b.py", status="added")
        file3 = DiffFile(path="c.py", status="deleted")
        pane.files = [file1, file2, file3]

        assert pane.selected_index == 0
        pane.scroll(1)
        assert pane.selected_index == 1
        pane.scroll(1)
        assert pane.selected_index == 2
        pane.scroll(1)  # Should not exceed
        assert pane.selected_index == 2
        pane.scroll(-1)
        assert pane.selected_index == 1
        pane.scroll(-2)
        assert pane.selected_index == 0

    def test_get_selected_file(self):
        """Test getting selected file."""
        pane = DiffPane(repo_path="/repo", session_id="sess_1")
        file1 = DiffFile(path="a.py", status="modified")
        file2 = DiffFile(path="b.py", status="added")
        pane.files = [file1, file2]

        assert pane.get_selected_file() == file1
        pane.selected_index = 1
        assert pane.get_selected_file() == file2
        pane.selected_index = 5  # Out of bounds
        assert pane.get_selected_file() is None

    def test_set_mode(self):
        """Test setting mode."""
        pane = DiffPane(repo_path="/repo", session_id="sess_1")
        assert pane.mode == "docked"
        pane.set_mode("dialog")
        assert pane.mode == "dialog"
        pane.set_mode("docked")
        assert pane.mode == "docked"

    def test_to_dict(self):
        """Test serialization."""
        pane = DiffPane(repo_path="/repo", session_id="sess_1", base="main")
        file1 = DiffFile(path="a.py", status="modified")
        file2 = DiffFile(path="b.py", status="renamed", old_path="old_b.py")
        hunk = DiffHunk(old_start=1, old_count=1, new_start=1, new_count=2, lines=[])
        file2.hunks = [hunk]
        pane.files = [file1, file2]

        data = pane.to_dict()
        assert data["repo_path"] == "/repo"
        assert data["session_id"] == "sess_1"
        assert data["base"] == "main"
        assert len(data["files"]) == 2
        assert data["files"][0]["path"] == "a.py"
        assert data["files"][0]["status"] == "modified"
        assert data["files"][1]["path"] == "b.py"
        assert data["files"][1]["status"] == "renamed"
        assert data["files"][1]["old_path"] == "old_b.py"
        assert data["files"][1]["hunk_count"] == 1


class TestUIPaneManager:
    """Tests for UIPaneManager."""

    def test_create_pane(self):
        """Test creating a pane."""
        from zcoder.agent.plugin.hook_bus import HookBus
        from zcoder.agent.plugin.manager import PluginManager

        manager = PluginManager()
        bus = HookBus(manager)
        pane_manager = UIPaneManager(bus)

        # Create pane manually
        pane = DiffPane(repo_path="/repo", session_id="sess_1")
        pane_manager.panes["test"] = pane

        assert "test" in pane_manager.panes
        assert pane_manager.panes["test"].repo_path == "/repo"

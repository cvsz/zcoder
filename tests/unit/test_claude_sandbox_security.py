import os

import pytest

from zcoder.claude.tools.sandbox import SandboxViolation, check_filesystem, enforce


def test_relative_redirection_cannot_escape_sandbox(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    violation = check_filesystem("printf x > ../outside.txt", [str(root)])

    assert violation is not None
    assert "outside the sandbox" in violation


def test_relative_redirection_inside_sandbox_is_allowed(tmp_path):
    root = tmp_path / "workspace"
    nested = root / "nested"
    nested.mkdir(parents=True)

    assert check_filesystem("printf x > nested/output.txt", [str(root)]) is None


def test_mutation_command_cannot_escape_with_relative_path(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    violation = check_filesystem("cp input.txt ../outside.txt", [str(root)])

    assert violation is not None
    assert "../outside.txt" in violation


def test_enforce_blocks_relative_traversal_before_execution(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(SandboxViolation):
        enforce("printf x > ../outside.txt", cwd=str(root), allow_net=True)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not consistently available on Windows CI")
def test_redirection_through_symlink_outside_root_is_blocked(tmp_path):
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    violation = check_filesystem("printf x > escape/output.txt", [str(root)])

    assert violation is not None
    assert "outside the sandbox" in violation

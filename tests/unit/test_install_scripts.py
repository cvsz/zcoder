"""Cross-platform installer and standalone build path regression tests."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

INSTALLER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("zcoder_installer", INSTALLER_PATH)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_relative_install_destination_uses_invocation_dir(tmp_path):
    chosen = installer._selected_dir(
        "my apps/zcoder", env_name="ZCODER_VENV", default="venv", invocation_dir=tmp_path
    )
    assert chosen == tmp_path / "my apps" / "zcoder"


def test_legacy_venv_env_uses_checkout_root(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("ZCODER_VENV", "old-venv")
    assert (
        installer._selected_dir(
            None, env_name="ZCODER_VENV", default="venv", invocation_dir=tmp_path / "elsewhere"
        )
        == tmp_path / "old-venv"
    )


def test_custom_setup_installs_non_editable_package(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    repo.mkdir()
    (repo / ".env").write_text("", encoding="utf-8")
    monkeypatch.setattr(installer, "PROJECT_ROOT", repo)
    monkeypatch.setattr(installer, "_ensure_venv", lambda path: path / "bin" / "python")
    commands = []
    monkeypatch.setattr(installer, "_run", lambda *args: commands.append(tuple(map(str, args))))
    installer._setup(argparse.Namespace(install_dir="my-venv"), tmp_path)
    assert commands[1][-1] == str(repo)
    assert "-e" not in commands[1]
    assert commands[2] == (str(installer._command_in_venv(tmp_path / "my-venv", "zcoder")), "--version")


def test_default_setup_preserves_editable_install(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.setattr(installer, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("ZCODER_VENV", raising=False)
    monkeypatch.setattr(installer, "_ensure_venv", lambda path: path / "bin" / "python")
    commands = []
    monkeypatch.setattr(installer, "_run", lambda *args: commands.append(tuple(map(str, args))))
    installer._setup(argparse.Namespace(install_dir=None), tmp_path)
    assert "-e" in commands[1]
    assert str(tmp_path / "venv" / "bin" / "python") == commands[1][0]


def test_build_does_not_overwrite_existing_executable(tmp_path, monkeypatch):
    artifact = tmp_path / ("zcoder.exe" if installer.os.name == "nt" else "zcoder")
    artifact.write_text("valuable user executable", encoding="utf-8")
    monkeypatch.setattr(installer, "_ensure_venv", lambda _: pytest.fail("unexpected installation"))
    args = argparse.Namespace(dist_dir=str(tmp_path), work_dir=None, build_venv=None, force=False)
    with pytest.raises(installer.InstallError, match="Output already exists"):
        installer._build(args, tmp_path)
    assert artifact.read_text(encoding="utf-8") == "valuable user executable"


def test_build_passes_custom_output_without_deletion(tmp_path, monkeypatch):
    dist = tmp_path / "release bins"
    args = argparse.Namespace(dist_dir=str(dist), work_dir="temp-work", build_venv="temp-venv", force=False)
    monkeypatch.setattr(installer, "_ensure_venv", lambda path: path / "bin" / "python")
    commands = []

    def record(*command):
        commands.append(tuple(map(str, command)))
        if "PyInstaller" in command:
            dist.mkdir(parents=True)
            (dist / ("zcoder.exe" if installer.os.name == "nt" else "zcoder")).write_text(
                "test build", encoding="utf-8"
            )

    monkeypatch.setattr(installer, "_run", record)
    installer._build(args, tmp_path)
    pyinstaller = commands[2]
    assert "--distpath" in pyinstaller
    assert pyinstaller[pyinstaller.index("--distpath") + 1] == str(dist)
    assert commands[-1] == (
        str(dist / ("zcoder.exe" if installer.os.name == "nt" else "zcoder")),
        "--version",
    )


def test_nonempty_directory_cannot_be_replaced_as_virtualenv(tmp_path, monkeypatch):
    (tmp_path / "existing.txt").write_text("keep me", encoding="utf-8")
    monkeypatch.setattr(installer, "_run", lambda *args: pytest.fail("unexpected virtualenv creation"))
    with pytest.raises(installer.InstallError, match="Refusing to replace"):
        installer._ensure_venv(tmp_path)

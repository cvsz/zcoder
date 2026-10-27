#!/usr/bin/env python3
"""Cross-platform source installation and standalone build commands."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class InstallError(Exception):
    """An actionable, user-facing installation or build failure."""


def _path(value: str, *, relative_to: Path) -> Path:
    candidate = Path(value).expanduser()
    return (candidate if candidate.is_absolute() else relative_to / candidate).resolve()


def _python_in_venv(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _command_in_venv(directory: Path, command: str) -> Path:
    return directory / (f"Scripts/{command}.exe" if os.name == "nt" else f"bin/{command}")


def _run(*args: str | Path) -> None:
    # Invoke an explicit argument vector without shell expansion.
    subprocess.run([str(arg) for arg in args], cwd=PROJECT_ROOT, check=True)  # nosec B603


def _ensure_venv(directory: Path) -> Path:
    python = _python_in_venv(directory)
    if python.is_file():
        return python
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise InstallError(f"Refusing to replace a non-empty directory without a Python venv: {directory}")
    _run(sys.executable, "-m", "venv", directory)
    if not python.is_file():
        raise InstallError(f"Python virtual environment was not created: {directory}")
    return python


def _selected_dir(requested: str | None, *, env_name: str, default: str, invocation_dir: Path) -> Path:
    if requested:
        return _path(requested, relative_to=invocation_dir)
    # Preserve the previous meaning of relative environment variable paths.
    return _path(os.environ.get(env_name) or default, relative_to=PROJECT_ROOT)


def _validate_dotenv_path(path: Path) -> None:
    if path.is_symlink():
        raise InstallError(
            "Refusing to use a symlink for .env; use a regular file to keep credential permissions explicit."
        )
    if path.exists() and not path.is_file():
        raise InstallError("Refusing to use .env because it is not a regular file.")


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _setup(args: argparse.Namespace, invocation_dir: Path) -> None:
    dotenv = PROJECT_ROOT / ".env"
    _validate_dotenv_path(dotenv)
    venv_dir = _selected_dir(
        args.install_dir, env_name="ZCODER_VENV", default="venv", invocation_dir=invocation_dir
    )
    python = _ensure_venv(venv_dir)
    _run(python, "-m", "pip", "install", "--upgrade", "pip")
    # A custom installation must remain usable if the checkout is removed.
    command = [python, "-m", "pip", "install"]
    if args.install_dir is None:
        command.append("-e")
    command.append(PROJECT_ROOT)
    _run(*command)

    if not dotenv.exists():
        shutil.copyfile(PROJECT_ROOT / ".env.example", dotenv)
        print("Created .env from .env.example; configure provider credentials for live calls.")
    if os.name != "nt":
        dotenv.chmod(0o600)
    _run(_command_in_venv(venv_dir, "zcoder"), "--version")
    print(f"Installed ZCoder in: {venv_dir}")
    print(f"Run: {_command_in_venv(venv_dir, 'zcoder')}")


def _build(args: argparse.Namespace, invocation_dir: Path) -> None:
    dist_dir = _selected_dir(
        args.dist_dir, env_name="ZCODER_DIST_DIR", default="dist", invocation_dir=invocation_dir
    )
    work_dir = _selected_dir(
        args.work_dir,
        env_name="ZCODER_WORK_DIR",
        default="build/pyinstaller",
        invocation_dir=invocation_dir,
    )
    build_venv = _selected_dir(
        args.build_venv,
        env_name="ZCODER_BUILD_VENV",
        default=".build-venv",
        invocation_dir=invocation_dir,
    )
    artifact = dist_dir / ("zcoder.exe" if os.name == "nt" else "zcoder")
    if artifact.exists() and (not args.force or not artifact.is_file()):
        raise InstallError(f"Output already exists: {artifact}. Use --force to replace a file.")
    filesystem_roots = {Path(work_dir.anchor), Path(dist_dir.anchor), Path(build_venv.anchor)}
    if (
        work_dir == PROJECT_ROOT
        or dist_dir == PROJECT_ROOT
        or build_venv == PROJECT_ROOT
        or work_dir in filesystem_roots
        or dist_dir in filesystem_roots
        or build_venv in filesystem_roots
        or _paths_overlap(work_dir, dist_dir)
        or _paths_overlap(work_dir, build_venv)
        or _paths_overlap(dist_dir, build_venv)
    ):
        raise InstallError(
            "The work, output, and build-venv directories must be distinct, non-overlapping paths "
            "outside the repository root and filesystem roots."
        )

    python = _ensure_venv(build_venv)
    _run(python, "-m", "pip", "install", "--upgrade", "pip")
    _run(python, "-m", "pip", "install", "-e", PROJECT_ROOT, "pyinstaller")
    _run(
        python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        dist_dir,
        "--workpath",
        work_dir,
        PROJECT_ROOT / "spec" / "zcoder.spec",
    )
    if not artifact.is_file():
        raise InstallError(f"PyInstaller did not produce an executable: {artifact}")
    _run(artifact, "--version")
    print(f"Standalone executable: {artifact}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    setup = subparsers.add_parser("setup", help="Install into a selectable Python environment")
    setup.add_argument("--install-dir", metavar="PATH", help="Exact destination of the installed environment")
    build = subparsers.add_parser("build", help="Build a platform-specific standalone executable")
    build.add_argument("--dist-dir", metavar="PATH", help="Directory for the resulting executable")
    build.add_argument("--work-dir", metavar="PATH", help="Directory for intermediate build files")
    build.add_argument("--build-venv", metavar="PATH", help="Directory for the build dependencies")
    build.add_argument("--force", action="store_true", help="Allow replacing an existing executable")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required")
    try:
        if args.action == "setup":
            _setup(args, Path.cwd())
        else:
            _build(args, Path.cwd())
    except (InstallError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

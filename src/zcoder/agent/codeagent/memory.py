"""Project memory (ZCODER.md / AGENTS.md), @file mentions and the system prompt."""

from __future__ import annotations

import datetime as _dt
import os
import platform
import re
import subprocess  # nosec B404 - fixed read-only git invocations
from pathlib import Path

from zcoder.agent.codeagent.workspace import ToolError, Workspace

MEMORY_FILES = ("ZCODER.md", "AGENTS.md")
_MAX_MEMORY_CHARS = 20_000
_MENTION = re.compile(r"(?<![\w@])@([\w./\-]+)")


def zcoder_home() -> Path:
    return Path(os.getenv("ZCODER_HOME") or Path.home() / ".zcoder")


def load_project_memory(cwd: Path) -> list[tuple[str, str]]:
    """Memory files from ~/.zcoder, then ancestors of cwd (outermost first), then cwd."""
    found: list[tuple[str, str]] = []
    seen: set[Path] = set()
    candidates = [zcoder_home() / "ZCODER.md"]
    chain = [cwd, *cwd.parents]
    home = Path.home().resolve()
    for d in reversed([d for d in chain if d == cwd or (home in d.parents or d == home)]):
        candidates += [d / n for n in MEMORY_FILES]
    for path in candidates:
        try:
            real = path.resolve()
            if real in seen or not real.is_file():
                continue
            seen.add(real)
            found.append((str(path), real.read_text(encoding="utf-8", errors="replace")[:_MAX_MEMORY_CHARS]))
        except OSError:
            continue
    return found


def _git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(  # nosec B603 B607 - fixed args, no shell
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=3, check=False
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_branch(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def build_system_prompt(
    ws: Workspace, mode: str, memory: list[tuple[str, str]], tool_names: list[str]
) -> str:
    branch = git_branch(ws.root)
    status = _git(ws.root, "status", "--short")[:1500] if branch else ""
    plan_note = (
        "\nYou are in PLAN MODE: you may only read and search. Investigate, then call ExitPlanMode with a concrete "
        "step-by-step plan. Do not attempt edits or commands until the plan is approved.\n"
        if mode == "plan"
        else ""
    )
    parts = [
        "You are ZCoder, an expert software engineering agent running in the user's terminal or browser. "
        "Work autonomously, but make precise, minimal changes and never claim work is done without verifying it.",
        "# Tools\nAvailable: " + ", ".join(tool_names) + ". Rules:\n"
        "- Read a file before you Edit or Write it. Prefer Edit over Write for existing files.\n"
        "- Use Glob/Grep to find code instead of guessing paths.\n"
        "- Use Bash to run tests, linters and builds after changes, and fix what fails.\n"
        "- For tasks with 3+ steps, keep a TodoWrite list current; exactly one item in_progress.\n"
        "- If a tool is denied, do not retry the same call; adapt or ask the user.\n"
        "- Be concise. Cite file paths as path:line. Do not paste large files back at the user.",
        plan_note.strip(),
        f"# Environment\nWorking directory: {ws.root}\nPlatform: {platform.system()} {platform.machine()}\n"
        f"Date: {_dt.date.today().isoformat()}\nPermission mode: {mode}"
        + (f"\nGit branch: {branch}" if branch else "\nGit repo: no")
        + (f"\nGit status (short):\n{status}" if status else ""),
    ]
    for path, text in memory:
        parts.append(f"# Project memory ({path})\n{text.strip()}")
    return "\n\n".join(p for p in parts if p)


def expand_mentions(text: str, ws: Workspace) -> tuple[str, list[str]]:
    """Attach the content of ``@path`` mentions (files inside the workspace) to the prompt."""
    attached: list[str] = []
    blocks: list[str] = []
    for m in _MENTION.finditer(text):
        raw = m.group(1).rstrip(".,;:)")
        if raw in attached:
            continue
        try:
            path = ws.resolve(raw)
        except ToolError:
            continue
        if not path.is_file() or path.stat().st_size > 200_000:
            continue
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            continue
        ws.mark_read(path)
        attached.append(raw)
        body = data.decode("utf-8", "replace")[:20_000]
        blocks.append(f'<file path="{ws.rel(path)}">\n{body}\n</file>')
    return (text + "\n\n" + "\n".join(blocks) if blocks else text), attached


def mention_candidates(ws: Workspace, prefix: str, limit: int = 20) -> list[str]:
    """Path completions for the @-picker in both front ends."""
    from zcoder.agent.codeagent.workspace import IGNORED_DIRS

    out: list[str] = []
    prefix = prefix.lstrip("./")
    for dirpath, dirnames, filenames in os.walk(ws.root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), ws.root)
            if prefix.lower() in rel.lower():
                out.append(rel)
                if len(out) >= limit:
                    return out
    return out

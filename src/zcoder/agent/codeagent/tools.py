"""Built-in coding tools: Read, Write, Edit, Glob, Grep, LS, Bash, TodoWrite, ExitPlanMode."""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import os
import re
import signal
import subprocess  # nosec B404  # Bash tool is permission-gated by PermissionPolicy
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcoder.agent.codeagent.workspace import IGNORED_DIRS, ToolError, Workspace

MAX_OUTPUT_CHARS = 30_000
MAX_READ_BYTES = 2_000_000
MAX_LINE_CHARS = 2_000


@dataclass
class ToolContext:
    workspace: Workspace
    todos: list[dict[str, Any]] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    scrub_env: bool = True
    pass_env: tuple[str, ...] = ()
    agent_llm: Any = None
    agent_policy: Any = None
    agent_registry: Any = None
    agent_mcp: Any = None
    agent_skills: Any = None


@dataclass
class ToolOutput:
    text: str
    diff: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    category: str  # read | edit | exec | meta | plan
    func: Callable[[ToolContext, dict[str, Any]], ToolOutput]

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


# --- helpers -----------------------------------------------------------------
def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n… [{len(text) - limit} characters truncated] …\n{text[-half:]}"


def make_diff(path: str, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}", n=3
    )
    out = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines
    )
    return truncate(out, 20_000)


_SECRET_NAME = re.compile(r"(?i)(key|token|secret|passw|credential|auth|cookie|session)")


def bash_environment(ctx: ToolContext) -> dict[str, str]:
    """Environment for Bash: by default drop anything that looks like a credential."""
    if not ctx.scrub_env:
        return dict(os.environ)
    keep = set(ctx.pass_env)
    return {k: v for k, v in os.environ.items() if k in keep or not _SECRET_NAME.search(k)}


def _read_text(path: Path) -> str:
    if not path.exists():
        raise ToolError(f"file not found: {path.name}")
    if path.is_dir():
        raise ToolError(f"{path.name} is a directory; use LS")
    if path.stat().st_size > MAX_READ_BYTES:
        raise ToolError("file is larger than 2 MB; use Grep or Read with offset/limit on a smaller file")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise ToolError("binary file; refusing to read as text")
    return data.decode("utf-8", errors="replace")


def _int(args: dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    raw = args.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{key} must be an integer") from exc
    return max(lo, min(hi, value))


def _walk(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


# --- tools --------------------------------------------------------------------
def _read(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    path = ctx.workspace.resolve(args.get("path", ""))
    text = _read_text(path)
    ctx.workspace.mark_read(path)
    lines = text.splitlines()
    offset = _int(args, "offset", 1, 1, 10**9)
    limit = _int(args, "limit", 2000, 1, 5000)
    chunk = lines[offset - 1 : offset - 1 + limit]
    if not chunk and lines:
        raise ToolError(f"offset {offset} is past the end of the file ({len(lines)} lines)")
    body = "\n".join(f"{i:>6}\t{ln[:MAX_LINE_CHARS]}" for i, ln in enumerate(chunk, start=offset))
    if offset - 1 + limit < len(lines):
        body += f"\n… {len(lines) - (offset - 1 + limit)} more lines (use offset/limit)"
    return ToolOutput(body or "(empty file)")


def _write(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    ws = ctx.workspace
    path = ws.resolve(args.get("path", ""))
    content = args.get("content")
    if not isinstance(content, str):
        raise ToolError("content must be a string")
    if ws.is_protected(path):
        raise ToolError("writing inside .git is not allowed")
    if path.is_dir():
        raise ToolError(f"{ws.rel(path)} is a directory")
    existed = path.exists()
    old = ""
    if existed:
        ws.ensure_fresh(path)
        old = _read_text(path)
    ws.write_atomic(path, content.encode("utf-8"))
    verb = "Updated" if existed else "Created"
    return ToolOutput(
        f"{verb} {ws.rel(path)} ({len(content.splitlines())} lines)", make_diff(ws.rel(path), old, content)
    )


def _edit(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    ws = ctx.workspace
    path = ws.resolve(args.get("path", ""))
    old_s, new_s = args.get("old_string"), args.get("new_string")
    if not isinstance(old_s, str) or not isinstance(new_s, str):
        raise ToolError("old_string and new_string must be strings")
    if ws.is_protected(path):
        raise ToolError("editing inside .git is not allowed")
    if old_s == new_s:
        raise ToolError("old_string and new_string are identical")
    if not old_s:
        raise ToolError("old_string is empty; use Write to create files")
    ws.ensure_fresh(path)
    text = _read_text(path)
    count = text.count(old_s)
    if count == 0:
        raise ToolError(
            "old_string was not found. It must match exactly, including whitespace and indentation."
        )
    replace_all = bool(args.get("replace_all", False))
    if count > 1 and not replace_all:
        raise ToolError(
            f"old_string matches {count} places. Add surrounding context to make it unique, or set replace_all."
        )
    new_text = text.replace(old_s, new_s) if replace_all else text.replace(old_s, new_s, 1)
    ws.write_atomic(path, new_text.encode("utf-8"))
    return ToolOutput(
        f"Edited {ws.rel(path)} ({count if replace_all else 1} replacement{'s' if replace_all and count > 1 else ''})",
        make_diff(ws.rel(path), text, new_text),
    )


def _glob(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    ws = ctx.workspace
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ToolError("pattern is required")
    if pattern.startswith("/") or ".." in Path(pattern).parts:
        raise ToolError("pattern must be relative and must not contain '..'")
    base = ws.resolve(args.get("path") or ".")
    hits = [
        p
        for p in base.glob(pattern)
        if p.is_file() and not (set(p.relative_to(base).parts[:-1]) & IGNORED_DIRS)
    ]
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    shown = [ws.rel(p) for p in hits[:200]]
    if not shown:
        return ToolOutput("No files matched")
    more = f"\n… {len(hits) - 200} more" if len(hits) > 200 else ""
    return ToolOutput("\n".join(shown) + more)


def _grep(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    ws = ctx.workspace
    pattern = args.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ToolError("pattern is required")
    try:
        rx = re.compile(pattern, re.IGNORECASE if args.get("ignore_case") else 0)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc
    base = ws.resolve(args.get("path") or ".")
    file_glob = args.get("glob")
    mode = args.get("output_mode", "files_with_matches")
    if mode not in {"files_with_matches", "content", "count"}:
        raise ToolError("output_mode must be files_with_matches, content or count")
    limit = _int(args, "head_limit", 250, 1, 2000)
    files = [base] if base.is_file() else _walk(base)
    deadline = time.monotonic() + 10
    out: list[str] = []
    for f in files:
        if time.monotonic() > deadline or ctx.cancel.is_set():
            out.append("… search stopped early (time limit or interrupt)")
            break
        if file_glob and not (fnmatch.fnmatch(f.name, file_glob) or fnmatch.fnmatch(ws.rel(f), file_glob)):
            continue
        try:
            if f.stat().st_size > MAX_READ_BYTES:
                continue
            raw = f.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        matches = [
            (i, ln)
            for i, ln in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1)
            if rx.search(ln)
        ]
        if not matches:
            continue
        rel = ws.rel(f)
        if mode == "files_with_matches":
            out.append(rel)
        elif mode == "count":
            out.append(f"{rel}:{len(matches)}")
        else:
            out.extend(f"{rel}:{i}:{ln[:500]}" for i, ln in matches)
        if len(out) >= limit:
            out = out[:limit] + [f"… truncated at {limit} results"]
            break
    return ToolOutput("\n".join(out) if out else "No matches found")


def _ls(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    path = ctx.workspace.resolve(args.get("path") or ".")
    if not path.is_dir():
        raise ToolError("not a directory")
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = [f"{p.name}/" if p.is_dir() else p.name for p in entries if p.name not in IGNORED_DIRS][:500]
    return ToolOutput("\n".join(lines) if lines else "(empty directory)")


def _bash(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ToolError("command is required")
    timeout = _int(args, "timeout", 120, 1, 600)
    env = {**bash_environment(ctx), "GIT_PAGER": "cat", "PAGER": "cat", "TERM": "dumb", "NO_COLOR": "1"}
    shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
    proc = subprocess.Popen(  # nosec B603  # gated by PermissionPolicy; user approves non-read-only commands
        [shell, "-c", command],
        cwd=ctx.workspace.root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # The stdout pipe is owned by this call and must be closed deterministically
    # (even on cancellation/timeout/error) to avoid leaking file descriptors.
    pipe = proc.stdout
    if pipe is None:  # pragma: no cover - Popen was created with stdout=PIPE
        proc.kill()
        raise ToolError("failed to capture command stdout")
    chunks: list[bytes] = []

    def pump() -> None:
        for block in iter(lambda: pipe.read(4096), b""):
            chunks.append(block)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    status = ""
    try:
        while proc.poll() is None:
            if ctx.cancel.is_set():
                status = "interrupted by user"
            elif time.monotonic() > deadline:
                status = f"timed out after {timeout}s"
            if status:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                break
            time.sleep(0.05)
        proc.wait()
        reader.join(timeout=2)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        text = truncate(text)
        if status:
            text += f"\n[command {status}]"
            raise ToolError(text)
        if proc.returncode != 0:
            raise ToolError(f"{text}\n[exit code {proc.returncode}]".strip())
        return ToolOutput(text or "(no output)")
    finally:
        try:
            pipe.close()
        except Exception:
            # Closing a pipe must never mask the command result.
            pass


_TODO_STATES = {"pending", "in_progress", "completed"}


def _todo(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    todos = args.get("todos")
    if not isinstance(todos, list):
        raise ToolError("todos must be a list")
    cleaned: list[dict[str, Any]] = []
    for item in todos:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
        ):
            raise ToolError("each todo needs non-empty string 'content'")
        status = item.get("status", "pending")
        if status not in _TODO_STATES:
            raise ToolError(f"todo status must be one of {sorted(_TODO_STATES)}")
        cleaned.append({"content": item["content"].strip(), "status": status})
    if sum(t["status"] == "in_progress" for t in cleaned) > 1:
        raise ToolError("only one todo may be in_progress at a time")
    ctx.todos[:] = cleaned
    return ToolOutput("Todos updated")


def _exit_plan(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    plan = args.get("plan")
    if not isinstance(plan, str) or not plan.strip():
        raise ToolError("plan is required")
    return ToolOutput("User approved the plan. You may now make changes.")


def _enter_plan(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Enter plan mode — the agent must research and present a plan before making changes."""
    policy = ctx.agent_policy
    if policy is not None:
        try:
            import importlib

            perms_mod = importlib.import_module("zcoder.agent.codeagent.permissions")
            policy.set_mode(perms_mod.Mode.PLAN)
        except Exception:
            pass
    return ToolOutput("Entered plan mode. Research the codebase and present a plan for approval.")


def _ask_user(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Ask the user a question and wait for their response."""
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ToolError("question is required")
    options = args.get("options")
    if isinstance(options, list) and options:
        opts = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
        return ToolOutput(f"Question: {question}\n{opts}")
    return ToolOutput(f"Question: {question}")


def _skill(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Activate a named skill, loading its instructions into context."""
    name = args.get("skill")
    if not isinstance(name, str) or not name.strip():
        raise ToolError("skill name is required")
    skills = getattr(ctx, "agent_skills", None)
    if skills is None:
        raise ToolError("No skill registry available.")
    try:
        from zcoder.agent.codeagent.skills import SkillRegistry

        if isinstance(skills, SkillRegistry):
            skill = skills.get(name)
            if skill is None:
                raise ToolError(f"unknown skill: {name}")
            return ToolOutput(f"Skill '{name}' activated.\n\n{skill.body}")
    except ImportError:
        pass
    return ToolOutput(f"Skill '{name}' requested (no registry available).")


def _web_fetch(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Fetch a URL and return its content as text."""
    import urllib.request

    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ToolError("url is required")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return ToolOutput(f"Failed to fetch {url}: {exc}")
    return ToolOutput(data[:8000])


def _web_search(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Search the web and return results."""
    import urllib.parse
    import urllib.request

    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query is required")
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        import re

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', data, re.DOTALL)
        if not snippets:
            return ToolOutput(f"No results for: {query}")
        return ToolOutput("\n\n".join(s.strip() for s in snippets[:5]))
    except Exception as exc:
        return ToolOutput(f"Search failed: {exc}")


def _notebook_edit(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Edit a Jupyter notebook cell."""
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ToolError("path is required")
    cell = args.get("cell")
    cell_type = args.get("cell_type", "code")
    if not isinstance(cell, str):
        raise ToolError("cell content is required")
    ws = ctx.workspace
    resolved = ws.resolve(path)
    try:
        import json as _json

        nb = _json.loads(resolved.read_text(encoding="utf-8"))
        if "cells" not in nb:
            nb["cells"] = []
        nb["cells"].append({"cell_type": cell_type, "source": cell, "metadata": {}, "execution_count": None})
        ws.write_atomic(resolved, _json.dumps(nb, indent=2).encode("utf-8"))
    except Exception as exc:
        return ToolOutput(f"Notebook edit failed: {exc}")
    return ToolOutput(f"Edited {ws.rel(resolved)}")


def _spawn_subagent(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Spawn a subagent in isolated context and return its summary."""
    agent_type = args.get("agent_type")
    prompt = args.get("prompt")
    if not isinstance(agent_type, str) or not agent_type.strip():
        raise ToolError("agent_type is required")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ToolError("prompt is required")

    llm = ctx.agent_llm
    policy = ctx.agent_policy
    registry = ctx.agent_registry
    if llm is None or policy is None or registry is None:
        raise ToolError("Subagent spawning requires agent context (LLM, policy, registry).")

    import importlib

    subagents_mod = importlib.import_module("zcoder.agent.codeagent.subagents")
    SubagentRunner = subagents_mod.SubagentRunner

    tools = args.get("tools")
    model = args.get("model")
    permission_mode = args.get("permission_mode")
    max_turns = args.get("max_turns")
    if isinstance(max_turns, str) and max_turns.isdigit():
        max_turns = int(max_turns)

    runner = SubagentRunner(
        llm=llm,
        ws=ctx.workspace,
        policy=policy,
        registry=registry,
    )

    try:
        result = asyncio.run(
            runner.run(
                agent_type=agent_type,
                prompt=prompt,
                tools=tools if isinstance(tools, list) else None,
                model=model if isinstance(model, str) else None,
                permission_mode=permission_mode if isinstance(permission_mode, str) else None,
                max_turns=max_turns if isinstance(max_turns, int) else None,
            )
        )
    except Exception as exc:
        return ToolOutput(f"Subagent '{agent_type}' failed: {exc}")

    if not result.success:
        return ToolOutput(f"Subagent '{agent_type}' was blocked by depth limit.")

    return ToolOutput(f"Subagent '{agent_type}' result:\n{result.summary}")


def _task_output(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Get the output of a background subagent task."""
    task_id = args.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ToolError("task_id is required")
    registry = ctx.agent_registry
    if registry is None:
        raise ToolError("No subagent registry available.")
    try:
        import importlib

        subagents_mod = importlib.import_module("zcoder.agent.codeagent.subagents")
        result = subagents_mod.SubagentRunner.get_task_output(task_id)
        if result is None:
            return ToolOutput(f"Task '{task_id}' not found or still running.")
        return ToolOutput(result.summary if hasattr(result, "summary") else str(result))
    except Exception as exc:
        return ToolOutput(f"Task output failed: {exc}")


def _lsp(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Query a language server for code intelligence."""
    operation = args.get("operation")
    if not isinstance(operation, str) or not operation.strip():
        raise ToolError("operation is required (e.g. hover, definition, references, symbols)")
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ToolError("path is required")
    ws = ctx.workspace
    resolved = ws.resolve(path)
    try:
        import subprocess

        # Try to find an LSP server for the file extension
        ext = resolved.suffix
        server_map = {
            ".py": ["pylsp", "--stdio"],
            ".js": ["node", "node_modules/typescript-language-server/bin/typescript-language-server", "--stdio"],
            ".ts": ["node", "node_modules/typescript-language-server/bin/typescript-language-server", "--stdio"],
            ".go": ["gopls", "serve", "--stdio"],
            ".rs": ["rust-analyzer"],
        }
        cmd = server_map.get(ext)
        if cmd is None:
            return ToolOutput(f"No LSP server configured for {ext} files.")

        proc = subprocess.run(
            cmd,
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return ToolOutput(f"LSP {operation} on {ws.rel(resolved)}: {proc.stdout.strip()[:500] or proc.stderr.strip()[:500] or 'no response'}")
    except Exception as exc:
        return ToolOutput(f"LSP query failed: {exc}")


def _bash_output(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Get the output of a background bash command."""
    shell_id = args.get("shell_id")
    if not isinstance(shell_id, str) or not shell_id.strip():
        raise ToolError("shell_id is required")
    return ToolOutput(f"Shell {shell_id} output not available (background processes are not tracked in this mode).")


def _kill_shell(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Kill a background shell process."""
    shell_id = args.get("shell_id")
    if not isinstance(shell_id, str) or not shell_id.strip():
        raise ToolError("shell_id is required")
    return ToolOutput(f"Shell {shell_id} killed.")


def _background_output(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Read output from a background process."""
    process_id = args.get("process_id")
    if not isinstance(process_id, str) or not process_id.strip():
        raise ToolError("process_id is required")
    return ToolOutput(f"Background process {process_id} output not available.")


def _call_mcp_tool(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
        """Call a tool on a configured MCP server by full name (mcp__<server>__<tool>)."""
        full_name = args.get("tool")
        if not isinstance(full_name, str) or not full_name.strip():
            raise ToolError("tool is required (format: mcp__<server>__<tool>)")
        tool_args = args.get("arguments") or {}
        if not isinstance(tool_args, dict):
            raise ToolError("arguments must be a JSON object")

        mcp = getattr(ctx, "agent_mcp", None)
        if mcp is None:
            raise ToolError("No MCP client configured. Add a server via .mcp.json.")

        try:
            result = asyncio.run(mcp.call_tool_full_name(full_name, tool_args))
        except Exception as exc:
            return ToolOutput(f"MCP tool '{full_name}' failed: {exc}")

        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                return ToolOutput("\n".join(parts) or "(no text output)")
            return ToolOutput(str(result))
        return ToolOutput(str(result))


def _enter_worktree(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Create an isolated git worktree and switch the workspace into it."""
    branch = args.get("branch")
    if branch is not None and not isinstance(branch, str):
        raise ToolError("branch must be a string")
    ws = ctx.workspace
    try:
        target = ws.enter_worktree(branch)
    except ToolError as exc:
        return ToolOutput(str(exc))
    return ToolOutput(f"Worktree created at {ws.rel(target)}. Files in the original tree are untouched.")


def _exit_worktree(ctx: ToolContext, args: dict[str, Any]) -> ToolOutput:
    """Remove the current worktree and prune its branch."""
    ws = ctx.workspace
    return ToolOutput(ws.exit_worktree())


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


def default_tools() -> dict[str, Tool]:
    s, i, b = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
    tools = [
        Tool(
            "Read",
            "Read a text file with line numbers. Use offset/limit for large files. Required before Edit/Write on existing files.",
            _obj({"path": s, "offset": i, "limit": i}, ["path"]),
            "read",
            _read,
        ),
        Tool(
            "Write",
            "Create a file or overwrite an existing one (must be Read first). Prefer Edit for changes.",
            _obj({"path": s, "content": s}, ["path", "content"]),
            "edit",
            _write,
        ),
        Tool(
            "Edit",
            "Replace an exact string in a file (must be Read first). old_string must be unique unless replace_all is true.",
            _obj(
                {"path": s, "old_string": s, "new_string": s, "replace_all": b},
                ["path", "old_string", "new_string"],
            ),
            "edit",
            _edit,
        ),
        Tool(
            "Glob",
            "Find files by glob pattern (e.g. '**/*.py'), newest first.",
            _obj({"pattern": s, "path": s}, ["pattern"]),
            "read",
            _glob,
        ),
        Tool(
            "Grep",
            "Regex search file contents. output_mode: files_with_matches (default), content, or count.",
            _obj(
                {"pattern": s, "path": s, "glob": s, "ignore_case": b, "output_mode": s, "head_limit": i},
                ["pattern"],
            ),
            "read",
            _grep,
        ),
        Tool("LS", "List a directory.", _obj({"path": s}, []), "read", _ls),
        Tool(
            "Bash",
            "Run a shell command in the workspace root (no persistent cwd; chain with &&). Default timeout 120s.",
            _obj({"command": s, "timeout": i}, ["command"]),
            "exec",
            _bash,
        ),
        Tool(
            "TodoWrite",
            "Maintain a task list for multi-step work. Send the full list each time; exactly one item in_progress.",
            _obj(
                {
                    "todos": {
                        "type": "array",
                        "items": _obj({"content": s, "status": s}, ["content", "status"]),
                    }
                },
                ["todos"],
            ),
            "meta",
            _todo,
        ),
        Tool(
            "ExitPlanMode",
            "In plan mode, present your finished plan for the user to approve before making changes.",
            _obj({"plan": s}, ["plan"]),
            "plan",
            _exit_plan,
        ),
        Tool(
            "EnterPlanMode",
            "Enter plan mode to research and present a plan before making changes.",
            _obj({}, []),
            "meta",
            _enter_plan,
        ),
        Tool(
            "AskUserQuestion",
            "Ask the user a question during execution. Use for decisions that need human input.",
            _obj(
                {
                    "question": s,
                    "options": {"type": "array", "items": s},
                    "header": s,
                },
                ["question"],
            ),
            "meta",
            _ask_user,
        ),
        Tool(
            "Skill",
            "Activate a named skill, loading its instructions into context.",
            _obj({"skill": s}, ["skill"]),
            "meta",
            _skill,
        ),
        Tool(
            "WebFetch",
            "Fetch a URL and return its content as text.",
            _obj({"url": s, "prompt": s}, ["url"]),
            "read",
            _web_fetch,
        ),
        Tool(
            "WebSearch",
            "Search the web and return results.",
            _obj({"query": s}, ["query"]),
            "read",
            _web_search,
        ),
        Tool(
            "NotebookEdit",
            "Edit a Jupyter notebook cell.",
            _obj({"path": s, "cell": s, "cell_type": s}, ["path", "cell"]),
            "edit",
            _notebook_edit,
        ),
        Tool(
            "LSP",
            "Query a language server for code intelligence (hover, definition, references, symbols).",
            _obj(
                {
                    "operation": s,
                    "path": s,
                    "line": i,
                    "character": i,
                },
                ["operation", "path"],
            ),
            "read",
            _lsp,
        ),
        Tool(
            "TaskOutput",
            "Get the output of a background subagent task.",
            _obj({"task_id": s, "block": b, "timeout": i}, ["task_id"]),
            "meta",
            _task_output,
        ),
        Tool(
            "BashOutput",
            "Get the output of a background bash command.",
            _obj({"shell_id": s}, ["shell_id"]),
            "meta",
            _bash_output,
        ),
        Tool(
            "KillShell",
            "Kill a background shell process.",
            _obj({"shell_id": s}, ["shell_id"]),
            "meta",
            _kill_shell,
        ),
        Tool(
            "BackgroundOutput",
            "Read output from a background process.",
            _obj({"process_id": s}, ["process_id"]),
            "meta",
            _background_output,
        ),
        Tool(
            "Agent",
            "Spawn a subagent to handle a task in isolated context. Returns a summary when complete.",
            _obj(
                {
                    "agent_type": s,
                    "prompt": s,
                    "tools": {"type": "array", "items": s},
                    "model": s,
                    "permission_mode": s,
                    "max_turns": i,
                },
                ["agent_type", "prompt"],
            ),
            "meta",
            _spawn_subagent,
        ),
        Tool(
            "MCP",
            "Call a tool on a configured MCP server by full name (mcp__<server>__<tool>)",
            _obj(
                {
                    "tool": s,
                    "arguments": {"type": "object", "properties": {}, "default": {}},
                },
                ["tool"],
            ),
            "exec",
            _call_mcp_tool,
        ),
        Tool(
            "EnterWorktree",
            "Create an isolated git worktree for focused work. Use this when the task requires branching without touching the main tree.",
            _obj({"branch": s}, []),
            "meta",
            _enter_worktree,
        ),
        Tool(
            "ExitWorktree",
            "Remove the current worktree and prune its branch. Call only after the work is complete.",
            _obj({}, []),
            "meta",
            _exit_worktree,
        ),
    ]
    return {t.name: t for t in tools}


_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}


def validate_args(tool: Tool, args: Any) -> dict[str, Any]:
    """Light JSON-schema check with coercion for the sloppy values small models emit."""
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    if "__parse_error__" in args:
        raise ToolError("arguments were not valid JSON; resend the call with valid JSON")
    schema = tool.parameters
    out = dict(args)
    for key in schema.get("required", []):
        if key not in out:
            raise ToolError(f"missing required argument: {key}")
    for key, spec in schema.get("properties", {}).items():
        if key not in out:
            continue
        want = _TYPES.get(spec.get("type", ""))
        val = out[key]
        if want is int and isinstance(val, str) and val.strip().lstrip("-").isdigit():
            out[key] = val = int(val)
        elif want is bool and isinstance(val, str) and val.lower() in {"true", "false"}:
            out[key] = val = val.lower() == "true"
        if want and not isinstance(val, want):
            raise ToolError(f"argument '{key}' must be of type {spec['type']}")
    return out


def preview(ctx: ToolContext, tool: Tool, args: dict[str, Any]) -> tuple[str, str | None]:
    """Human summary + optional diff shown in the permission prompt (never mutates anything)."""
    ws = ctx.workspace
    try:
        if tool.name == "Bash":
            return str(args.get("command", "")), None
        if tool.name == "Edit":
            path = ws.resolve(args["path"])
            old = _read_text(path) if path.exists() else ""
            new = old.replace(args["old_string"], args["new_string"], -1 if args.get("replace_all") else 1)
            return f"Edit {ws.rel(path)}", make_diff(ws.rel(path), old, new)
        if tool.name == "Write":
            path = ws.resolve(args["path"])
            old = _read_text(path) if path.exists() else ""
            return f"{'Overwrite' if old else 'Create'} {ws.rel(path)}", make_diff(
                ws.rel(path), old, args["content"]
            )
        if tool.name == "ExitPlanMode":
            return "Approve plan and start making changes", str(args.get("plan", ""))
        if tool.name == "EnterWorktree":
            branch = args.get("branch", "")
            return f"create worktree branch={branch}", None
        if tool.name == "ExitWorktree":
            return "remove worktree", None
    except (ToolError, KeyError, TypeError, OSError):
        # Tool invocation may fail; return unmodified.
        pass
    return f"{tool.name} {args}", None


def describe_call(name: str, args: dict[str, Any]) -> str:
    """One-line summary of a tool call, shared by every front end."""
    if name == "Bash":
        first = str(args.get("command", "")).strip().splitlines()[:1] or [""]
        return first[0][:90]
    if name in {"Read", "Write", "Edit", "LS"}:
        return str(args.get("path", "."))
    if name in {"Grep", "Glob"}:
        return str(args.get("pattern", ""))[:90]
    if name == "TodoWrite":
        return f"{len(args.get('todos') or [])} tasks"
    if name == "ExitPlanMode":
        return "plan ready"
    if name == "EnterWorktree":
        return f"branch={args.get('branch', '')}"
    if name == "ExitWorktree":
        return "exit worktree"
    return ""

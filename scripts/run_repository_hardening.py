#!/usr/bin/env python3
"""Run the one-shot hardening migration with robust security rewrites."""

from __future__ import annotations

import apply_repository_hardening as migration

EXEC_BLOCKS = {
    "src/zcoder/claude/integrations/excel.py": (
        """            exec(compile(code, "<excel-turn>", "exec"), {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns)""",
        """            execute_restricted_code(code, {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns, filename="<excel-turn>")""",
    ),
    "src/zcoder/claude/integrations/powerpoint.py": (
        """            exec(compile(code, "<pptx-turn>", "exec"), {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns)""",
        """            execute_restricted_code(code, {"__builtins__": {
                "len": len, "range": range, "sum": sum, "min": min, "max": max,
                "round": round, "sorted": sorted, "list": list, "dict": dict,
                "str": str, "int": int, "float": float, "bool": bool,
                "enumerate": enumerate, "zip": zip, "abs": abs,
            }}, local_ns, filename="<pptx-turn>")""",
    ),
}


def create_security_helpers() -> None:
    migration.write(
        "src/zcoder/core/safe_io.py",
        '''"""Validated network I/O helpers used by ZCoder integrations."""
from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _target_url(target: Any) -> str:
    return str(getattr(target, "full_url", target))


def validate_http_url(target: Any) -> str:
    """Require an absolute HTTP(S) URL before opening a network resource."""
    url = _target_url(target)
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise ValueError("network URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not permitted")
    return url


def safe_urlopen(target: Any, *, timeout: float = 30):
    """Open only a validated absolute HTTP(S) URL."""
    validate_http_url(target)
    return urllib.request.urlopen(target, timeout=timeout)  # nosec B310 -- HTTP(S) and authority validated above
''',
    )
    migration.write(
        "src/zcoder/core/safe_subprocess.py",
        '''"""Explicit subprocess capability boundaries.

Direct commands execute as argv without shell expansion. Callers that are
intentionally user-configurable shell capabilities (Bash/status-line/hooks)
use an explicit platform interpreter while Python itself keeps shell=False.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any, Sequence, Union

Command = Union[str, Sequence[str]]


def command_argv(command: Command) -> list:
    """Convert a direct command to argv without invoking a shell."""
    if isinstance(command, str):
        argv = shlex.split(command, posix=os.name != "nt")
    else:
        argv = [str(part) for part in command]
    if not argv:
        raise ValueError("command must not be empty")
    return argv


def shell_argv(command: str) -> list:
    """Return an explicit shell interpreter argv for an intentional shell capability."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("shell command must be a non-empty string")
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
    return ["/bin/sh", "-c", command]


def run_command(command: Command, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a direct executable/argv command without implicit shell parsing."""
    kwargs.pop("shell", None)
    return subprocess.run(command_argv(command), shell=False, **kwargs)


def run_shell_command(command: str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run an explicitly declared shell capability through a fixed interpreter argv."""
    kwargs.pop("shell", None)
    return subprocess.run(shell_argv(command), shell=False, **kwargs)
''',
    )
    migration.write(
        "src/zcoder/core/restricted_exec.py",
        '''"""AST policy for narrowly scoped model-generated Python snippets.

This is defense in depth, not an OS sandbox. Arbitrary untrusted execution
belongs in the dedicated ZCoder sandbox runtime.
"""
from __future__ import annotations

import ast
from typing import Any, Mapping, MutableMapping

_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.With,
    ast.AsyncWith,
    ast.While,
)
_FORBIDDEN_NAMES = frozenset({
    "__import__", "breakpoint", "compile", "delattr", "dir", "eval", "exec",
    "getattr", "globals", "help", "input", "locals", "open", "setattr", "type", "vars",
})


class RestrictedCodeError(ValueError):
    """Raised when generated code crosses the restricted execution policy."""


class _PolicyVisitor(ast.NodeVisitor):
    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _FORBIDDEN_NODES):
            raise RestrictedCodeError(f"disallowed syntax: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_") or node.id in _FORBIDDEN_NAMES:
            raise RestrictedCodeError(f"disallowed name: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise RestrictedCodeError(f"disallowed attribute: {node.attr}")
        self.generic_visit(node)


def execute_restricted_code(
    code: str,
    globals_ns: Mapping[str, Any],
    locals_ns: MutableMapping[str, Any],
    *,
    filename: str = "<generated>",
) -> None:
    """Validate then execute a small capability-scoped Python snippet."""
    tree = ast.parse(code, filename=filename, mode="exec")
    _PolicyVisitor().visit(tree)
    compiled = compile(tree, filename, "exec")
    exec(compiled, dict(globals_ns), locals_ns)  # nosec B102 -- AST policy and caller capabilities enforced above
''',
    )
    migration.write(
        "src/zcoder/core/temp_paths.py",
        '''"""Cross-platform temporary-directory helpers."""
from __future__ import annotations

import tempfile
from pathlib import Path


def default_temp_dir(name: str) -> str:
    parts = Path(name).parts
    if not name or any(segment in {"..", "."} for segment in parts):
        raise ValueError("temporary directory name must be a simple relative name")
    if Path(name).is_absolute():
        raise ValueError("temporary directory name must be relative")
    return str(Path(tempfile.gettempdir()) / name)
''',
    )


def _replace(path: str, old: str, new: str, import_line: str) -> None:
    text = migration.read(path)
    if old not in text:
        raise RuntimeError(f"expected shell block not found in {path}: {old[:80]!r}")
    text = text.replace(old, new, 1)
    text = migration.add_import(text, import_line)
    migration.write(path, text)


def harden_shell_calls() -> None:
    shell_import = "from zcoder.core.safe_subprocess import run_shell_command"
    direct_import = "from zcoder.core.safe_subprocess import run_command"

    _replace(
        "src/zcoder/claude/capabilities/code.py",
        """                result = subprocess.run(
                    cmd, shell=True, input=stdin_data,
                    capture_output=True, text=True, timeout=30, env=env,
                )""",
        """                result = run_shell_command(
                    cmd, input=stdin_data,
                    capture_output=True, text=True, timeout=30, env=env,
                )""",
        shell_import,
    )
    _replace(
        "src/zcoder/claude/capabilities/code.py",
        """                r = subprocess.run(cmd, shell=True, cwd=cwd,
                                   capture_output=True, text=True, timeout=timeout)""",
        """                r = run_shell_command(cmd, cwd=cwd,
                                   capture_output=True, text=True, timeout=timeout)""",
        shell_import,
    )
    _replace(
        "src/zcoder/claude/integrations/git.py",
        """    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=30)""",
        """    r = run_command(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)""",
        direct_import,
    )
    _replace(
        "src/zcoder/claude/enterprise/settings.py",
        """            r = subprocess.run(
                sl["command"], shell=True,
                input=json.dumps(session_state),
                capture_output=True, text=True, timeout=5,
            )""",
        """            r = run_shell_command(
                sl["command"],
                input=json.dumps(session_state),
                capture_output=True, text=True, timeout=5,
            )""",
        shell_import,
    )
    _replace(
        "src/zcoder/claude/orchestration/sessions.py",
        """        r = subprocess.run(f'git log --since="{since_iso}" --oneline',
                          shell=True, cwd=cwd, capture_output=True, text=True, timeout=5)""",
        """        r = run_command(["git", "log", f"--since={since_iso}", "--oneline"],
                          cwd=cwd, capture_output=True, text=True, timeout=5)""",
        direct_import,
    )
    _replace(
        "src/zcoder/claude/enterprise/hooks_perms.py",
        """                p = subprocess.run(h.command, shell=True, capture_output=True,
                                   text=True, timeout=30, env=env)""",
        """                p = run_shell_command(h.command, capture_output=True,
                                   text=True, timeout=30, env=env)""",
        shell_import,
    )


def harden_generated_code() -> None:
    for path, (old, new) in EXEC_BLOCKS.items():
        text = migration.read(path)
        if old not in text:
            raise RuntimeError(f"expected generated-code block not found in {path}")
        text = text.replace(old, new, 1)
        text = migration.add_import(text, "from zcoder.core.restricted_exec import execute_restricted_code")
        migration.write(path, text)


def main() -> None:
    migration.create_security_helpers = create_security_helpers
    migration.harden_shell_calls = harden_shell_calls
    migration.harden_generated_code = harden_generated_code
    migration.main()


if __name__ == "__main__":
    main()

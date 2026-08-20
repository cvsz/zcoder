"""
security.py — Input validation and security controls

Centralizes the checks that were previously either missing or duplicated
ad hoc across claude_files.py, claude_code_exec.py, claude_sandbox.py,
projects.py, and artifacts.py — every module that takes a user-supplied
path or writes files to disk. Import from here instead of re-implementing
path checks locally.

Threat model covered:
- Path traversal / arbitrary file read-write (`../../etc/passwd`, absolute
  paths escaping an intended project/artifact directory, symlink escapes).
- Secrets accidentally echoed back to the user or written to disk (API
  keys pasted into a prompt, `.env` contents included in a file upload).
- Oversized input (a multi-GB file handed to --file / --file-upload
  exhausting memory before any API call is made).
- Unvalidated shell/URL schemes reaching url-fetch-style tools.

Not covered here (out of scope for a CLI security module): sandboxing of
arbitrary code the model asks to execute — see claude_sandbox.py, which
already delegates that to Anthropic's hosted code-execution tool rather
than running anything locally.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from zcoder.core.exceptions import SecurityError, ValidationError

# ── Path safety ──────────────────────────────────────────────────────────

MAX_FILE_SIZE_BYTES = int(os.getenv("ZCODER_MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024))  # 25 MB default


def safe_resolve(path: str | os.PathLike, base_dir: str | os.PathLike) -> Path:
    """Resolve ``path`` against ``base_dir`` and enforce containment.

    Both paths are canonicalized with ``realpath`` so traversal and symlink
    escapes are resolved before the boundary check. The separator-aware
    prefix check also rejects sibling-prefix confusion such as
    ``/safe/workspace-evil`` when the trusted root is ``/safe/workspace``.
    """
    base = os.path.realpath(os.path.expanduser(os.fspath(base_dir)))
    raw_path = os.fspath(path)
    candidate = os.path.realpath(raw_path if os.path.isabs(raw_path) else os.path.join(base, raw_path))
    base_prefix = base if base.endswith(os.sep) else base + os.sep
    if candidate != base and not candidate.startswith(base_prefix):
        raise SecurityError(
            "Path escapes the allowed base directory",
            details={"path": str(path), "base_dir": str(base)},
        )
    return Path(candidate)


def check_file_size(path: str | os.PathLike, max_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    size = os.path.getsize(path)
    if size > max_bytes:
        raise ValidationError(
            f"File too large ({size} bytes > {max_bytes} byte limit)",
            details={"path": str(path), "size": size, "limit": max_bytes},
        )


# ── Secret detection ─────────────────────────────────────────────────────

_SECRET_LIKE = re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}")


def contains_secret(text: str) -> bool:
    return bool(text) and bool(_SECRET_LIKE.search(text))


def assert_no_secret(text: str, *, context: str = "input") -> None:
    """Raise if ``text`` looks like it contains a live API key."""
    if contains_secret(text):
        raise SecurityError(f"Refusing to write {context}: looks like it contains an API key")


# ── URL / scheme validation ──────────────────────────────────────────────

_ALLOWED_SCHEMES = ("https",)


def validate_url(url: str, *, allowed_schemes: tuple[str, ...] = _ALLOWED_SCHEMES) -> None:
    """Reject non-HTTPS schemes before URL fetch/download code paths."""
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme not in allowed_schemes:
        raise SecurityError(
            f"URL scheme '{scheme or '(none)'}' is not allowed",
            details={"url": url},
        )


# ── Generic input validation ─────────────────────────────────────────────

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._\- ]{1,200}$")


def validate_name(name: str, *, field: str = "name") -> str:
    """Validate a user-supplied identifier used to build a filesystem path."""
    if not name or not _SAFE_NAME.match(name):
        raise ValidationError(
            f"Invalid {field}: only letters, numbers, spaces, '.', '_', '-' are allowed",
            details={field: name},
        )
    if ".." in name or "/" in name or "\\" in name:
        raise ValidationError(
            f"Invalid {field}: path separators are not allowed",
            details={field: name},
        )
    return name


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable consistently across the codebase."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")

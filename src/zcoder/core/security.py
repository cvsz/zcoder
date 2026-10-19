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
- Non-regular files (FIFOs, device nodes, sockets) and binary content
  reaching text-reading tools: ``read_text`` on a workspace FIFO blocks
  the agent forever; decoding an image or spreadsheet into text floods
  the model context with mojibake.
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


# ── Bounded text reads ───────────────────────────────────────────────────

# Extensions that must never be decoded as text into a model context.
# The .xlsm/.parquet/.epub/.heic entries mirror the claude-code fix of
# 2.1.3xx; the remainder covers the other container/media/data formats
# a coding workspace realistically accumulates.
BINARY_FILE_EXTENSIONS = frozenset(
    {
        ".epub",
        ".gz",
        ".bz2",
        ".xz",
        ".zst",
        ".7z",
        ".zip",
        ".jar",
        ".rar",
        ".heic",
        ".tiff",
        ".bmp",
        ".webp",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".flac",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".ppt",
        ".pptx",
        ".sqlite",
        ".db",
        ".class",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".parquet",
        ".pyc",
    }
)

# A bounded prefix covers every caller whose output is sliced further
# (the code-agent Read caps at 8000 chars); nothing justifies loading a
# multi-gigabyte file behind that slice.
READ_PREFIX_BYTES_DEFAULT = 1 * 1024 * 1024  # 1 MiB


def read_text_prefix(
    path: str | os.PathLike,
    *,
    max_bytes: int = READ_PREFIX_BYTES_DEFAULT,
    max_chars: int | None = None,
) -> str:
    """Read at most ``max_bytes`` of a *text* file, refusing anything unsafe.

    Fail-closed rules (Upgrade-55, parity workstream W4):

    - the path must be a *regular* file — a FIFO, device node, socket, or
      directory is refused by ``stat`` before any descriptor is opened,
      so a workspace FIFO can no longer block the agent forever;
    - only the first ``max_bytes`` bytes are ever read — a multi-GB
      input can no longer be loaded wholesale into memory behind a small
      character slice; a truncation marker naming the true size is
      appended when the file was cut short;
    - known binary extensions and NUL-bearing content are refused as
      binary instead of being decoded into mojibake context.

    ``max_chars`` additionally caps the returned text (after the
    truncation marker is placed), matching the code-agent Read's
    8000-character context budget without losing the marker.
    """
    from stat import S_ISREG

    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in BINARY_FILE_EXTENSIONS:
        raise ValidationError(
            f"Refusing to read binary file {p.name} as text",
            details={"path": str(p), "suffix": suffix},
        )
    st = p.stat()
    if not S_ISREG(st.st_mode):
        kind = "directory" if os.path.isdir(p) else "non-regular file (pipe/device/socket)"
        raise ValidationError(
            f"Refusing to read {kind}: {p.name}",
            details={"path": str(p), "mode": oct(st.st_mode)},
        )
    with p.open("rb") as fh:
        prefix = fh.read(max_bytes + 1)
    truncated = len(prefix) > max_bytes
    prefix = prefix[:max_bytes]
    if b"\x00" in prefix:
        raise ValidationError(
            f"Refusing to read {p.name}: binary content (NUL bytes)",
            details={"path": str(p), "suffix": suffix, "bytes": len(prefix)},
        )
    text = prefix.decode("utf-8", errors="replace")
    if truncated:
        marker = f"\n[TRUNCATED — showing first {max_bytes} bytes of {st.st_size}-byte file]"
        budget = (max_chars if max_chars is not None else len(text) + len(marker)) - len(marker)
        text = text[: max(0, budget)] + marker
    elif max_chars is not None and len(text) > max_chars:
        text = text[:max_chars]
    return text


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


# ── Child-process environment isolation ─────────────────────────────────

_SECRET_ENV_SUFFIXES = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PASSPHRASE",
    "DSN",
)

_SECRET_ENV_NAMES = frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_SECRET",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "DATABASE_URL",
        "GIT_ASKPASS",
        "PGPASSWORD",
        "SSH_ASKPASS",
        "SSH_AUTH_SOCK",
    }
)


def is_secret_env_name(name: str) -> bool:
    """Return True when an environment variable name is treated as secret.

    A name is secret when it ends with a known credential suffix
    (``*_API_KEY``, ``*_TOKEN``, ``*_SECRET``, ``*_PASSWORD``,
    ``*_PASSWD``, ``*_PASSPHRASE``, ``*_DSN``) or appears on the explicit
    credential-name list. Matching is case-insensitive.

    Note: ``DATABASE_URL`` can embed database credentials. ``SSH_AUTH_SOCK``,
    ``GIT_ASKPASS``, and ``SSH_ASKPASS`` are also filtered deliberately —
    model-spawned children should not reach agent/credential-helper sockets.
    Re-inject them via explicit trusted config if a workflow requires it.
    """
    upper = name.upper()
    if upper in _SECRET_ENV_NAMES:
        return True
    return any(upper.endswith(suffix) for suffix in _SECRET_ENV_SUFFIXES)


def build_child_env(
    overrides: dict[str, str] | None = None,
    *,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a filtered environment for child processes (SEC-008).

    Starts from ``base`` (default: the current process environment), drops
    every variable whose name matches :func:`is_secret_env_name`, then
    applies ``overrides`` last. Overrides are applied *after* filtering so
    trusted callers can deliberately re-inject a specific credential (for
    example ``PGPASSWORD`` for a backup child); they are an explicit
    operator-code decision, never implicit inheritance.
    """
    env = dict(base if base is not None else os.environ)
    filtered = {k: v for k, v in env.items() if not is_secret_env_name(k)}
    if overrides:
        filtered.update(overrides)
    return filtered

"""
security.py — Security primitives for zcoder.

Provides branded opaque IDs, credential reference validation, and the
CredentialProvider service definition. This is the zcoder equivalent of
deepseek-harness's dsh-brand and dsh-credentials packages, adapted for Python.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast

from zcoder.core.exceptions import SecurityError, ValidationError

# ── Branded opaque IDs (deepseek-harness dsh-brand equivalent) ──────────────

T = TypeVar("T")

# Branded string/number types make structurally identical values non-interchangeable
# at the type level: a SessionId cannot be passed where a ToolCallId is expected.
# brandString() / brandNumber() change only the static type; perform no runtime
# validation; validate domain grammar before calling when the owning type has
# one. Once branded, the id compares, logs, serializes to JSON, and crosses the
# wire as an ordinary string/number.

_BRAND: str = "__brand__"


def brandString(value: str) -> str:
    """Brand a raw string as a nominal type.

    Changes only the static type; performs no runtime validation. Validate
    domain grammar before calling when the owning type has one. Once branded,
    the id compares, logs, serializes to JSON, and crosses the wire as an
    ordinary string.
    """
    return value


def brandNumber(value: float) -> float:
    """Brand a raw number as a nominal type.

    Returns the original number and performs no validation. Comparison,
    arithmetic, logging, JSON serialization, and wire transport retain
    ordinary number behavior; arithmetic produces an unbranded number that
    the owner must admit again before it re-enters the domain.
    """
    return float(value)


def is_branded(value: Any, brand: str) -> bool:
    """Check whether a value carries the given brand marker."""
    return isinstance(value, str) and hasattr(value, "__brand__") and value.__brand__ == brand


# ── Session id brands ──────────────────────────────────────────────────────

SessionId = Annotated[str, "SessionId"]
SessionSeq = Annotated[int, "SessionSeq"]
ToolCallId = Annotated[str, "ToolCallId"]


def brandSessionId(value: str) -> SessionId:
    return cast(SessionId, brandString(value))


def brandSessionSeq(value: int) -> SessionSeq:
    return cast(SessionSeq, brandNumber(float(value)))


def brandToolCallId(value: str) -> ToolCallId:
    return cast(ToolCallId, brandString(value))


# ── Credential seam (deepseek-harness credentials/credentials equivalent) ──


# ── Credential pattern constants ────────────────────────────────────────────


REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

KEY_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def is_credential_ref_name(value: str) -> bool:
    """Whether a raw string could name a reference at all.

    Consumers that receive environment-variable names from somewhere else — a
    provider library's own ambient discovery, a hook payload — ask this before
    resolving, because a name outside the grammar has no reference to miss and
    should read as "not set" rather than as a thrown error.
    """
    return bool(REF_PATTERN.fullmatch(value))


class CredentialRef(str):
    """Branded reference to a credential value.

    A CredentialRef names an environment variable (e.g. ``DEEPSEEK_API_KEY``)
    whose value is the actual secret. Consumers resolve a reference once per
    operation; a changed credential reaches the next operation without any
    plugin restart.
    """

    @classmethod
    def parse(cls, value: str) -> CredentialRef:
        if not is_credential_ref_name(value):
            raise ValueError(f'credential ref "{value}" must match ' f"{REF_PATTERN.pattern!r}")
        return cast(CredentialRef, brandString(value))


def credentialRef(value: str) -> CredentialRef:
    """Brand a raw string as a {@link CredentialRef}.

    @param value - candidate reference; a POSIX shell identifier such as
        ``ZCODER_API_KEY``.
    @returns the branded reference.
    @throws ValueError when value does not match the reference name pattern.
    """
    return CredentialRef.parse(value)


# ── CredentialProvider (Service Definition) ──────────────────────────────


# Public alias for the snake_case version.
isCredentialRefName = is_credential_ref_name


class CredentialProvider(ABC):
    """Abstract credential service over two key spaces.

    A {@link CredentialRef} answers "what is behind this environment-variable
    name": the provider-managed store first, then ambient fallbacks such as the
    process environment and ``.env`` files.

    A {@link CredentialKey} answers "what credential does this plugin hold for
    this id". Nothing can layer here — an authorization grant has no
    environment to be read from — so presence of the record is the whole fact,
    and {@link modifyRecord} is the only write path because a correct write
    depends on the current value (a token refresh is read-decide-replace under
    one lock).
    """

    @abstractmethod
    def resolve(self, ref: CredentialRef) -> ResolvedCredential | None: ...

    @abstractmethod
    def describe(self, ref: CredentialRef) -> CredentialInfo: ...

    @abstractmethod
    def set(self, ref: CredentialRef, value: str) -> None: ...

    @abstractmethod
    def unset(self, ref: CredentialRef) -> None: ...

    @abstractmethod
    def readRecord(self, key: CredentialKey) -> CredentialRecord | None: ...

    @abstractmethod
    def describeRecord(self, key: CredentialKey) -> CredentialRecordInfo: ...

    @abstractmethod
    def listRecords(self) -> list[CredentialRecordEntry]: ...

    @abstractmethod
    def modifyRecord(
        self,
        key: CredentialKey,
        mutate: Callable[[CredentialRecord | None], CredentialRecord | None | None],
    ) -> CredentialRecord | None: ...

    @abstractmethod
    def deleteRecord(self, key: CredentialKey) -> None: ...

    def notifyUpdated(self, ref: CredentialRef) -> None:  # noqa: B027
        """Fan ``credentials/reference-updated`` out with contained listener
        failures: every listener runs, and a sync throw or async rejection is
        logged without changing the committed operation's outcome."""
        # Default implementation does nothing; subclasses can override.
        pass

    def notifyRecordUpdated(self, key: CredentialKey) -> None:  # noqa: B027
        """Fan ``credentials/record-updated`` out on exactly the terms
        {@link notifyUpdated} documents, for the record half of the seam."""
        # Default implementation does nothing; subclasses can override.
        pass


# ── CredentialRecord types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class CredentialRecord:
    kind: str
    value: str | None = None


@dataclass(frozen=True)
class CredentialRecordEntry:
    key: CredentialKey
    kind: str


@dataclass(frozen=True)
class CredentialRecordInfo:
    configured: bool
    kind: str | None = None
    writable: bool = False


@dataclass(frozen=True)
class ResolvedCredential:
    """One resolved credential value and the source layer that supplied it."""

    value: str
    source: str


@dataclass(frozen=True)
class CredentialInfo:
    """Describe one reference for configuration surfaces without exposing the
    full value."""

    configured: bool
    kind: str | None = None
    writable: bool = False


# ── Credential key types ────────────────────────────────────────────────────


class CredentialKey(str):
    """Branded string representing a stored credential key "<scope>/<id>".

    Both halves of a {@link CredentialKey}; the "/" between them is what keeps
    it out of {@link REF_PATTERN}.
    """

    @classmethod
    def parse(cls, value: str) -> CredentialKey:
        segments = value.split("/")
        if len(segments) != 2:
            raise ValueError(f'credential key "{value}" must be "<scope>/<id>"')
        scope, id_ = segments
        if not KEY_SEGMENT_PATTERN.match(scope) or not KEY_SEGMENT_PATTERN.match(id_):
            raise ValueError(f"credential key segment must match {KEY_SEGMENT_PATTERN.pattern!r}")
        return cast(CredentialKey, brandString(value))


def credentialKey(scope: str, id: str) -> CredentialKey:
    """Brand a scope and an id as a {@link CredentialKey}.

    @param scope - the owning plugin's registered name, such as ``llm-pi-ai``.
    @param id - that plugin's own addressing unit, such as a provider route key.
    @returns the branded key.
    @throws TypeError when either segment is not a lowercase hyphenated
        identifier.
    """
    for segment in [scope, id]:
        if not KEY_SEGMENT_PATTERN.match(segment):
            raise ValueError(
                f'credential key segment "{segment}" must match ' f"{KEY_SEGMENT_PATTERN.pattern!r}"
            )
    return cast(CredentialKey, brandString(f"{scope}/{id}"))


def parseCredentialKey(value: str) -> CredentialKey:
    """Brand a stored ``<scope>/<id>`` string as a {@link CredentialKey}.

    This is the read half of {@link credentialKey}, for a provider admitting
    keys off disk.
    """
    return CredentialKey.parse(value)


def credentialKeyScope(key: CredentialKey) -> str:
    """The owning plugin's name for one key."""
    return key[: key.index("/")]


def credentialKeyId(key: CredentialKey) -> str:
    """The owning plugin's own addressing unit for one key."""
    return key[key.index("/") + 1 :]


# ── Safe path resolution ────────────────────────────────────────────────────


def safe_resolve(path: str | os.PathLike[str], base_dir: str | os.PathLike[str]) -> Path:
    """Resolve a path safely within a base directory.

    Resolves ``path`` relative to ``base_dir`` (ขยาย ``~`` และ canonicalize
    ด้วย ``realpath`` เพื่อกัน traversal และ symlink escape) แล้วตรวจว่าผลลัพธ์
    ยังอยู่ใน ``base_dir`` การตรวจ prefix แบบมี separator กัน sibling-prefix
    เช่น ``/safe/workspace-evil`` เมื่อ root คือ ``/safe/workspace``

    @param path - candidate path (relative or absolute)
    @param base_dir - base directory that constrains the resolution
    @returns the resolved absolute path as a ``Path``
    @throws SecurityError if the resolved path escapes the base directory
    """
    base = os.path.realpath(os.path.expanduser(os.fspath(base_dir)))
    raw_path = os.fspath(path)
    candidate = os.path.realpath(raw_path if os.path.isabs(raw_path) else os.path.join(base, raw_path))
    base_prefix = base if base.endswith(os.sep) else base + os.sep
    if candidate != base and not candidate.startswith(base_prefix):
        raise SecurityError(
            "Path escapes the allowed base directory",
            details={"path": raw_path, "base_dir": base},
        )
    return Path(candidate)


# ── Child environment ───────────────────────────────────────────────────────


def build_child_env(
    overrides: dict[str, str] | None = None,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a clean child-process environment with optional overrides.

    Starts from the ``base`` environment (or the current process environment
    if ``base`` is not given), filters out secret-named variables, and
    applies ``overrides`` on top. Follows the "no secret inheritance" principle
    (SEC-008): child processes do not inherit secret environment variables
    unless explicitly allowed via overrides.

    @param overrides - additional environment variables to set on top
    @param base - base environment dict to start from (defaults to os.environ)
    @returns the child environment dictionary
    """
    import os as _os

    if base is None:
        base = dict(_os.environ)

    # Filter out secret-named environment variables
    filtered: dict[str, str] = {}
    for key, value in base.items():
        if not is_secret_env_name(key):
            filtered[key] = value

    # Apply overrides on top (overrides can re-inject trusted secrets)
    if overrides:
        for key, value in overrides.items():
            filtered[key] = value

    return filtered


# ── Text prefix reading ─────────────────────────────────────────────────────


def assert_no_secret(text: str, field: str = "text") -> None:
    """Raise :exc:`SecurityError` if ``text`` contains a secret pattern.

    Uses heuristic detection to find API keys, passwords, and other secret
    patterns in text. Common patterns include ``sk-`` prefixed Anthropic/OpenAI
    keys, ``password=`` assignments, and ``secret=`` assignments.

    @param text - text to scan for secrets
    @param field - field name used in error messages
    @throws SecurityError if a secret pattern is detected
    """
    import re as _re

    patterns = [
        _re.compile(r"sk-[a-zA-Z0-9-]{20,}"),  # API keys (minimum 20 chars after sk-)
        _re.compile(r"password\s*=\s*['\"][^'\"]{4,}"),  # password assignments
        _re.compile(r"secret\s*=\s*['\"][^'\"]{4,}"),  # secret assignments
    ]
    for pattern in patterns:
        if pattern.search(text):
            raise SecurityError(f"{field} contains a secret pattern")


def contains_secret(text: str) -> bool:
    """Check whether ``text`` contains a secret pattern.

    Same heuristic as {@link assert_no_secret} but returns a boolean instead
    of raising an exception.

    @param text - text to scan for secrets
    @returns True if a secret pattern is found, False otherwise
    """
    import re as _re

    patterns = [
        _re.compile(r"sk-[a-zA-Z0-9-]{20,}"),  # API keys (minimum 20 chars after sk-)
        _re.compile(r"password\s*=\s*['\"][^'\"]{4,}"),  # password assignments
        _re.compile(r"secret\s*=\s*['\"][^'\"]{4,}"),  # secret assignments
    ]
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False


def env_flag(value: str, default: bool = False) -> bool:
    """Parse an environment variable flag as a truthy/falsy value.

    Accepts an environment variable ``value`` string or a ``key`` name.
    When ``value`` is an env var key name, reads from ``os.environ``.
    Accepted truthy values: ``"1"`, ``"true"`, ``"True"`, ``"yes"`, ``"on"``.
    Accepted falsy values: ``"0"`, ``"false"`, ``"False"`, ``"no"`, ``"off"``.
    When ``default`` is provided and the variable is unset, return the default.
    When ``default`` is not provided and the variable is unset, return ``True``
    (safer default for secret-sensitive contexts).

    @param value - environment variable value string, or key name to read from os.environ
    @param default - default value when env var is unset
    @returns parsed boolean
    """
    import os as _os

    # If value is None, return default immediately
    if value is None:
        return default if default is not None else True

    # If value looks like a key name (not a direct value), read from env
    truthy = {"1", "true", "True", "yes", "on"}
    falsy = {"0", "false", "False", "no", "off"}

    # Try to read from environment if value is a key name
    env_value = _os.environ.get(value, None)

    if env_value is not None:
        value = env_value

    if value is None:
        return default if default is not None else True
    if value in truthy:
        return True
    if value in falsy:
        return False
    return default if default is not None else True


BINARY_FILE_EXTENSIONS = frozenset(
    {
        ".xlsm",
        ".parquet",
        ".epub",
        ".heic",
        ".png",
        ".zip",
        ".sqlite",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".pdf",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".pyc",
    }
)

READ_PREFIX_BYTES_DEFAULT = 1 * 1024 * 1024  # 1 MiB


def read_text_prefix(
    path: str | os.PathLike,
    *,
    max_bytes: int = READ_PREFIX_BYTES_DEFAULT,
    max_chars: int | None = None,
) -> str:
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


# ── File size checking ──────────────────────────────────────────────────────


def check_file_size(path_or_file: Any, max_bytes: int) -> None:
    """Raise :exc:`SecurityError` if ``path_or_file`` exceeds ``max_bytes``.

    Accepts either a file-like object (with ``seek``/``tell``) or a path
    string. When a file-like object is given, its position is restored to 0.

    @param path_or_file - file-like object or path to check
    @param max_bytes - maximum allowed size in bytes
    @throws SecurityError if the file is too large
    """
    size = 0
    try:
        if hasattr(path_or_file, "seek") and hasattr(path_or_file, "tell"):
            name = getattr(path_or_file, "name", "unknown")
            path_or_file.seek(0, 2)  # seek to end
            size = path_or_file.tell()
            path_or_file.seek(0)
        else:
            name = str(path_or_file)
            size = Path(path_or_file).stat().st_size
    except (OSError, AttributeError):
        return
    if size > max_bytes:
        raise SecurityError(f"{name} exceeds maximum size of {max_bytes} bytes (got {size})")


# ── Name validation ─────────────────────────────────────────────────────────


_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_. -]*$")


# ── Constants ──────────────────────────────────────────────────────────────


# ── Environment variable secret name detection ───────────────────────────────
def is_secret_env_name(name: str) -> bool:
    """Check whether an environment variable name indicates a secret.

    Environment variables whose names match known secret patterns (e.g.
    containing ``API_KEY`, ``TOKEN`, ``PASSWORD`, ``SECRET``, ``DSN``, or
    matching credential reference patterns) are considered secret-containing.

    @param name - environment variable name
    @returns True if the name indicates a secret, False otherwise
    """
    secret_patterns = [
        re.compile(r".*[_-]?API_KEY.*", re.IGNORECASE),
        re.compile(r".*[_-]?TOKEN.*", re.IGNORECASE),
        re.compile(r".*[_-]?PASSWORD.*", re.IGNORECASE),
        re.compile(r".*[_-]?SECRET.*", re.IGNORECASE),
        re.compile(r".*[_-]?DSN.*", re.IGNORECASE),
        re.compile(r".*[_-]?PASSWD.*", re.IGNORECASE),
        re.compile(r".*[_-]?KEY.*", re.IGNORECASE),
        re.compile(r".*[_-]?ASKPASS.*", re.IGNORECASE),
        re.compile(r".*[_-]?URL.*", re.IGNORECASE),
        re.compile(r".*[_-]?PASSPHRASE.*", re.IGNORECASE),
    ]
    for pattern in secret_patterns:
        if pattern.search(name):
            return True
    return False


def validate_name(name: str, field: str = "name") -> str:
    """Validate that name is a safe identifier."""
    if not isinstance(name, str) or not name or len(name) > 255:
        raise ValidationError(f"{field} must be a non-empty string <= 255 chars")
    if not _NAME_RE.fullmatch(name):
        raise ValidationError(
            f"{field} '{name}' contains invalid characters; "
            "only letters, digits, underscore, hyphen, and dot are allowed"
        )
    return name


# ── URL validation ──────────────────────────────────────────────────────────


def validate_url(url: str, allowed_schemes: tuple[str, ...] = ("https",)) -> None:
    """Validate that ``url`` uses an allowed scheme.

    @param url - URL to validate
    @param allowed_schemes - schemes permitted (default: http, https)
    @throws SecurityError if the URL uses a disallowed scheme or is malformed
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise SecurityError(f"invalid URL: {url}") from exc
    if parsed.scheme not in allowed_schemes:
        raise SecurityError(
            f"URL scheme '{parsed.scheme}' not allowed; " f"permitted schemes: {', '.join(allowed_schemes)}"
        )

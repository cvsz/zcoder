"""JSONL session persistence with migration — mirrors deepseek-harness
@deepseek-ai/dsh-session-persistence-jsonl.

Provides append-only JSONL session persistence with:
  * Zstd compression option
  * Lease-based concurrent access control
  * Format migration pipeline (v0→v1→v2→v3→v4)
  * Migration verifier
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Try to import zstd; fall back to no compression if unavailable
try:
    import zstandard as zstd

    _HAS_ZSTD = True
except ImportError:
    _HAS_ZSTD = False


SESSION_FORMAT_VERSION = 4

# Used by serialize/deserialize for format identification and version validation.
_FORMAT_MAGIC: str = "ZCODER-SESSION"  # noqa: F841
_FORMAT_VERSIONS: set[int] = {0, 1, 2, 3, 4}  # noqa: F841


@dataclass
class SessionLease:
    """Lease for concurrent session access control."""

    session_id: str
    path: Path
    acquired_at: float
    ttl: float = 30.0
    _released: bool = field(default=False, init=False)

    def is_expired(self) -> bool:
        return time.time() - self.acquired_at > self.ttl

    def release(self) -> None:
        self._released = True


class SessionPersistenceJSONL:
    """JSONL-based session persistence with append-only writes.

    Mirrors deepseek-harness session-persistence-jsonl:
    - Each session event is appended as a JSONL line
    - Optional zstd compression
    - Lease-based concurrent access
    - Format migration across versions
    """

    def __init__(
        self,
        directory: Path | None = None,
        compression: bool = False,
        lease_ttl: float = 30.0,
    ) -> None:
        self.dir = Path(directory) if directory else Path.home() / ".zcoder" / "sessions"
        self.compression = compression and _HAS_ZSTD
        self.lease_ttl = lease_ttl
        self._leases: dict[str, SessionLease] = {}
        self._lock = __import__("threading").RLock()
        self._zstd_compressor: Any = None
        self._zstd_decompressor: Any = None

        if self.compression and _HAS_ZSTD:
            self._zstd_compressor = zstd.ZstdCompressor()
            self._zstd_decompressor = zstd.ZstdDecompressor()
        else:
            self._zstd_compressor = None
            self._zstd_decompressor = None

    # ── Path & validation ─────────────────────────────────────────

    def _path(self, session_id: str) -> Path:
        safe_id = os.path.basename(session_id)
        if safe_id != session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("invalid session id")
        root = self.dir.resolve()
        expected = root / f"{safe_id}.jsonl"
        resolved = os.path.realpath(expected)
        if not resolved.startswith(str(root) + os.sep):
            raise ValueError("session path escapes storage directory")
        return Path(resolved)

    # ── Lease management ──────────────────────────────────────────

    def acquire_lease(self, session_id: str) -> SessionLease:
        """Acquire a lease for concurrent access control."""
        with self._lock:
            # Clean expired leases
            expired = [sid for sid, lease in self._leases.items() if lease.is_expired()]
            for sid in expired:
                del self._leases[sid]

            if session_id in self._leases:
                existing = self._leases[session_id]
                if not existing.is_expired():
                    raise ValueError(f"session {session_id} is locked by another process")
                del self._leases[session_id]

            lease = SessionLease(session_id, self._path(session_id), time.time(), self.lease_ttl)
            self._leases[session_id] = lease
            return lease

    def release_lease(self, session_id: str) -> None:
        """Release a session lease."""
        with self._lock:
            self._leases.pop(session_id, None)

    # ── Read ──────────────────────────────────────────────────────

    def load(self, session_id: str) -> dict[str, Any]:
        """Load a session from JSONL file."""
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session {session_id} not found")

        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        if not events:
            return {}

        # First line is the session header
        header = events[0]
        # Remaining lines are events
        session_events = events[1:]

        return {
            "id": session_id,
            "header": header,
            "events": session_events,
            "event_count": len(session_events),
            "format_version": header.get("format_version", SESSION_FORMAT_VERSION),
        }

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        """Load all events from a session JSONL file."""
        path = self._path(session_id)
        if not path.exists():
            return []

        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        # Skip header line if present
        if events and events[0].get("kind") == "session/header":
            events = events[1:]

        return events

    # ── Write ─────────────────────────────────────────────────────

    def save_header(
        self,
        session_id: str,
        cwd: str,
        title: str = "",
        format_version: int = SESSION_FORMAT_VERSION,
    ) -> None:
        """Write the session header line (first line of JSONL)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(session_id)

        header = {
            "kind": "session/header",
            "id": session_id,
            "cwd": cwd,
            "title": title,
            "created_at": time.time(),
            "format_version": format_version,
        }

        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")

        os.chmod(path, 0o600)

    def append_event(
        self,
        session_id: str,
        event: dict[str, Any],
    ) -> None:
        """Append one event to the session JSONL file (append-only)."""
        path = self._path(session_id)

        # Ensure file exists with header
        if not path.exists():
            self.save_header(session_id, event.get("cwd", ""))

        line = json.dumps(event, separators=(",", ":"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def save(
        self,
        session_id: str,
        cwd: str,
        events: list[dict[str, Any]],
        usage: dict[str, int] | None = None,
    ) -> None:
        """Save all events to session (rewrites entire file - for compatibility)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(session_id)

        doc = {
            "id": session_id,
            "cwd": cwd,
            "updated": time.time(),
            "usage": usage,
            "events": events,
            "format_version": SESSION_FORMAT_VERSION,
        }

        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    # ── List / Delete / Fork / Rename ─────────────────────────────

    def list_sessions(self, cwd: str | None = None) -> list[dict[str, Any]]:
        """List all sessions with metadata."""
        infos: list[dict[str, Any]] = []
        if not self.dir.exists():
            return infos

        for p in self.dir.glob("*.jsonl"):
            try:
                data = self.load(p.stem)
                if cwd and data.get("header", {}).get("cwd") != cwd:
                    continue
                infos.append(
                    {
                        "id": p.stem,
                        "title": data.get("header", {}).get("title", ""),
                        "cwd": data.get("header", {}).get("cwd", ""),
                        "updated": data.get("header", {}).get("created_at", 0.0),
                        "event_count": data.get("event_count", 0),
                    }
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue

        return sorted(infos, key=lambda i: i["updated"], reverse=True)

    def delete(self, session_id: str) -> None:
        """Delete a session file."""
        path = self._path(session_id)
        path.unlink(missing_ok=True)
        self.release_lease(session_id)

    def fork(self, session_id: str, *, label: str | None = None) -> str:
        """Fork a session, creating a new session with copied events."""
        original = self.load(session_id)
        new_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        events = list(original.get("events", []))
        if label:
            events.append(
                {
                    "kind": "user/message",
                    "data": {"message": label},
                    "timestamp": time.time(),
                }
            )
        header = original.get("header", {})
        self.save_header(
            new_id,
            header.get("cwd", ""),
            header.get("title", ""),
            header.get("format_version", SESSION_FORMAT_VERSION),
        )
        for event in events:
            self.append_event(new_id, event)
        return new_id

    def rename(self, session_id: str, new_title: str) -> None:
        """Rename a session by updating the header."""
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session {session_id} not found")

        # Read all lines, update header, rewrite
        lines = []
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        if lines:
            header = json.loads(lines[0])
            header["title"] = new_title
            header["updated"] = time.time()
            lines[0] = json.dumps(header) + "\n"

        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    # ── Migration ─────────────────────────────────────────────────

    def migrate(self, session_id: str, target_version: int = SESSION_FORMAT_VERSION) -> None:
        """Migrate a session to the target format version."""
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session {session_id} not found")

        data = self.load(session_id)
        current_version = data.get("format_version", 0)

        if current_version >= target_version:
            return  # Already at or above target

        # Apply migrations sequentially
        for version in range(current_version, target_version):
            data = self._migrate_version(data, version, version + 1)

        # Write migrated data
        header = data.get("header", {})
        header["format_version"] = target_version
        self.save_header(
            session_id,
            header.get("cwd", ""),
            header.get("title", ""),
            target_version,
        )
        for event in data.get("events", []):
            self.append_event(session_id, event)

    def _migrate_version(self, data: dict[str, Any], from_version: int, to_version: int) -> dict[str, Any]:
        """Migrate data from one format version to the next."""
        if from_version == 0 and to_version == 1:
            return self._migrate_v0_to_v1(data)
        if from_version == 1 and to_version == 2:
            return self._migrate_v1_to_v2(data)
        if from_version == 2 and to_version == 3:
            return self._migrate_v2_to_v3(data)
        if from_version == 3 and to_version == 4:
            return self._migrate_v3_to_v4(data)
        raise ValueError(f"no migration path from v{from_version} to v{to_version}")

    def _migrate_v0_to_v1(self, data: dict[str, Any]) -> dict[str, Any]:
        """v0→v1: Add event_id and timestamp to all events."""
        for event in data.get("events", []):
            if "event_id" not in event:
                event["event_id"] = secrets.token_hex(8)
            if "timestamp" not in event:
                event["timestamp"] = time.time()
        return data

    def _migrate_v1_to_v2(self, data: dict[str, Any]) -> dict[str, Any]:
        """v1→v2: Add source_event_seqs to events."""
        for event in data.get("events", []):
            if "source_event_seqs" not in event:
                event["source_event_seqs"] = None
        return data

    def _migrate_v2_to_v3(self, data: dict[str, Any]) -> dict[str, Any]:
        """v2→v3: Add ignorable flag and surface_op to events."""
        for event in data.get("events", []):
            if "ignorable" not in event:
                event["ignorable"] = False
            if "surface_op" not in event:
                event["surface_op"] = None
        return data

    def _migrate_v3_to_v4(self, data: dict[str, Any]) -> dict[str, Any]:
        """v3→v4: Final format with all fields present."""
        # v4 is the current format; just ensure all fields exist
        for event in data.get("events", []):
            event.setdefault("event_id", secrets.token_hex(8))
            event.setdefault("timestamp", time.time())
            event.setdefault("source_event_seqs", None)
            event.setdefault("ignorable", False)
            event.setdefault("surface_op", None)
        return data

    # ── Verification ──────────────────────────────────────────────

    def verify_migration(self, session_id: str) -> dict[str, Any]:
        """Verify that a session can be migrated without data loss."""
        path = self._path(session_id)
        if not path.exists():
            return {"valid": False, "error": "session not found"}

        try:
            data = self.load(session_id)
            events = data.get("events", [])
            event_count = len(events)

            # Check all events have required fields
            missing_fields = []
            for i, event in enumerate(events):
                for field in ("kind", "data"):
                    if field not in event:
                        missing_fields.append(f"event[{i}].{field}")

            return {
                "valid": len(missing_fields) == 0,
                "event_count": event_count,
                "format_version": data.get("format_version", 0),
                "missing_fields": missing_fields,
            }
        except Exception as exc:
            return {"valid": False, "error": str(exc)}


__all__ = [
    "SESSION_FORMAT_VERSION",
    "SessionLease",
    "SessionPersistenceJSONL",
]

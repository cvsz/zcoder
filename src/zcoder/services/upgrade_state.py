"""Durable state and repository snapshot adapters for Upgrade-25."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from zcoder.services.upgrade_loop import LoopCheckpoint, UpgradeWorkItem, WorkKind, WorkState

_LEDGER_SCHEMA_VERSION = 1
_DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".zcoder",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
_SECRET_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
_SECRET_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}


class UpgradeLedgerError(RuntimeError):
    """Raised when durable loop state cannot be read or written safely."""


class RepositorySnapshotter:
    """Build a bounded, secret-aware text snapshot for Upgrade-20 context."""

    def __init__(
        self,
        repository_root: str | Path,
        *,
        max_files: int = 400,
        max_file_bytes: int = 256 * 1024,
        max_total_bytes: int = 4 * 1024 * 1024,
        excluded_dirs: Iterable[str] = _DEFAULT_EXCLUDED_DIRS,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.excluded_dirs = frozenset(excluded_dirs)
        if max_files < 1 or max_file_bytes < 1 or max_total_bytes < 1:
            raise ValueError("snapshot limits must be >= 1")

    def snapshot(self) -> dict[str, str]:
        if not self.repository_root.is_dir():
            raise FileNotFoundError(f"repository root not found: {self.repository_root}")

        snapshot: dict[str, str] = {}
        total_bytes = 0
        for current_root, dirnames, filenames in os.walk(self.repository_root):
            dirnames[:] = sorted(name for name in dirnames if name not in self.excluded_dirs)
            for filename in sorted(filenames):
                if len(snapshot) >= self.max_files or total_bytes >= self.max_total_bytes:
                    return snapshot
                path = Path(current_root) / filename
                if path.is_symlink() or self._excluded(path):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > self.max_file_bytes or size == 0:
                    continue
                try:
                    raw = path.read_bytes()
                    text = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                encoded_size = len(raw)
                if total_bytes + encoded_size > self.max_total_bytes:
                    continue
                snapshot[path.relative_to(self.repository_root).as_posix()] = text
                total_bytes += encoded_size
        return snapshot

    def _excluded(self, path: Path) -> bool:
        relative = path.relative_to(self.repository_root)
        if any(part in self.excluded_dirs for part in relative.parts[:-1]):
            return True
        name = path.name.lower()
        return name.startswith(".env") or name in _SECRET_NAMES or path.suffix.lower() in _SECRET_SUFFIXES


class JsonUpgradeLedger:
    """Atomic durable state for idempotent Upgrade-24/25 restart and resume."""

    def __init__(self, path: str | Path, *, max_checkpoints: int = 100) -> None:
        self.path = Path(path)
        self.max_checkpoints = max_checkpoints
        self._lock = threading.RLock()
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be >= 1")

    def restore_or_register(
        self, item: UpgradeWorkItem, *, retry_blocked: bool = False
    ) -> UpgradeWorkItem | None:
        """Return a resumable item or None for a terminal fingerprint."""

        with self._lock:
            data = self._read()
            record = data["records"].get(item.fingerprint)
            if record is None:
                data["records"][item.fingerprint] = self._serialize_item(item)
                self._write(data)
                return item

            state = str(record.get("state", WorkState.PENDING.value))
            if state == WorkState.SUCCEEDED.value:
                return None
            if state == WorkState.BLOCKED.value and not retry_blocked:
                return None

            attempts = int(record.get("attempts", 0))
            if state == WorkState.BLOCKED.value and retry_blocked:
                attempts = 0

            restored = UpgradeWorkItem(
                title=str(record.get("title", item.title)),
                kind=WorkKind(str(record.get("kind", item.kind.value))),
                payload=dict(record.get("payload", item.payload)),
                priority=int(record.get("priority", item.priority)),
                risk=str(record.get("risk", item.risk)),
                max_attempts=int(record.get("max_attempts", item.max_attempts)),
                item_id=str(record.get("item_id", item.item_id)),
                state=WorkState.PENDING,
                attempts=attempts,
                last_error=str(record.get("last_error", "")),
            )
            data["records"][restored.fingerprint] = self._serialize_item(restored)
            self._write(data)
            return restored

    def load_resumable(self, *, retry_blocked: bool = False) -> list[UpgradeWorkItem]:
        with self._lock:
            data = self._read()
            items: list[UpgradeWorkItem] = []
            changed = False
            for fingerprint, record in data["records"].items():
                state = str(record.get("state", WorkState.PENDING.value))
                if state == WorkState.SUCCEEDED.value:
                    continue
                if state == WorkState.BLOCKED.value and not retry_blocked:
                    continue
                attempts = int(record.get("attempts", 0))
                if state == WorkState.BLOCKED.value:
                    attempts = 0
                    record["state"] = WorkState.PENDING.value
                    record["attempts"] = 0
                    changed = True
                item = UpgradeWorkItem(
                    title=str(record["title"]),
                    kind=WorkKind(str(record["kind"])),
                    payload=dict(record.get("payload", {})),
                    priority=int(record.get("priority", 50)),
                    risk=str(record.get("risk", "medium")),
                    max_attempts=int(record.get("max_attempts", 2)),
                    item_id=str(record["item_id"]),
                    state=WorkState.PENDING,
                    attempts=attempts,
                    last_error=str(record.get("last_error", "")),
                )
                if item.fingerprint != fingerprint:
                    raise UpgradeLedgerError("ledger fingerprint mismatch")
                items.append(item)
            if changed:
                self._write(data)
            return items

    def record_checkpoint(
        self, checkpoint: LoopCheckpoint, items_by_id: dict[str, UpgradeWorkItem]
    ) -> None:
        with self._lock:
            data = self._read()
            completed = set(checkpoint.completed_item_ids)
            blocked = set(checkpoint.blocked_item_ids)
            pending = set(checkpoint.pending_item_ids)
            for item_id, item in items_by_id.items():
                persisted_state = item.state
                if item_id in completed:
                    persisted_state = WorkState.SUCCEEDED
                elif item_id in blocked:
                    persisted_state = WorkState.BLOCKED
                elif item_id in pending:
                    persisted_state = WorkState.PENDING
                elif item_id == checkpoint.active_item_id:
                    persisted_state = WorkState.RUNNING
                data["records"][item.fingerprint] = self._serialize_item(
                    item, state=persisted_state
                )

            checkpoints = data["checkpoints"]
            checkpoints.append(
                {
                    "iteration": checkpoint.iteration,
                    "state": checkpoint.state.value,
                    "active_item_id": checkpoint.active_item_id,
                    "completed_item_ids": list(checkpoint.completed_item_ids),
                    "blocked_item_ids": list(checkpoint.blocked_item_ids),
                    "pending_item_ids": list(checkpoint.pending_item_ids),
                    "created_at": checkpoint.created_at,
                }
            )
            data["checkpoints"] = checkpoints[-self.max_checkpoints :]
            self._write(data)

    def state_for(self, fingerprint: str) -> str | None:
        with self._lock:
            record = self._read()["records"].get(fingerprint)
            return None if record is None else str(record.get("state"))

    def blocked_item_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                str(record.get("item_id", ""))
                for record in self._read()["records"].values()
                if record.get("state") == WorkState.BLOCKED.value and record.get("item_id")
            )

    def terminal_counts(self) -> dict[str, int]:
        counts = {WorkState.SUCCEEDED.value: 0, WorkState.BLOCKED.value: 0}
        with self._lock:
            for record in self._read()["records"].values():
                state = str(record.get("state", ""))
                if state in counts:
                    counts[state] += 1
        return counts

    def _serialize_item(
        self, item: UpgradeWorkItem, *, state: WorkState | None = None
    ) -> dict[str, Any]:
        return {
            "item_id": item.item_id,
            "title": item.title,
            "kind": item.kind.value,
            "payload": item.payload,
            "priority": item.priority,
            "risk": item.risk,
            "max_attempts": item.max_attempts,
            "state": (state or item.state).value,
            "attempts": item.attempts,
            "last_error": item.last_error,
            "updated_at": time.time(),
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": _LEDGER_SCHEMA_VERSION, "records": {}, "checkpoints": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UpgradeLedgerError(f"unable to read upgrade ledger: {exc}") from exc
        if data.get("schema_version") != _LEDGER_SCHEMA_VERSION:
            raise UpgradeLedgerError("unsupported upgrade ledger schema")
        if not isinstance(data.get("records"), dict) or not isinstance(data.get("checkpoints"), list):
            raise UpgradeLedgerError("invalid upgrade ledger structure")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True, default=str) + "\n"
        try:
            fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except OSError as exc:
            raise UpgradeLedgerError(f"unable to write upgrade ledger: {exc}") from exc

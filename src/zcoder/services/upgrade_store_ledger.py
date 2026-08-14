"""EngineeringStore-backed durable ledger for continuous upgrade work.

This adapter reuses the existing Upgrade-21 EngineeringStore boundary instead of
introducing a second database schema. Upgrade work state is authoritative in
namespaced task metadata; carrier EngineeringTask statuses deliberately avoid
CREATED so normal engineering workers cannot claim ledger records as executable
Upgrade-20 tasks.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Protocol

from zcoder.domain.interfaces.engineering_store import EngineeringStore
from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.upgrade_loop import LoopCheckpoint, UpgradeWorkItem, WorkKind, WorkState
from zcoder.services.upgrade_state import UpgradeLedgerError

_STORE_LEDGER_SCHEMA_VERSION = 1
_METADATA_KEY = "zcoder_upgrade_ledger"


class UpgradeLedger(Protocol):
    """Persistence contract consumed by ContinuousEngineeringPipeline."""

    def restore_or_register(
        self, item: UpgradeWorkItem, *, retry_blocked: bool = False
    ) -> UpgradeWorkItem | None: ...

    def load_resumable(self, *, retry_blocked: bool = False) -> list[UpgradeWorkItem]: ...

    def record_checkpoint(
        self, checkpoint: LoopCheckpoint, items_by_id: dict[str, UpgradeWorkItem]
    ) -> None: ...

    def state_for(self, fingerprint: str) -> str | None: ...

    def blocked_item_ids(self) -> tuple[str, ...]: ...

    def terminal_counts(self) -> dict[str, int]: ...


class EngineeringStoreUpgradeLedger:
    """Persist Upgrade-24/25 work through an existing EngineeringStore.

    The store may be SQLite, PostgreSQL, or another implementation of the
    Upgrade-21 EngineeringStore interface. This class intentionally does not
    provide a distributed run lease; callers must still serialize a full
    ContinuousEngineeringPipeline run with an appropriate lease boundary.
    """

    def __init__(
        self,
        store: EngineeringStore,
        *,
        namespace: str = "zcoder-continuous-upgrades",
        max_checkpoints: int = 100,
    ) -> None:
        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            raise ValueError("namespace must not be empty")
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be >= 1")
        self.store = store
        self.namespace = normalized_namespace
        self.max_checkpoints = max_checkpoints
        namespace_hash = hashlib.sha256(normalized_namespace.encode("utf-8")).hexdigest()[:16]
        self._task_prefix = f"upgrade-ledger-{namespace_hash}-"
        self.control_task_id = f"{self._task_prefix}control"
        self._lock = threading.RLock()

    def restore_or_register(
        self, item: UpgradeWorkItem, *, retry_blocked: bool = False
    ) -> UpgradeWorkItem | None:
        with self._lock:
            existing = self.store.get_task(self._task_id(item.fingerprint))
            if existing is None:
                self._save_item(item)
                return item

            record = self._record_from_task(existing, expected_fingerprint=item.fingerprint)
            state = str(record.get("state", WorkState.PENDING.value))
            if state == WorkState.SUCCEEDED.value:
                return None
            if state == WorkState.BLOCKED.value and not retry_blocked:
                return None

            attempts = int(record.get("attempts", 0))
            if state == WorkState.BLOCKED.value:
                attempts = 0

            restored = self._deserialize_item(record, fallback=item, attempts=attempts)
            self._save_item(restored)
            return restored

    def load_resumable(self, *, retry_blocked: bool = False) -> list[UpgradeWorkItem]:
        with self._lock:
            items: list[UpgradeWorkItem] = []
            for task in self._record_tasks():
                record = self._record_from_task(task)
                state = str(record.get("state", WorkState.PENDING.value))
                if state == WorkState.SUCCEEDED.value:
                    continue
                if state == WorkState.BLOCKED.value and not retry_blocked:
                    continue
                attempts = int(record.get("attempts", 0))
                if state == WorkState.BLOCKED.value:
                    attempts = 0
                item = self._deserialize_item(record, attempts=attempts)
                self._save_item(item)
                items.append(item)
            return items

    def record_checkpoint(self, checkpoint: LoopCheckpoint, items_by_id: dict[str, UpgradeWorkItem]) -> None:
        with self._lock:
            completed = set(checkpoint.completed_item_ids)
            blocked = set(checkpoint.blocked_item_ids)
            pending = set(checkpoint.pending_item_ids)
            for item_id, item in items_by_id.items():
                state = item.state
                if item_id in completed:
                    state = WorkState.SUCCEEDED
                elif item_id in blocked:
                    state = WorkState.BLOCKED
                elif item_id in pending:
                    state = WorkState.PENDING
                elif item_id == checkpoint.active_item_id:
                    state = WorkState.RUNNING
                self._save_item(item, state=state)

            control = self.store.get_task(self.control_task_id)
            checkpoints: list[dict[str, Any]] = []
            created_at = time.time()
            if control is not None:
                marker = self._marker_from_task(control, expected_type="control")
                raw_checkpoints = marker.get("checkpoints", [])
                if not isinstance(raw_checkpoints, list):
                    raise UpgradeLedgerError("invalid EngineeringStore upgrade checkpoint history")
                checkpoints = list(raw_checkpoints)
                created_at = control.created_at
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
            metadata = {
                _METADATA_KEY: {
                    "schema_version": _STORE_LEDGER_SCHEMA_VERSION,
                    "record_type": "control",
                    "namespace": self.namespace,
                    "checkpoints": checkpoints[-self.max_checkpoints :],
                }
            }
            self.store.save_task(
                EngineeringTask(
                    id=self.control_task_id,
                    task_description=f"Continuous upgrade ledger control: {self.namespace}",
                    status=TaskStatus.PAUSED,
                    created_at=created_at,
                    metadata=metadata,
                )
            )

    def state_for(self, fingerprint: str) -> str | None:
        with self._lock:
            task = self.store.get_task(self._task_id(fingerprint))
            if task is None:
                return None
            return str(self._record_from_task(task, expected_fingerprint=fingerprint).get("state"))

    def blocked_item_ids(self) -> tuple[str, ...]:
        with self._lock:
            blocked: list[str] = []
            for task in self._record_tasks():
                record = self._record_from_task(task)
                if record.get("state") == WorkState.BLOCKED.value and record.get("item_id"):
                    blocked.append(str(record["item_id"]))
            return tuple(blocked)

    def terminal_counts(self) -> dict[str, int]:
        counts = {WorkState.SUCCEEDED.value: 0, WorkState.BLOCKED.value: 0}
        with self._lock:
            for task in self._record_tasks():
                state = str(self._record_from_task(task).get("state", ""))
                if state in counts:
                    counts[state] += 1
        return counts

    def _record_tasks(self) -> list[EngineeringTask]:
        tasks: list[EngineeringTask] = []
        for task in self.store.list_tasks():
            if task.id == self.control_task_id:
                self._marker_from_task(task, expected_type="control")
                continue
            if not task.id.startswith(self._task_prefix):
                continue
            self._marker_from_task(task, expected_type="work")
            tasks.append(task)
        return tasks

    def _save_item(self, item: UpgradeWorkItem, *, state: WorkState | None = None) -> None:
        effective_state = state or item.state
        record = self._serialize_item(item, state=effective_state)
        task_id = self._task_id(item.fingerprint)
        existing = self.store.get_task(task_id)
        created_at = existing.created_at if existing is not None else time.time()
        metadata = {
            _METADATA_KEY: {
                "schema_version": _STORE_LEDGER_SCHEMA_VERSION,
                "record_type": "work",
                "namespace": self.namespace,
                "fingerprint": item.fingerprint,
                "record": record,
            }
        }
        carrier_status = TaskStatus.SUCCEEDED if effective_state == WorkState.SUCCEEDED else TaskStatus.PAUSED
        self.store.save_task(
            EngineeringTask(
                id=task_id,
                task_description=item.title,
                status=carrier_status,
                created_at=created_at,
                metadata=metadata,
            )
        )

    def _record_from_task(
        self, task: EngineeringTask, *, expected_fingerprint: str | None = None
    ) -> dict[str, Any]:
        marker = self._marker_from_task(task, expected_type="work")
        fingerprint = marker.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise UpgradeLedgerError("missing EngineeringStore upgrade fingerprint")
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            raise UpgradeLedgerError("EngineeringStore upgrade fingerprint mismatch")
        if task.id != self._task_id(fingerprint):
            raise UpgradeLedgerError("EngineeringStore upgrade task identity mismatch")
        record = marker.get("record")
        if not isinstance(record, dict):
            raise UpgradeLedgerError("invalid EngineeringStore upgrade work record")
        item = self._deserialize_item(record)
        if item.fingerprint != fingerprint:
            raise UpgradeLedgerError("EngineeringStore upgrade content fingerprint mismatch")
        return record

    def _marker_from_task(self, task: EngineeringTask, *, expected_type: str) -> dict[str, Any]:
        marker = task.metadata.get(_METADATA_KEY) if isinstance(task.metadata, dict) else None
        if not isinstance(marker, dict):
            raise UpgradeLedgerError("invalid EngineeringStore upgrade metadata")
        if marker.get("schema_version") != _STORE_LEDGER_SCHEMA_VERSION:
            raise UpgradeLedgerError("unsupported EngineeringStore upgrade ledger schema")
        if marker.get("namespace") != self.namespace:
            raise UpgradeLedgerError("EngineeringStore upgrade namespace mismatch")
        if marker.get("record_type") != expected_type:
            raise UpgradeLedgerError("EngineeringStore upgrade record type mismatch")
        return marker

    def _task_id(self, fingerprint: str) -> str:
        return f"{self._task_prefix}{fingerprint}"

    @staticmethod
    def _serialize_item(item: UpgradeWorkItem, *, state: WorkState | None = None) -> dict[str, Any]:
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

    @staticmethod
    def _deserialize_item(
        record: dict[str, Any],
        *,
        fallback: UpgradeWorkItem | None = None,
        attempts: int | None = None,
    ) -> UpgradeWorkItem:
        try:
            return UpgradeWorkItem(
                title=str(record.get("title", fallback.title if fallback else "")),
                kind=WorkKind(str(record.get("kind", fallback.kind.value if fallback else ""))),
                payload=dict(record.get("payload", fallback.payload if fallback else {})),
                priority=int(record.get("priority", fallback.priority if fallback else 50)),
                risk=str(record.get("risk", fallback.risk if fallback else "medium")),
                max_attempts=int(record.get("max_attempts", fallback.max_attempts if fallback else 2)),
                item_id=str(record.get("item_id", fallback.item_id if fallback else "")),
                state=WorkState.PENDING,
                attempts=int(record.get("attempts", 0) if attempts is None else attempts),
                last_error=str(record.get("last_error", "")),
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise UpgradeLedgerError(f"invalid EngineeringStore upgrade work record: {exc}") from exc

"""Bounded meta-loop for upgrade, update, repair, and feature implementation work.

The service deliberately keeps side effects behind injected callbacks. This lets zcoder
reuse its existing engineering/runtime adapters while the loop owns prioritisation,
retry budgets, regression guards, idempotency, and checkpointing.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence


class WorkKind(str, enum.Enum):
    """Kinds of work the continuous loop can schedule."""

    UPGRADE = "UPGRADE"
    UPDATE = "UPDATE"
    IMPLEMENT_FEATURE = "IMPLEMENT_FEATURE"
    REPAIR = "REPAIR"


class WorkState(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"


class LoopState(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    HALTED = "HALTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class ValidationResult:
    """Post-change validation outcome for one work item."""

    passed: bool
    summary: str = ""
    regressions: Sequence[str] = ()


@dataclass
class UpgradeWorkItem:
    """One independently verifiable vertical slice."""

    title: str
    kind: WorkKind
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    risk: str = "medium"
    max_attempts: int = 2
    item_id: str = field(default_factory=lambda: f"work_{uuid.uuid4().hex}")
    state: WorkState = WorkState.PENDING
    attempts: int = 0
    last_error: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    @property
    def fingerprint(self) -> str:
        """Stable content fingerprint used to deduplicate discovered work."""

        encoded = json.dumps(
            {
                "kind": self.kind.value,
                "title": self.title.strip(),
                "payload": self.payload,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LoopPolicy:
    """Safety and progress budgets for the meta-loop."""

    max_iterations: int = 12
    max_no_progress_iterations: int = 3
    stop_on_regression: bool = True

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.max_no_progress_iterations < 1:
            raise ValueError("max_no_progress_iterations must be >= 1")


@dataclass(frozen=True)
class LoopCheckpoint:
    iteration: int
    state: LoopState
    active_item_id: Optional[str]
    completed_item_ids: Sequence[str]
    blocked_item_ids: Sequence[str]
    pending_item_ids: Sequence[str]
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class IterationRecord:
    iteration: int
    item_id: str
    title: str
    kind: WorkKind
    attempt: int
    outcome: str
    validation_summary: str = ""
    regressions: Sequence[str] = ()


@dataclass(frozen=True)
class LoopReport:
    state: LoopState
    iterations: int
    completed_item_ids: Sequence[str]
    blocked_item_ids: Sequence[str]
    pending_item_ids: Sequence[str]
    records: Sequence[IterationRecord]
    halt_reason: str = ""


DiscoverCallback = Callable[[], Iterable[UpgradeWorkItem]]
ImplementCallback = Callable[[UpgradeWorkItem], Any]
ValidateCallback = Callable[[UpgradeWorkItem, Any], ValidationResult]
RollbackCallback = Callable[[UpgradeWorkItem, Any], None]
CheckpointCallback = Callable[[LoopCheckpoint], None]


class ContinuousUpgradeLoop:
    """Run bounded upgrade/update/feature work until complete or safely halted.

    Discovery can be called on every iteration, so new CI failures, dependency updates,
    or requested features can enter the queue without duplicating already-seen work.
    The implementation and validation callbacks are intentionally injected; this service
    can therefore sit above the existing AutonomousEngineeringLoop, GitHub orchestrator,
    local-only runtime, or tests without coupling the application layer to a provider.
    """

    def __init__(
        self,
        discover: DiscoverCallback,
        implement: ImplementCallback,
        validate: ValidateCallback,
        *,
        rollback: Optional[RollbackCallback] = None,
        checkpoint: Optional[CheckpointCallback] = None,
        policy: Optional[LoopPolicy] = None,
    ) -> None:
        self.discover = discover
        self.implement = implement
        self.validate = validate
        self.rollback = rollback
        self.checkpoint = checkpoint
        self.policy = policy or LoopPolicy()
        self._items: dict[str, UpgradeWorkItem] = {}
        self._fingerprints: set[str] = set()

    def add_work(self, item: UpgradeWorkItem) -> bool:
        """Add work once. Returns False when an equivalent item already exists."""

        fingerprint = item.fingerprint
        if fingerprint in self._fingerprints:
            return False
        self._fingerprints.add(fingerprint)
        self._items[item.item_id] = item
        return True

    def run(self, seed_items: Iterable[UpgradeWorkItem] = ()) -> LoopReport:
        for item in seed_items:
            self.add_work(item)

        records: list[IterationRecord] = []
        completed: list[str] = []
        blocked: list[str] = []
        no_progress = 0
        halt_reason = ""
        final_state = LoopState.RUNNING
        iterations = 0

        for iteration in range(1, self.policy.max_iterations + 1):
            iterations = iteration
            try:
                discovered_items = self.discover()
                for discovered in discovered_items:
                    self.add_work(discovered)
            except Exception as exc:  # discovery is an external application boundary
                final_state = LoopState.HALTED
                halt_reason = f"discovery_error:{type(exc).__name__}"
                break

            item = self._next_pending()
            if item is None:
                if blocked:
                    final_state = LoopState.HALTED
                    halt_reason = "blocked_work_remaining"
                else:
                    final_state = LoopState.COMPLETED
                break

            item.state = WorkState.RUNNING
            item.attempts += 1
            changed: Any = None

            try:
                changed = self.implement(item)
                item.state = WorkState.VALIDATING
                validation = self.validate(item, changed)
            except Exception as exc:  # application boundary: record and bound failures
                item.last_error = f"{type(exc).__name__}: {exc}"
                exhausted = item.attempts >= item.max_attempts
                item.state = WorkState.BLOCKED if exhausted else WorkState.PENDING
                if exhausted:
                    blocked.append(item.item_id)
                records.append(
                    IterationRecord(
                        iteration=iteration,
                        item_id=item.item_id,
                        title=item.title,
                        kind=item.kind,
                        attempt=item.attempts,
                        outcome="BLOCKED" if exhausted else "RETRY",
                        validation_summary=item.last_error,
                    )
                )
                no_progress += 1
                self._emit_checkpoint(iteration, LoopState.RUNNING, item.item_id, completed, blocked)
                if no_progress >= self.policy.max_no_progress_iterations:
                    final_state = LoopState.HALTED
                    halt_reason = "no_progress_budget_exhausted"
                    break
                continue

            regressions = tuple(validation.regressions)
            regression_halt = bool(regressions) and self.policy.stop_on_regression
            if not validation.passed or regression_halt:
                if self.rollback is not None:
                    try:
                        self.rollback(item, changed)
                    except Exception as exc:
                        item.state = WorkState.BLOCKED
                        blocked.append(item.item_id)
                        item.last_error = f"rollback failed: {type(exc).__name__}: {exc}"
                        records.append(
                            IterationRecord(
                                iteration=iteration,
                                item_id=item.item_id,
                                title=item.title,
                                kind=item.kind,
                                attempt=item.attempts,
                                outcome="ROLLBACK_FAILED",
                                validation_summary=item.last_error,
                                regressions=regressions,
                            )
                        )
                        final_state = LoopState.HALTED
                        halt_reason = "rollback_failed"
                        break

                exhausted = item.attempts >= item.max_attempts
                item.state = WorkState.BLOCKED if exhausted or regression_halt else WorkState.PENDING
                if item.state == WorkState.BLOCKED:
                    blocked.append(item.item_id)

                records.append(
                    IterationRecord(
                        iteration=iteration,
                        item_id=item.item_id,
                        title=item.title,
                        kind=item.kind,
                        attempt=item.attempts,
                        outcome="REGRESSION_BLOCKED" if regression_halt else "VALIDATION_RETRY",
                        validation_summary=validation.summary,
                        regressions=regressions,
                    )
                )
                no_progress += 1
                self._emit_checkpoint(iteration, LoopState.RUNNING, item.item_id, completed, blocked)

                if regression_halt:
                    final_state = LoopState.HALTED
                    halt_reason = "regression_guard"
                    break
                if no_progress >= self.policy.max_no_progress_iterations:
                    final_state = LoopState.HALTED
                    halt_reason = "no_progress_budget_exhausted"
                    break
                continue

            item.state = WorkState.SUCCEEDED
            completed.append(item.item_id)
            no_progress = 0
            records.append(
                IterationRecord(
                    iteration=iteration,
                    item_id=item.item_id,
                    title=item.title,
                    kind=item.kind,
                    attempt=item.attempts,
                    outcome="SUCCEEDED",
                    validation_summary=validation.summary,
                )
            )
            self._emit_checkpoint(iteration, LoopState.RUNNING, item.item_id, completed, blocked)

        pending = self._pending_ids()
        if final_state == LoopState.RUNNING:
            if pending:
                final_state = LoopState.BUDGET_EXHAUSTED
                halt_reason = "iteration_budget_exhausted"
            elif blocked:
                final_state = LoopState.HALTED
                halt_reason = "blocked_work_remaining"
            else:
                final_state = LoopState.COMPLETED

        self._emit_checkpoint(iterations, final_state, None, completed, blocked)
        return LoopReport(
            state=final_state,
            iterations=iterations,
            completed_item_ids=tuple(completed),
            blocked_item_ids=tuple(dict.fromkeys(blocked)),
            pending_item_ids=tuple(pending),
            records=tuple(records),
            halt_reason=halt_reason,
        )

    def _next_pending(self) -> Optional[UpgradeWorkItem]:
        pending = [item for item in self._items.values() if item.state == WorkState.PENDING]
        if not pending:
            return None
        return sorted(pending, key=lambda item: (-item.priority, item.item_id))[0]

    def _pending_ids(self) -> list[str]:
        return [
            item.item_id
            for item in self._items.values()
            if item.state in {WorkState.PENDING, WorkState.RUNNING, WorkState.VALIDATING}
        ]

    def _emit_checkpoint(
        self,
        iteration: int,
        state: LoopState,
        active_item_id: Optional[str],
        completed: Sequence[str],
        blocked: Sequence[str],
    ) -> None:
        if self.checkpoint is None:
            return
        self.checkpoint(
            LoopCheckpoint(
                iteration=iteration,
                state=state,
                active_item_id=active_item_id,
                completed_item_ids=tuple(completed),
                blocked_item_ids=tuple(dict.fromkeys(blocked)),
                pending_item_ids=tuple(self._pending_ids()),
            )
        )


def work_from_maintenance_recommendation(recommendation: Any) -> UpgradeWorkItem:
    """Adapt Upgrade-23 maintenance recommendations into Upgrade-24 work items."""

    recommendation_type = str(getattr(recommendation, "type", "")).upper()
    kind_map = {
        "PATCH_DEPENDENCY": WorkKind.UPDATE,
        "REPAIR_CI": WorkKind.REPAIR,
    }
    kind = kind_map.get(recommendation_type, WorkKind.UPGRADE)
    reason = str(getattr(recommendation, "reason", "maintenance recommendation"))
    return UpgradeWorkItem(
        title=reason,
        kind=kind,
        payload={
            "recommendation_id": str(getattr(recommendation, "id", "")),
            "repository": str(getattr(recommendation, "repository", "")),
            "recommendation_type": recommendation_type,
        },
        priority=int(getattr(recommendation, "priority", 1)),
        risk=str(getattr(recommendation, "risk", "low")),
    )


def feature_work(title: str, description: str, *, priority: int = 50, risk: str = "medium") -> UpgradeWorkItem:
    """Convenience constructor for feature implementation work."""

    return UpgradeWorkItem(
        title=title.strip(),
        kind=WorkKind.IMPLEMENT_FEATURE,
        payload={"description": description.strip()},
        priority=priority,
        risk=risk,
    )

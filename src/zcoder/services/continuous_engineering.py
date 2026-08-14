"""End-to-end Upgrade-25 continuous engineering orchestration."""

from __future__ import annotations

import argparse
import dataclasses
import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from zcoder.services.upgrade_lease import UpgradeRunLease
from zcoder.services.upgrade_loop import (
    ContinuousUpgradeLoop,
    LoopCheckpoint,
    LoopPolicy,
    LoopReport,
    LoopState,
    UpgradeWorkItem,
    ValidationResult,
    WorkKind,
    feature_work,
    work_from_maintenance_recommendation,
)
from zcoder.services.upgrade_state import JsonUpgradeLedger, RepositorySnapshotter


@dataclasses.dataclass(frozen=True)
class EngineeringExecution:
    """Normalized result returned by an engineering runtime adapter."""

    task_id: str
    status: str
    raw_task: Any = dataclasses.field(repr=False, compare=False)
    ci_repair_passed: bool | None = None


class Upgrade20EngineeringExecutor:
    """Adapter from UpgradeWorkItem to the existing Upgrade-20 engineering runtime."""

    def __init__(
        self,
        engineering_loop: Any,
        snapshotter: RepositorySnapshotter,
        *,
        project_id: str = "zcoder-continuous-upgrades",
        task_source: Any = None,
        risk_mapper: Callable[[str], Any] | None = None,
        ci_repair: Callable[[UpgradeWorkItem, EngineeringExecution], bool] | None = None,
    ) -> None:
        self.engineering_loop = engineering_loop
        self.snapshotter = snapshotter
        self.project_id = project_id
        self.task_source = task_source
        self.risk_mapper = risk_mapper
        self.ci_repair = ci_repair

    def execute(self, item: UpgradeWorkItem) -> EngineeringExecution:
        task_id = f"upgrade25-{item.fingerprint[:20]}"
        prompt = self._prompt(item)
        project_id = str(item.payload.get("project_id") or self.project_id)
        create_kwargs: dict[str, Any] = {
            "task_id": task_id,
            "project_id": project_id,
            "description": prompt,
            "title": item.title,
        }
        if self.task_source is not None:
            create_kwargs["source"] = self.task_source
        if self.risk_mapper is not None:
            create_kwargs["risk"] = self.risk_mapper(item.risk)
        self.engineering_loop.create_task(**create_kwargs)

        raw_task = self.engineering_loop.run_engineering_loop(
            task_id=task_id,
            project_id=project_id,
            issue_prompt=prompt,
            codebase=self.snapshotter.snapshot(),
            failing_initially=bool(item.payload.get("failing_initially", item.kind == WorkKind.REPAIR)),
        )
        status = getattr(raw_task, "status", "UNKNOWN")
        normalized = str(getattr(status, "value", status)).upper()
        execution = EngineeringExecution(task_id=task_id, status=normalized, raw_task=raw_task)
        if self.ci_repair is not None and item.kind == WorkKind.REPAIR:
            execution = dataclasses.replace(execution, ci_repair_passed=bool(self.ci_repair(item, execution)))
        return execution

    def validate(self, item: UpgradeWorkItem, execution: EngineeringExecution) -> ValidationResult:
        if execution.ci_repair_passed is False:
            return ValidationResult(
                passed=False,
                summary=f"GitHub CI repair exhausted for Upgrade-20 task {execution.task_id}",
            )
        passed = execution.status == "SUCCEEDED"
        return ValidationResult(
            passed=passed,
            summary=(
                f"Upgrade-20 task {execution.task_id} succeeded"
                if passed
                else f"Upgrade-20 task {execution.task_id} ended in {execution.status}"
            ),
        )

    @staticmethod
    def _prompt(item: UpgradeWorkItem) -> str:
        description = str(item.payload.get("description", "")).strip()
        parts = [
            f"Work kind: {item.kind.value}",
            f"Title: {item.title}",
            f"Risk: {item.risk}",
        ]
        if description:
            parts.append(f"Description: {description}")
        parts.append("Preserve tests, security gates, backward compatibility, and repository conventions.")
        return "\n".join(parts)


def github_ci_repair_hook(
    orchestrator: Any, *, max_repairs: int = 3
) -> Callable[[UpgradeWorkItem, EngineeringExecution], bool]:
    """Adapt the existing GitHubOrchestrator bounded CI repair loop to Upgrade-25."""

    if max_repairs < 1:
        raise ValueError("max_repairs must be >= 1")

    def repair(item: UpgradeWorkItem, execution: EngineeringExecution) -> bool:
        job_id = str(item.payload.get("github_job_id", ""))
        repository = str(item.payload.get("github_repo", item.payload.get("repository", "")))
        pr_number = item.payload.get("github_pr")
        if not job_id or not repository or pr_number is None:
            return True
        return bool(
            orchestrator.execute_ci_repair_loop(job_id, repository, int(pr_number), max_repairs=max_repairs)
        )

    return repair


WorkSource = Callable[[], Iterable[UpgradeWorkItem]]


def maintenance_work_source(service: Any) -> WorkSource:
    """Bridge Upgrade-23 recommendations into the Upgrade-25 discovery pipeline."""

    def discover() -> Iterable[UpgradeWorkItem]:
        return [work_from_maintenance_recommendation(rec) for rec in service.generate_recommendations()]

    return discover


class ContinuousEngineeringPipeline:
    """Durable orchestration layer joining Upgrade-24 with an engineering executor."""

    def __init__(
        self,
        executor: Upgrade20EngineeringExecutor,
        ledger: JsonUpgradeLedger,
        *,
        work_sources: Sequence[WorkSource] = (),
        policy: LoopPolicy | None = None,
        retry_blocked: bool = False,
        run_lease: UpgradeRunLease | None = None,
    ) -> None:
        self.executor = executor
        self.ledger = ledger
        self.work_sources = tuple(work_sources)
        self.policy = policy or LoopPolicy()
        self.retry_blocked = retry_blocked
        self.run_lease = run_lease or UpgradeRunLease(
            ledger.path.with_name(f"{ledger.path.name}.run.lock")
        )
        self._items_by_id: dict[str, UpgradeWorkItem] = {}

    def run(self, seed_items: Iterable[UpgradeWorkItem] = ()) -> LoopReport:
        with self.run_lease:
            return self._run_locked(seed_items)

    def _run_locked(self, seed_items: Iterable[UpgradeWorkItem]) -> LoopReport:
        seed = self.ledger.load_resumable(retry_blocked=self.retry_blocked)
        seed.extend(self._restore(item) for item in seed_items)
        normalized_seed = [item for item in seed if item is not None]
        for item in normalized_seed:
            self._items_by_id[item.item_id] = item

        loop = ContinuousUpgradeLoop(
            discover=self._discover,
            implement=self._implement,
            validate=self._validate,
            checkpoint=self._checkpoint,
            policy=self.policy,
        )
        report = loop.run(normalized_seed)
        persisted_blocked = self.ledger.blocked_item_ids()
        if persisted_blocked:
            blocked_ids = tuple(dict.fromkeys((*report.blocked_item_ids, *persisted_blocked)))
            if report.state == LoopState.COMPLETED:
                return dataclasses.replace(
                    report,
                    state=LoopState.HALTED,
                    blocked_item_ids=blocked_ids,
                    halt_reason="persisted_blocked_work_remaining",
                )
            return dataclasses.replace(report, blocked_item_ids=blocked_ids)
        return report

    def _restore(self, item: UpgradeWorkItem) -> UpgradeWorkItem | None:
        return self.ledger.restore_or_register(item, retry_blocked=self.retry_blocked)

    def _discover(self) -> Iterable[UpgradeWorkItem]:
        discovered: list[UpgradeWorkItem] = []
        for source in self.work_sources:
            for candidate in source():
                item = self._restore(candidate)
                if item is None:
                    continue
                self._items_by_id[item.item_id] = item
                discovered.append(item)
        return discovered

    def _implement(self, item: UpgradeWorkItem) -> EngineeringExecution:
        self._items_by_id[item.item_id] = item
        return self.executor.execute(item)

    def _validate(self, item: UpgradeWorkItem, execution: EngineeringExecution) -> ValidationResult:
        return self.executor.validate(item, execution)

    def _checkpoint(self, checkpoint: LoopCheckpoint) -> None:
        self.ledger.record_checkpoint(checkpoint, self._items_by_id)


def _risk_mapper(task_risk: Any) -> Callable[[str], Any]:
    values = {str(member.value).lower(): member for member in task_risk}

    def map_risk(value: str) -> Any:
        return values.get(str(value).lower(), values["medium"])

    return map_risk


def build_local_pipeline(
    repository_root: str | Path,
    state_file: str | Path,
    *,
    project_id: str = "zcoder-continuous-upgrades",
    allow_push: bool = False,
    policy: LoopPolicy | None = None,
    retry_blocked: bool = False,
    work_sources: Sequence[WorkSource] = (),
    github_orchestrator: Any = None,
    max_ci_repairs: int = 3,
) -> ContinuousEngineeringPipeline:
    """Build the real local Upgrade-25 pipeline with Upgrade-20 as the executor."""

    from local_ai_stack import AutonomousEngineeringLoop, PushPolicy, TaskRisk, TaskSource

    push_policy = PushPolicy.AUTO_PUSH_ALLOWED if allow_push else PushPolicy.AUTO_LOCAL_ONLY
    executor = Upgrade20EngineeringExecutor(
        AutonomousEngineeringLoop(push_policy=push_policy),
        RepositorySnapshotter(repository_root),
        project_id=project_id,
        task_source=TaskSource.WORKFLOW,
        risk_mapper=_risk_mapper(TaskRisk),
        ci_repair=(
            github_ci_repair_hook(github_orchestrator, max_repairs=max_ci_repairs)
            if github_orchestrator is not None
            else None
        ),
    )
    return ContinuousEngineeringPipeline(
        executor,
        JsonUpgradeLedger(state_file),
        work_sources=work_sources,
        policy=policy,
        retry_blocked=retry_blocked,
    )


def _load_work_file(path: Path) -> list[UpgradeWorkItem]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read work file: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("work file must contain a JSON array")

    items: list[UpgradeWorkItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("each work file entry must be an object")
        kind = WorkKind(str(entry.get("kind", WorkKind.IMPLEMENT_FEATURE.value)).upper())
        item_payload = dict(entry.get("payload", {}))
        if entry.get("description"):
            item_payload.setdefault("description", str(entry["description"]))
        items.append(
            UpgradeWorkItem(
                title=str(entry.get("title", "")),
                kind=kind,
                payload=item_payload,
                priority=int(entry.get("priority", 50)),
                risk=str(entry.get("risk", "medium")),
                max_attempts=int(entry.get("max_attempts", 2)),
            )
        )
    return items


def _report_dict(report: LoopReport, ledger: JsonUpgradeLedger) -> dict[str, Any]:
    return {
        "state": report.state.value,
        "iterations": report.iterations,
        "completed_item_ids": list(report.completed_item_ids),
        "blocked_item_ids": list(report.blocked_item_ids),
        "pending_item_ids": list(report.pending_item_ids),
        "halt_reason": report.halt_reason,
        "terminal_ledger_counts": ledger.terminal_counts(),
        "records": [
            {
                "iteration": record.iteration,
                "item_id": record.item_id,
                "title": record.title,
                "kind": record.kind.value,
                "attempt": record.attempt,
                "outcome": record.outcome,
                "validation_summary": record.validation_summary,
                "regressions": list(record.regressions),
            }
            for record in report.records
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the durable ZCoder continuous engineering pipeline")
    parser.add_argument("--repository", default=".", help="Repository root to snapshot and improve")
    parser.add_argument("--state-file", default=".zcoder/upgrade-loop-state.json")
    parser.add_argument("--project-id", default="zcoder-continuous-upgrades")
    parser.add_argument("--feature", help="Seed one feature implementation item")
    parser.add_argument("--description", default="", help="Description for --feature")
    parser.add_argument("--work-file", type=Path, help="JSON array of upgrade/update/repair/feature work")
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--retry-blocked", action="store_true")
    parser.add_argument(
        "--allow-push",
        action="store_true",
        help="Opt in to Upgrade-20 AUTO_PUSH_ALLOWED; local-only is the safe default",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = Path(args.repository).resolve()
    state_file = Path(args.state_file)
    if not state_file.is_absolute():
        state_file = repository_root / state_file

    seed: list[UpgradeWorkItem] = []
    if args.feature:
        seed.append(feature_work(args.feature, args.description, priority=args.priority, risk=args.risk))
    if args.work_file:
        seed.extend(_load_work_file(args.work_file))

    policy = LoopPolicy(max_iterations=args.max_iterations)
    pipeline = build_local_pipeline(
        repository_root,
        state_file,
        project_id=args.project_id,
        allow_push=args.allow_push,
        policy=policy,
        retry_blocked=args.retry_blocked,
    )
    report = pipeline.run(seed)
    print(json.dumps(_report_dict(report, pipeline.ledger), indent=2, sort_keys=True))
    return 0 if report.state == LoopState.COMPLETED else 2


if __name__ == "__main__":
    raise SystemExit(main())

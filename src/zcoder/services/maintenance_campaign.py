"""One-shot bounded maintenance campaigns over the continuous engineering pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from zcoder.domain.models.intelligence import MaintenanceSignal, SignalType
from zcoder.services.continuous_engineering import (
    ContinuousEngineeringPipeline,
    build_local_pipeline,
    build_postgres_store_pipeline,
    build_sqlite_store_pipeline,
)
from zcoder.services.maintenance_intelligence import MaintenanceIntelligenceService
from zcoder.services.upgrade_loop import (
    LoopPolicy,
    LoopState,
    UpgradeWorkItem,
    work_from_maintenance_recommendation,
)


@dataclass(frozen=True)
class MaintenanceCampaignReport:
    """Secret-free structured result for one bounded maintenance campaign."""

    campaign_id: str
    state: str
    recommendations_discovered: int
    work_seeded: int
    iterations: int
    completed_count: int
    blocked_count: int
    pending_count: int
    halt_reason: str
    terminal_ledger_counts: dict[str, int]
    started_at: float
    finished_at: float

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["duration_seconds"] = self.duration_seconds
        return payload


def maintenance_campaign_work(recommendation: Any) -> UpgradeWorkItem:
    """Adapt a recommendation using a stable cross-campaign content identity.

    Upgrade-23 recommendation IDs are UUID-backed. They are intentionally not
    included in the campaign work payload because doing so would defeat durable
    cross-run deduplication for the same recommendation content.
    """

    base = work_from_maintenance_recommendation(recommendation)
    stable_content = {
        "kind": base.kind.value,
        "title": base.title.strip(),
        "repository": str(base.payload.get("repository", "")),
        "recommendation_type": str(base.payload.get("recommendation_type", "")),
        "priority": base.priority,
        "risk": base.risk,
    }
    encoded = json.dumps(stable_content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    recommendation_key = hashlib.sha256(encoded).hexdigest()
    return UpgradeWorkItem(
        title=base.title,
        kind=base.kind,
        payload={
            "repository": stable_content["repository"],
            "recommendation_type": stable_content["recommendation_type"],
            "recommendation_key": recommendation_key,
        },
        priority=base.priority,
        risk=base.risk,
        max_attempts=base.max_attempts,
    )


class MaintenanceCampaignService:
    """Run Upgrade-23 recommendations through one bounded pipeline invocation."""

    def __init__(self, pipeline: ContinuousEngineeringPipeline, intelligence: Any) -> None:
        self.pipeline = pipeline
        self.intelligence = intelligence

    def run(self) -> MaintenanceCampaignReport:
        started_at = time.time()
        recommendations = list(self.intelligence.generate_recommendations())
        work_by_fingerprint: dict[str, UpgradeWorkItem] = {}
        for recommendation in recommendations:
            item = maintenance_campaign_work(recommendation)
            work_by_fingerprint.setdefault(item.fingerprint, item)

        report = self.pipeline.run(work_by_fingerprint.values())
        finished_at = time.time()
        return MaintenanceCampaignReport(
            campaign_id=f"maintenance-{uuid.uuid4().hex}",
            state=report.state.value,
            recommendations_discovered=len(recommendations),
            work_seeded=len(work_by_fingerprint),
            iterations=report.iterations,
            completed_count=len(report.completed_item_ids),
            blocked_count=len(report.blocked_item_ids),
            pending_count=len(report.pending_item_ids),
            halt_reason=report.halt_reason,
            terminal_ledger_counts=self.pipeline.ledger.terminal_counts(),
            started_at=started_at,
            finished_at=finished_at,
        )


def load_signals_file(path: Path) -> list[MaintenanceSignal]:
    """Load deterministic maintenance signals from a JSON array."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read signals file: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("signals file must contain a JSON array")

    signals: list[MaintenanceSignal] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("each signal entry must be an object")
        try:
            signal_type = SignalType(str(entry.get("type", "")).upper())
        except ValueError as exc:
            raise ValueError(f"unsupported maintenance signal type: {entry.get('type')!r}") from exc
        evidence = entry.get("evidence", {})
        if not isinstance(evidence, dict):
            raise ValueError("signal evidence must be an object")
        signals.append(
            MaintenanceSignal(
                id=str(entry.get("id") or f"sig_{uuid.uuid4().hex}"),
                repository=str(entry.get("repository", "")),
                type=signal_type,
                severity=str(entry.get("severity", "medium")),
                source=str(entry.get("source", "campaign-input")),
                evidence=dict(evidence),
                detected_at=float(entry.get("detected_at", time.time())),
            )
        )
    return signals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded ZCoder maintenance campaign")
    parser.add_argument("--repository", default=".")
    parser.add_argument("--signals-file", type=Path)
    parser.add_argument("--state-backend", choices=["json", "sqlite", "postgres"], default="json")
    parser.add_argument("--state-file", default=".zcoder/upgrade-loop-state.json")
    parser.add_argument("--engineering-db", default=".zcoder/engineering.db")
    parser.add_argument("--ledger-namespace", default="zcoder-maintenance-campaign")
    parser.add_argument("--project-id", default="zcoder-maintenance-campaign")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--retry-blocked", action="store_true")
    parser.add_argument("--allow-push", action="store_true")
    return parser


def _resolve(repository_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def _build_pipeline(args: argparse.Namespace, repository_root: Path) -> ContinuousEngineeringPipeline:
    policy = LoopPolicy(max_iterations=args.max_iterations)
    common = {
        "ledger_namespace": args.ledger_namespace,
        "project_id": args.project_id,
        "allow_push": args.allow_push,
        "policy": policy,
        "retry_blocked": args.retry_blocked,
    }
    if args.state_backend == "postgres":
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise ValueError("DATABASE_URL must be set for PostgreSQL state backend")
        return build_postgres_store_pipeline(repository_root, database_url, **common)
    if args.state_backend == "sqlite":
        return build_sqlite_store_pipeline(
            repository_root,
            _resolve(repository_root, args.engineering_db),
            **common,
        )
    return build_local_pipeline(
        repository_root,
        _resolve(repository_root, args.state_file),
        project_id=args.project_id,
        allow_push=args.allow_push,
        policy=policy,
        retry_blocked=args.retry_blocked,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = Path(args.repository).resolve()
    intelligence = MaintenanceIntelligenceService()
    if args.signals_file is not None:
        for signal in load_signals_file(args.signals_file):
            intelligence.add_signal(signal)

    pipeline = _build_pipeline(args, repository_root)
    try:
        campaign = MaintenanceCampaignService(pipeline, intelligence).run()
        output = json.dumps(campaign.to_dict(), indent=2, sort_keys=True)
    finally:
        close = getattr(pipeline, "close", None)
        if callable(close):
            close()
    print(output)
    return 0 if campaign.state == LoopState.COMPLETED.value else 2


if __name__ == "__main__":
    raise SystemExit(main())

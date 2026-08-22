"""CLI composition helpers for continuous-engineering infrastructure backends."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import zcoder.services.continuous_engineering as continuous_engineering_service
from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from zcoder.services.continuous_engineering import (
    ContinuousEngineeringPipeline,
    WorkSource,
    _build_upgrade20_executor,
    _load_work_file,
    _report_dict,
    build_local_pipeline,
)
from zcoder.services.engineering_store_pipeline import build_engineering_store_pipeline
from zcoder.services.upgrade_lease import UpgradeRunLease
from zcoder.services.upgrade_loop import LoopPolicy, LoopReport, LoopState, UpgradeWorkItem, feature_work
from zcoder.services.upgrade_postgres_fence import PostgresUpgradeFence
from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease
from zcoder.services.upgrade_postgres_runtime import FencedUpgradeEngineeringStore, PostgresFencedRunLease
from zcoder.services.upgrade_store_ledger import EngineeringStoreUpgradeLedger


def build_sqlite_store_pipeline(
    repository_root: str | Path,
    db_path: str | Path,
    *,
    ledger_namespace: str = "zcoder-continuous-upgrades",
    lease_path: str | Path | None = None,
    project_id: str = "zcoder-continuous-upgrades",
    allow_push: bool = False,
    policy: LoopPolicy | None = None,
    retry_blocked: bool = False,
    work_sources: Sequence[WorkSource] = (),
    github_orchestrator: Any = None,
    max_ci_repairs: int = 3,
) -> ContinuousEngineeringPipeline:
    """Compose the same-host SQLite backend outside the service layer."""

    db = Path(db_path)
    lease = Path(lease_path) if lease_path is not None else db.with_name(f"{db.name}.upgrade-loop.lock")
    store = SQLiteEngineeringStore(db_path=db)
    return build_engineering_store_pipeline(
        repository_root,
        store,
        ledger_namespace=ledger_namespace,
        run_lease=UpgradeRunLease(lease),
        project_id=project_id,
        allow_push=allow_push,
        policy=policy,
        retry_blocked=retry_blocked,
        work_sources=work_sources,
        github_orchestrator=github_orchestrator,
        max_ci_repairs=max_ci_repairs,
    )


def run_sqlite_store_pipeline_once(
    repository_root: str | Path,
    db_path: str | Path,
    seed_items: Iterable[UpgradeWorkItem] = (),
    **pipeline_kwargs: Any,
) -> LoopReport:
    """Compose, execute, and close exactly one bounded SQLite pipeline run."""

    pipeline = build_sqlite_store_pipeline(repository_root, db_path, **pipeline_kwargs)
    try:
        return pipeline.run(seed_items)
    finally:
        pipeline.close()


def build_postgres_store_pipeline(
    repository_root: str | Path,
    database_url: str,
    *,
    ledger_namespace: str = "zcoder-continuous-upgrades",
    project_id: str = "zcoder-continuous-upgrades",
    allow_push: bool = False,
    policy: LoopPolicy | None = None,
    retry_blocked: bool = False,
    work_sources: Sequence[WorkSource] = (),
    github_orchestrator: Any = None,
    max_ci_repairs: int = 3,
) -> ContinuousEngineeringPipeline:
    """Compose the fenced multi-host PostgreSQL backend outside services."""

    if not database_url:
        raise ValueError("database_url must not be empty for PostgreSQL state backend")

    store = PostgresEngineeringStore(dsn=database_url)
    try:
        store.init_schema()
        probe = EngineeringStoreUpgradeLedger(store, namespace=ledger_namespace)
        fence = PostgresUpgradeFence(
            store.connection_scope,
            namespace=ledger_namespace,
            control_task_id=probe.control_task_id,
        )
        run_lease = PostgresFencedRunLease(
            PostgresAdvisoryRunLease(store.connection_scope, f"{ledger_namespace}:continuous-run"),
            fence,
        )
        fenced_store = FencedUpgradeEngineeringStore(store, fence, run_lease.require_token)
        ledger = EngineeringStoreUpgradeLedger(fenced_store, namespace=ledger_namespace)
        executor = _build_upgrade20_executor(
            repository_root,
            project_id=project_id,
            allow_push=allow_push,
            github_orchestrator=github_orchestrator,
            max_ci_repairs=max_ci_repairs,
        )
        return ContinuousEngineeringPipeline(
            executor,
            ledger,
            work_sources=work_sources,
            policy=policy,
            retry_blocked=retry_blocked,
            run_lease=run_lease,
            close_callback=store.close,
        )
    except Exception:
        store.close()
        raise


continuous_engineering_service.build_postgres_store_pipeline._outward_composer = build_postgres_store_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the continuous-engineering CLI parser at the outward composition boundary."""

    parser = argparse.ArgumentParser(description="Run the durable ZCoder continuous engineering pipeline")
    parser.add_argument("--repository", default=".", help="Repository root to snapshot and improve")
    parser.add_argument("--state-backend", choices=["json", "sqlite", "postgres"], default="json")
    parser.add_argument("--state-file", default=".zcoder/upgrade-loop-state.json")
    parser.add_argument("--engineering-db", default=".zcoder/engineering.db")
    parser.add_argument("--ledger-namespace", default="zcoder-continuous-upgrades")
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


def _resolve_repository_path(repository_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def main(argv: Sequence[str] | None = None) -> int:
    """Compose and execute exactly one bounded continuous-engineering CLI run."""

    try:
        from zcoder.infrastructure.observability.bootstrap import bootstrap_from_env

        bootstrap_from_env()
    except Exception:
        pass

    args = build_parser().parse_args(argv)
    repository_root = Path(args.repository).resolve()

    seed: list[UpgradeWorkItem] = []
    if args.feature:
        seed.append(feature_work(args.feature, args.description, priority=args.priority, risk=args.risk))
    if args.work_file:
        seed.extend(_load_work_file(args.work_file))

    policy = LoopPolicy(max_iterations=args.max_iterations)
    if args.state_backend == "sqlite":
        pipeline = build_sqlite_store_pipeline(
            repository_root,
            _resolve_repository_path(repository_root, args.engineering_db),
            ledger_namespace=args.ledger_namespace,
            project_id=args.project_id,
            allow_push=args.allow_push,
            policy=policy,
            retry_blocked=args.retry_blocked,
        )
    elif args.state_backend == "postgres":
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise ValueError("DATABASE_URL must be set for PostgreSQL state backend")
        pipeline = build_postgres_store_pipeline(
            repository_root,
            database_url,
            ledger_namespace=args.ledger_namespace,
            project_id=args.project_id,
            allow_push=args.allow_push,
            policy=policy,
            retry_blocked=args.retry_blocked,
        )
    else:
        pipeline = build_local_pipeline(
            repository_root,
            _resolve_repository_path(repository_root, args.state_file),
            project_id=args.project_id,
            allow_push=args.allow_push,
            policy=policy,
            retry_blocked=args.retry_blocked,
        )

    try:
        report = pipeline.run(seed)
        output = json.dumps(_report_dict(report, pipeline.ledger), indent=2, sort_keys=True)
    finally:
        close = getattr(pipeline, "close", None)
        if callable(close):
            close()
    print(output)
    return 0 if report.state == LoopState.COMPLETED else 2


if __name__ == "__main__":
    raise SystemExit(main())

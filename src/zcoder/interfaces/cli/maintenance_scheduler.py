"""CLI composition root for the bounded scheduled maintenance-campaign loop."""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from zcoder.domain.services.control_plane import ControlPlaneStore
from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore
from zcoder.interfaces.cli.continuous_engineering import (
    build_postgres_store_pipeline,
    build_sqlite_store_pipeline,
)
from zcoder.services.continuous_engineering import build_local_pipeline
from zcoder.services.maintenance_campaign_delivery import (
    deliver_maintenance_campaign_summary_once,
)
from zcoder.services.maintenance_campaign_worker import run_maintenance_campaign_worker_once
from zcoder.services.maintenance_intelligence import MaintenanceIntelligenceService
from zcoder.services.maintenance_scheduler import (
    MaintenanceScheduler,
    install_sigterm_stop,
)
from zcoder.services.upgrade_lease import UpgradeRunLease
from zcoder.services.upgrade_loop import LoopPolicy
from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the maintenance-scheduler CLI parser at the outward composition boundary."""

    parser = argparse.ArgumentParser(
        description="Run bounded recurring ZCoder maintenance campaigns under one namespace lease"
    )
    parser.add_argument("--repository", default=".", help="Repository root to snapshot and improve")
    parser.add_argument("--backend", choices=["json", "sqlite", "postgres"], default="json")
    parser.add_argument("--state-file", default=".zcoder/upgrade-loop-state.json")
    parser.add_argument("--engineering-db", default=".zcoder/engineering.db")
    parser.add_argument("--control-plane-db", default=".zcoder/control_plane.db")
    parser.add_argument("--ledger-namespace", default="zcoder-maintenance-campaign")
    parser.add_argument("--project-id", default="zcoder-maintenance-campaign")
    parser.add_argument(
        "--namespace",
        default="zcoder-maintenance-scheduler",
        help="Exclusive lease namespace shared by competing schedulers",
    )
    parser.add_argument("--every-seconds", type=float, default=300.0)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--outbox-max-messages", type=int, default=100)
    parser.add_argument("--outbox-max-attempts", type=int, default=3)
    parser.add_argument("--retry-blocked", action="store_true")
    parser.add_argument("--allow-push", action="store_true")
    return parser


def _resolve(repository_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def _build_pipeline(args: argparse.Namespace, repository_root: Path) -> Any:
    policy = LoopPolicy(max_iterations=args.max_iterations)
    common = {
        "ledger_namespace": args.ledger_namespace,
        "project_id": args.project_id,
        "allow_push": args.allow_push,
        "policy": policy,
        "retry_blocked": args.retry_blocked,
    }
    if args.backend == "postgres":
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise ValueError("DATABASE_URL must be set for PostgreSQL state backend")
        return build_postgres_store_pipeline(repository_root, database_url, **common)
    if args.backend == "sqlite":
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


def _build_lease_factory(
    args: argparse.Namespace, repository_root: Path
) -> tuple[Callable[[], Any], Callable[[], None]]:
    """Compose the namespace lease factory plus a closer for its backing resources."""

    if args.backend != "postgres":
        lease_path = repository_root / ".zcoder" / f"{args.namespace}.lease"

        def file_lease_factory() -> UpgradeRunLease:
            return UpgradeRunLease(lease_path)

        return file_lease_factory, lambda: None

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL must be set for PostgreSQL state backend")

    lease_store = PostgresEngineeringStore(dsn=database_url)

    def postgres_lease_factory() -> PostgresAdvisoryRunLease:
        return PostgresAdvisoryRunLease(lease_store.connection_scope, args.namespace)

    return postgres_lease_factory, lease_store.close


def _log_delivery_sink(idempotency_key: str, payload: dict[str, Any]) -> None:
    LOGGER.info(
        "delivered maintenance campaign summary %s (exit_code=%s)",
        idempotency_key,
        payload.get("exit_code"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Compose real collaborators and run the bounded scheduler loop."""

    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args(argv)
    repository_root = Path(args.repository).resolve()
    stop_event = threading.Event()
    install_sigterm_stop(stop_event)

    intelligence = MaintenanceIntelligenceService()
    pipeline = _build_pipeline(args, repository_root)
    try:
        outbox = ControlPlaneStore(_resolve(repository_root, args.control_plane_db))

        def campaign_runner() -> Any:
            return run_maintenance_campaign_worker_once(pipeline, intelligence, outbox)

        def delivery_handler(action: str, payload: dict[str, Any]) -> None:
            deliver_maintenance_campaign_summary_once(action, payload, _log_delivery_sink)

        lease_factory, close_leases = _build_lease_factory(args, repository_root)
        try:
            results = MaintenanceScheduler(
                lease_factory=lease_factory,
                campaign_runner=campaign_runner,
                outbox_processor=partial(outbox.process_outbox, delivery_handler),
                every_seconds=args.every_seconds,
                max_cycles=args.max_cycles,
                stop_event=stop_event,
                outbox_max_messages=args.outbox_max_messages,
                outbox_max_attempts=args.outbox_max_attempts,
            ).run()
        finally:
            close_leases()
    finally:
        close = getattr(pipeline, "close", None)
        if callable(close):
            close()

    print(
        json.dumps(
            [
                {
                    "cycle_index": r.cycle_index,
                    "campaign_ran": r.campaign_ran,
                    "outbox_processed": r.outbox_processed,
                    "skipped_reason": r.skipped_reason,
                }
                for r in results
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if all(r.skipped_reason == "" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

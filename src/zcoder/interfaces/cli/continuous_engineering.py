"""CLI composition helpers for continuous-engineering infrastructure backends."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from zcoder.services.continuous_engineering import (
    ContinuousEngineeringPipeline,
    WorkSource,
    _build_upgrade20_executor,
)
from zcoder.services.upgrade_lease import UpgradeRunLease
from zcoder.services.upgrade_loop import LoopPolicy
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
    executor = _build_upgrade20_executor(
        repository_root,
        project_id=project_id,
        allow_push=allow_push,
        github_orchestrator=github_orchestrator,
        max_ci_repairs=max_ci_repairs,
    )
    ledger = EngineeringStoreUpgradeLedger(SQLiteEngineeringStore(db_path=db), namespace=ledger_namespace)
    return ContinuousEngineeringPipeline(
        executor,
        ledger,
        work_sources=work_sources,
        policy=policy,
        retry_blocked=retry_blocked,
        run_lease=UpgradeRunLease(lease),
    )

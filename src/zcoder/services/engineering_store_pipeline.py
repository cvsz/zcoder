"""Backend-agnostic composition for EngineeringStore-backed upgrade pipelines."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from zcoder.services.continuous_engineering import (
    ContinuousEngineeringPipeline,
    WorkSource,
    _build_upgrade20_executor,
)
from zcoder.services.upgrade_lease import RunLease
from zcoder.services.upgrade_loop import LoopPolicy
from zcoder.services.upgrade_store_ledger import EngineeringStoreUpgradeLedger


def build_engineering_store_pipeline(
    repository_root: str | Path,
    store: Any,
    *,
    ledger_namespace: str = "zcoder-continuous-upgrades",
    run_lease: RunLease,
    project_id: str = "zcoder-continuous-upgrades",
    allow_push: bool = False,
    policy: LoopPolicy | None = None,
    retry_blocked: bool = False,
    work_sources: Sequence[WorkSource] = (),
    github_orchestrator: Any = None,
    max_ci_repairs: int = 3,
    close_callback: Callable[[], None] | None = None,
) -> ContinuousEngineeringPipeline:
    """Compose one store-backed pipeline without knowing the concrete store adapter."""

    executor = _build_upgrade20_executor(
        repository_root,
        project_id=project_id,
        allow_push=allow_push,
        github_orchestrator=github_orchestrator,
        max_ci_repairs=max_ci_repairs,
    )
    ledger = EngineeringStoreUpgradeLedger(store, namespace=ledger_namespace)
    return ContinuousEngineeringPipeline(
        executor,
        ledger,
        work_sources=work_sources,
        policy=policy,
        retry_blocked=retry_blocked,
        run_lease=run_lease,
        close_callback=close_callback,
    )

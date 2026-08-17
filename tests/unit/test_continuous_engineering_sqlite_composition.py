from pathlib import Path
from types import SimpleNamespace

import zcoder.interfaces.cli.continuous_engineering as composition


def test_sqlite_composition_builds_one_store_and_preserves_bounded_inputs(monkeypatch, tmp_path):
    calls = SimpleNamespace(store=[], executor=[], ledger=[], lease=[], pipeline=[])
    store = object()
    executor = object()
    ledger = object()
    run_lease = object()
    pipeline = object()

    def fake_store(*, db_path):
        calls.store.append(db_path)
        return store

    def fake_executor(repository_root, **kwargs):
        calls.executor.append((repository_root, kwargs))
        return executor

    def fake_ledger(actual_store, *, namespace):
        calls.ledger.append((actual_store, namespace))
        return ledger

    def fake_lease(path):
        calls.lease.append(path)
        return run_lease

    def fake_pipeline(actual_executor, actual_ledger, **kwargs):
        calls.pipeline.append((actual_executor, actual_ledger, kwargs))
        return pipeline

    monkeypatch.setattr(composition, "SQLiteEngineeringStore", fake_store)
    monkeypatch.setattr(composition, "_build_upgrade20_executor", fake_executor)
    monkeypatch.setattr(composition, "EngineeringStoreUpgradeLedger", fake_ledger)
    monkeypatch.setattr(composition, "UpgradeRunLease", fake_lease)
    monkeypatch.setattr(composition, "ContinuousEngineeringPipeline", fake_pipeline)

    db_path = tmp_path / "engineering.db"
    work_source = lambda: ()
    policy = object()
    github = object()

    result = composition.build_sqlite_store_pipeline(
        "/repo",
        db_path,
        ledger_namespace="upgrade-test",
        project_id="project-test",
        allow_push=True,
        policy=policy,
        retry_blocked=True,
        work_sources=(work_source,),
        github_orchestrator=github,
        max_ci_repairs=2,
    )

    assert result is pipeline
    assert calls.store == [db_path]
    assert calls.executor == [
        (
            "/repo",
            {
                "project_id": "project-test",
                "allow_push": True,
                "github_orchestrator": github,
                "max_ci_repairs": 2,
            },
        )
    ]
    assert calls.ledger == [(store, "upgrade-test")]
    assert calls.lease == [Path(f"{db_path}.upgrade-loop.lock")]
    assert calls.pipeline == [
        (
            executor,
            ledger,
            {
                "work_sources": (work_source,),
                "policy": policy,
                "retry_blocked": True,
                "run_lease": run_lease,
            },
        )
    ]


def test_sqlite_composition_honors_explicit_lease_path(monkeypatch, tmp_path):
    captured = []

    monkeypatch.setattr(composition, "SQLiteEngineeringStore", lambda *, db_path: object())
    monkeypatch.setattr(composition, "_build_upgrade20_executor", lambda *args, **kwargs: object())
    monkeypatch.setattr(composition, "EngineeringStoreUpgradeLedger", lambda *args, **kwargs: object())
    monkeypatch.setattr(composition, "UpgradeRunLease", lambda path: captured.append(path) or object())
    monkeypatch.setattr(composition, "ContinuousEngineeringPipeline", lambda *args, **kwargs: object())

    lease_path = tmp_path / "custom.lock"
    composition.build_sqlite_store_pipeline(
        "/repo",
        tmp_path / "engineering.db",
        lease_path=lease_path,
    )

    assert captured == [lease_path]

from pathlib import Path
from types import SimpleNamespace

import zcoder.interfaces.cli.continuous_engineering as composition


def test_sqlite_composition_builds_one_store_and_preserves_bounded_inputs(monkeypatch, tmp_path):
    calls = SimpleNamespace(store=[], lease=[], seam=[])
    store = object()
    run_lease = object()
    pipeline = object()

    def fake_store(*, db_path):
        calls.store.append(db_path)
        return store

    def fake_lease(path):
        calls.lease.append(path)
        return run_lease

    def fake_seam(repository_root, actual_store, **kwargs):
        calls.seam.append((repository_root, actual_store, kwargs))
        return pipeline

    def work_source():
        return ()

    monkeypatch.setattr(composition, "SQLiteEngineeringStore", fake_store)
    monkeypatch.setattr(composition, "UpgradeRunLease", fake_lease)
    monkeypatch.setattr(composition, "build_engineering_store_pipeline", fake_seam)

    db_path = tmp_path / "engineering.db"
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
    assert calls.lease == [Path(f"{db_path}.upgrade-loop.lock")]
    assert calls.seam == [
        (
            "/repo",
            store,
            {
                "ledger_namespace": "upgrade-test",
                "run_lease": run_lease,
                "project_id": "project-test",
                "allow_push": True,
                "policy": policy,
                "retry_blocked": True,
                "work_sources": (work_source,),
                "github_orchestrator": github,
                "max_ci_repairs": 2,
            },
        )
    ]


def test_sqlite_composition_honors_explicit_lease_path(monkeypatch, tmp_path):
    captured = []

    monkeypatch.setattr(composition, "SQLiteEngineeringStore", lambda *, db_path: object())
    monkeypatch.setattr(composition, "UpgradeRunLease", lambda path: captured.append(path) or object())
    monkeypatch.setattr(composition, "build_engineering_store_pipeline", lambda *args, **kwargs: object())

    lease_path = tmp_path / "custom.lock"
    composition.build_sqlite_store_pipeline(
        "/repo",
        tmp_path / "engineering.db",
        lease_path=lease_path,
    )

    assert captured == [lease_path]

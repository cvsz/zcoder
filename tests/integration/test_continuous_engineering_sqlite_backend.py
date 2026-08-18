"""Upgrade-29 integration coverage for SQLite EngineeringStore pipeline wiring."""

from types import SimpleNamespace

import pytest

import zcoder.interfaces.cli.continuous_engineering as continuous_engineering_cli
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from zcoder.services.continuous_engineering import ContinuousEngineeringPipeline
from zcoder.services.upgrade_lease import UpgradeRunLease
from zcoder.services.upgrade_loop import LoopPolicy, LoopReport, LoopState, ValidationResult, feature_work
from zcoder.services.upgrade_store_ledger import EngineeringStoreUpgradeLedger


class PassingExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, item):
        self.calls.append(item.fingerprint)
        return SimpleNamespace(task_id=item.item_id, status="SUCCEEDED")

    def validate(self, item, execution):
        return ValidationResult(passed=True, summary="passed")


def test_generic_pathless_ledger_requires_explicit_run_lease():
    pathless_ledger = SimpleNamespace()

    with pytest.raises(ValueError, match="run_lease is required"):
        ContinuousEngineeringPipeline(PassingExecutor(), pathless_ledger)


def test_sqlite_builder_uses_store_ledger_and_sidecar_lease(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    db_path = tmp_path / "state" / "engineering.db"
    executor = PassingExecutor()
    monkeypatch.setattr(
        continuous_engineering_cli,
        "build_engineering_store_pipeline",
        lambda repository_root, store, **kwargs: ContinuousEngineeringPipeline(
            executor,
            EngineeringStoreUpgradeLedger(store, namespace=kwargs["ledger_namespace"]),
            policy=kwargs.get("policy"),
            retry_blocked=kwargs.get("retry_blocked", False),
            work_sources=kwargs.get("work_sources", ()),
            run_lease=kwargs["run_lease"],
        ),
    )

    pipeline = continuous_engineering_cli.build_sqlite_store_pipeline(
        repository,
        db_path,
        ledger_namespace="fleet-test",
    )

    assert isinstance(pipeline.ledger, EngineeringStoreUpgradeLedger)
    assert pipeline.ledger.namespace == "fleet-test"
    assert pipeline.run_lease.path == db_path.with_name("engineering.db.upgrade-loop.lock")
    assert pipeline.ledger.store.list_tasks(status="CREATED") == []


def test_sqlite_pipeline_persists_success_and_skips_restart_duplicate(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    db_path = tmp_path / "engineering.db"
    lease_path = tmp_path / "upgrade.lock"
    item = feature_work("Store-backed feature", "Execute exactly once")

    first_executor = PassingExecutor()
    first = ContinuousEngineeringPipeline(
        first_executor,
        EngineeringStoreUpgradeLedger(SQLiteEngineeringStore(db_path=db_path), namespace="resume-test"),
        policy=LoopPolicy(max_iterations=3),
        run_lease=UpgradeRunLease(lease_path),
    )
    first_report = first.run([item])

    assert first_report.state == LoopState.COMPLETED
    assert first_executor.calls == [item.fingerprint]
    assert not lease_path.exists()

    second_executor = PassingExecutor()
    restarted = ContinuousEngineeringPipeline(
        second_executor,
        EngineeringStoreUpgradeLedger(SQLiteEngineeringStore(db_path=db_path), namespace="resume-test"),
        policy=LoopPolicy(max_iterations=3),
        run_lease=UpgradeRunLease(lease_path),
    )
    second_report = restarted.run([feature_work("Store-backed feature", "Execute exactly once")])

    assert second_report.state == LoopState.COMPLETED
    assert second_executor.calls == []
    assert restarted.ledger.terminal_counts()["SUCCEEDED"] == 1
    assert not lease_path.exists()


def test_cli_defaults_to_json_and_accepts_sqlite_backend():
    defaults = continuous_engineering_cli.build_parser().parse_args([])
    sqlite = continuous_engineering_cli.build_parser().parse_args(
        ["--state-backend", "sqlite", "--engineering-db", "fleet.db", "--ledger-namespace", "fleet-a"]
    )

    assert defaults.state_backend == "json"
    assert defaults.state_file == ".zcoder/upgrade-loop-state.json"
    assert sqlite.state_backend == "sqlite"
    assert sqlite.engineering_db == "fleet.db"
    assert sqlite.ledger_namespace == "fleet-a"


def test_main_routes_sqlite_backend_to_store_builder(tmp_path, monkeypatch, capsys):
    captured = {}
    fake_ledger = SimpleNamespace(terminal_counts=lambda: {"SUCCEEDED": 0, "BLOCKED": 0})
    fake_report = LoopReport(
        state=LoopState.COMPLETED,
        iterations=0,
        completed_item_ids=(),
        blocked_item_ids=(),
        pending_item_ids=(),
        records=(),
    )
    fake_pipeline = SimpleNamespace(ledger=fake_ledger, run=lambda seed: fake_report, close=lambda: None)

    def fake_builder(repository_root, db_path, **kwargs):
        captured["repository_root"] = repository_root
        captured["db_path"] = db_path
        captured.update(kwargs)
        return fake_pipeline

    monkeypatch.setattr(continuous_engineering_cli, "build_sqlite_store_pipeline", fake_builder)

    result = continuous_engineering_cli.main(
        [
            "--repository",
            str(tmp_path),
            "--state-backend",
            "sqlite",
            "--engineering-db",
            "state/engineering.db",
            "--ledger-namespace",
            "fleet-main",
        ]
    )

    assert result == 0
    assert captured["repository_root"] == tmp_path.resolve()
    assert captured["db_path"] == tmp_path.resolve() / "state/engineering.db"
    assert captured["ledger_namespace"] == "fleet-main"
    assert '"state": "COMPLETED"' in capsys.readouterr().out

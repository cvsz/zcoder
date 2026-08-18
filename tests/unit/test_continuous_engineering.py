"""Unit tests for Upgrade-25 durable continuous engineering orchestration."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from zcoder.services.continuous_engineering import (
    ContinuousEngineeringPipeline,
    JsonUpgradeLedger,
    RepositorySnapshotter,
    Upgrade20EngineeringExecutor,
    _load_work_file,
    github_ci_repair_hook,
    maintenance_work_source,
)
from zcoder.services.upgrade_lease import UpgradeRunLeaseError
from zcoder.services.upgrade_loop import LoopPolicy, LoopState, UpgradeWorkItem, WorkKind, feature_work
from zcoder.services.upgrade_state import UpgradeLedgerError


class FakeStatus:
    def __init__(self, value: str):
        self.value = value


class FakeEngineeringLoop:
    def __init__(self, statuses=None):
        self.statuses = list(statuses or ["SUCCEEDED"])
        self.created = []
        self.runs = []

    def create_task(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(**kwargs)

    def run_engineering_loop(self, **kwargs):
        self.runs.append(kwargs)
        status = self.statuses.pop(0) if self.statuses else "SUCCEEDED"
        return SimpleNamespace(status=FakeStatus(status))


def build_pipeline(tmp_path, *, statuses=None, retry_blocked=False, work_sources=()):
    repository = tmp_path / "repo"
    repository.mkdir(exist_ok=True)
    (repository / "app.py").write_text("print('ok')\n", encoding="utf-8")
    loop = FakeEngineeringLoop(statuses=statuses)
    executor = Upgrade20EngineeringExecutor(
        loop,
        RepositorySnapshotter(repository),
        project_id="test-project",
        task_source="WORKFLOW",
        risk_mapper=lambda value: value.upper(),
    )
    ledger = JsonUpgradeLedger(tmp_path / "state.json")
    pipeline = ContinuousEngineeringPipeline(
        executor,
        ledger,
        work_sources=work_sources,
        policy=LoopPolicy(max_iterations=6, max_no_progress_iterations=3),
        retry_blocked=retry_blocked,
    )
    return pipeline, loop, ledger


def test_feature_runs_through_upgrade20_and_persists_success(tmp_path):
    pipeline, engineering_loop, ledger = build_pipeline(tmp_path)
    item = feature_work("Implement status endpoint", "Add a health/status endpoint", risk="high")

    report = pipeline.run([item])

    assert report.state == LoopState.COMPLETED
    assert len(engineering_loop.runs) == 1
    assert engineering_loop.created[0]["source"] == "WORKFLOW"
    assert engineering_loop.created[0]["risk"] == "HIGH"
    assert engineering_loop.runs[0]["codebase"]["app.py"] == "print('ok')\n"
    assert ledger.state_for(item.fingerprint) == "SUCCEEDED"
    assert not pipeline.run_lease.path.exists()


def test_competing_runner_fails_before_ledger_or_upgrade20(tmp_path, monkeypatch):
    first, _, _ = build_pipeline(tmp_path)
    second, second_engineering_loop, second_ledger = build_pipeline(tmp_path)
    item = feature_work("Concurrent feature", "Must not start while another runner owns the lease")

    def fail_if_ledger_read(*args, **kwargs):
        pytest.fail("competing runner touched durable ledger")

    monkeypatch.setattr(second_ledger, "load_resumable", fail_if_ledger_read)
    assert second.run_lease.wait_seconds == 0.0

    with first.run_lease:
        with pytest.raises(UpgradeRunLeaseError, match="already held"):
            second.run([item])

    assert not second_ledger.path.exists()
    assert second_engineering_loop.created == []
    assert second_engineering_loop.runs == []
    assert not first.run_lease.path.exists()


def test_restart_skips_already_completed_fingerprint(tmp_path):
    pipeline, engineering_loop, _ = build_pipeline(tmp_path)
    item = feature_work("Idempotent feature", "Do it once")
    first = pipeline.run([item])
    assert first.state == LoopState.COMPLETED
    assert len(engineering_loop.runs) == 1

    restarted, restarted_loop, ledger = build_pipeline(tmp_path)
    second = restarted.run([feature_work("Idempotent feature", "Do it once")])

    assert second.state == LoopState.COMPLETED
    assert restarted_loop.runs == []
    assert ledger.terminal_counts()["SUCCEEDED"] == 1


def test_failed_upgrade20_task_retries_then_blocks(tmp_path):
    pipeline, engineering_loop, ledger = build_pipeline(tmp_path, statuses=["FAILED", "FAILED"])
    item = UpgradeWorkItem("Repair CI", WorkKind.REPAIR, max_attempts=2)

    report = pipeline.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "blocked_work_remaining"
    assert len(engineering_loop.runs) == 2
    assert ledger.state_for(item.fingerprint) == "BLOCKED"


def test_restart_without_retry_keeps_persisted_blocker_visible(tmp_path):
    pipeline, _, ledger = build_pipeline(tmp_path, statuses=["FAILED"])
    item = UpgradeWorkItem("Blocked forever", WorkKind.UPDATE, max_attempts=1)
    first = pipeline.run([item])
    assert first.state == LoopState.HALTED
    assert ledger.state_for(item.fingerprint) == "BLOCKED"

    restarted, engineering_loop, _ = build_pipeline(tmp_path)
    second = restarted.run()

    assert second.state == LoopState.HALTED
    assert second.halt_reason == "persisted_blocked_work_remaining"
    assert item.item_id in second.blocked_item_ids
    assert engineering_loop.runs == []


def test_retry_blocked_resets_attempt_budget_on_restart(tmp_path):
    pipeline, _, ledger = build_pipeline(tmp_path, statuses=["FAILED"])
    item = UpgradeWorkItem("Retry dependency update", WorkKind.UPDATE, max_attempts=1)
    report = pipeline.run([item])
    assert report.state == LoopState.HALTED
    assert ledger.state_for(item.fingerprint) == "BLOCKED"

    restarted, engineering_loop, restarted_ledger = build_pipeline(
        tmp_path, statuses=["SUCCEEDED"], retry_blocked=True
    )
    retry_report = restarted.run()

    assert retry_report.state == LoopState.COMPLETED
    assert len(engineering_loop.runs) == 1
    assert restarted_ledger.state_for(item.fingerprint) == "SUCCEEDED"


def test_pending_item_is_resumed_after_restart(tmp_path):
    _, _, ledger = build_pipeline(tmp_path)
    item = feature_work("Resume me", "Persist before execution")
    restored = ledger.restore_or_register(item)
    assert restored is not None

    restarted, engineering_loop, restarted_ledger = build_pipeline(tmp_path)
    report = restarted.run()

    assert report.state == LoopState.COMPLETED
    assert len(engineering_loop.runs) == 1
    assert restarted_ledger.state_for(item.fingerprint) == "SUCCEEDED"


def test_maintenance_source_adapts_upgrade23_recommendations(tmp_path):
    recommendation = SimpleNamespace(
        id="rec-1",
        repository="cvsz/zcoder",
        type="PATCH_DEPENDENCY",
        priority=7,
        risk="low",
        reason="Dependency outdated: demo",
    )
    service = SimpleNamespace(generate_recommendations=lambda: [recommendation])
    pipeline, engineering_loop, ledger = build_pipeline(
        tmp_path,
        work_sources=(maintenance_work_source(service),),
    )

    report = pipeline.run()

    assert report.state == LoopState.COMPLETED
    assert len(engineering_loop.runs) == 1
    assert engineering_loop.created[0]["title"] == "Dependency outdated: demo"
    assert ledger.terminal_counts()["SUCCEEDED"] == 1


def test_github_ci_repair_hook_uses_existing_orchestrator_contract():
    calls = []
    orchestrator = SimpleNamespace(
        execute_ci_repair_loop=lambda job_id, repo, pr, max_repairs: (
            calls.append((job_id, repo, pr, max_repairs)) or True
        )
    )
    hook = github_ci_repair_hook(orchestrator, max_repairs=2)
    item = UpgradeWorkItem(
        "Repair PR CI",
        WorkKind.REPAIR,
        payload={"github_job_id": "job-1", "github_repo": "cvsz/zcoder", "github_pr": 8},
    )

    passed = hook(item, SimpleNamespace())

    assert passed is True
    assert calls == [("job-1", "cvsz/zcoder", 8, 2)]


def test_github_ci_repair_failure_blocks_validation(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "app.py").write_text("pass\n", encoding="utf-8")
    loop = FakeEngineeringLoop(statuses=["SUCCEEDED"] * 2)
    executor = Upgrade20EngineeringExecutor(
        loop,
        RepositorySnapshotter(repository),
        ci_repair=lambda item, execution: False,
    )
    pipeline = ContinuousEngineeringPipeline(
        executor,
        JsonUpgradeLedger(tmp_path / "state.json"),
        policy=LoopPolicy(max_iterations=3, max_no_progress_iterations=3),
    )
    item = UpgradeWorkItem("Repair PR CI", WorkKind.REPAIR, max_attempts=2)

    report = pipeline.run([item])

    assert report.state == LoopState.HALTED
    assert report.blocked_item_ids == (item.item_id,)
    assert len(loop.runs) == 2


def test_repository_snapshot_is_bounded_and_secret_aware(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (repository / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repository / "private.pem").write_text("SECRET\n", encoding="utf-8")
    git_dir = repository / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("secret-ish metadata\n", encoding="utf-8")
    oversized = repository / "large.txt"
    oversized.write_text("x" * 100, encoding="utf-8")

    snapshot = RepositorySnapshotter(repository, max_file_bytes=20).snapshot()

    assert snapshot == {"ok.py": "x = 1\n"}


def test_corrupt_ledger_fails_closed(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not-json", encoding="utf-8")
    ledger = JsonUpgradeLedger(path)

    with pytest.raises(UpgradeLedgerError):
        ledger.load_resumable()


def test_work_file_supports_all_work_kinds(tmp_path):
    work_file = tmp_path / "work.json"
    work_file.write_text(
        json.dumps(
            [
                {"title": "upgrade", "kind": "UPGRADE"},
                {"title": "update", "kind": "UPDATE"},
                {"title": "feature", "kind": "IMPLEMENT_FEATURE", "description": "ship it"},
                {"title": "repair", "kind": "REPAIR"},
            ]
        ),
        encoding="utf-8",
    )

    items = _load_work_file(work_file)

    assert [item.kind for item in items] == [
        WorkKind.UPGRADE,
        WorkKind.UPDATE,
        WorkKind.IMPLEMENT_FEATURE,
        WorkKind.REPAIR,
    ]
    assert items[2].payload["description"] == "ship it"


def test_work_file_rejects_non_array(tmp_path):
    work_file = tmp_path / "work.json"
    work_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array"):
        _load_work_file(work_file)

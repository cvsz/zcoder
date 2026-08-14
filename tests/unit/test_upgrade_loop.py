"""Unit tests for Upgrade-24 continuous upgrade/update/feature loop."""

from dataclasses import dataclass

from zcoder.services.upgrade_loop import (
    ContinuousUpgradeLoop,
    LoopPolicy,
    LoopState,
    UpgradeWorkItem,
    ValidationResult,
    WorkKind,
    feature_work,
    work_from_maintenance_recommendation,
)


def test_runs_upgrade_update_and_feature_work_in_priority_order():
    executed = []
    items = [
        UpgradeWorkItem("upgrade runtime", WorkKind.UPGRADE, priority=20),
        UpgradeWorkItem("update dependency", WorkKind.UPDATE, priority=30),
        feature_work("implement dashboard", "add status dashboard", priority=40),
    ]

    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda item: executed.append(item.title) or {"changed": item.item_id},
        validate=lambda item, changed: ValidationResult(True, summary="green"),
    )

    report = loop.run(items)

    assert report.state == LoopState.COMPLETED
    assert executed == ["implement dashboard", "update dependency", "upgrade runtime"]
    assert len(report.completed_item_ids) == 3
    assert all(record.outcome == "SUCCEEDED" for record in report.records)


def test_exact_iteration_budget_completes_when_last_item_succeeds():
    item = UpgradeWorkItem("single upgrade", WorkKind.UPGRADE)
    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: None,
        validate=lambda work, changed: ValidationResult(True),
        policy=LoopPolicy(max_iterations=1),
    )

    report = loop.run([item])

    assert report.state == LoopState.COMPLETED
    assert report.halt_reason == ""


def test_discovery_is_idempotent_by_content_fingerprint():
    discovered = UpgradeWorkItem("same update", WorkKind.UPDATE, payload={"package": "demo"})
    executions = []

    loop = ContinuousUpgradeLoop(
        discover=lambda: (discovered,),
        implement=lambda item: executions.append(item.item_id) or None,
        validate=lambda item, changed: ValidationResult(True),
    )

    report = loop.run()

    assert report.state == LoopState.COMPLETED
    assert executions == [discovered.item_id]


def test_failed_validation_retries_then_succeeds():
    item = UpgradeWorkItem("retry feature", WorkKind.IMPLEMENT_FEATURE, max_attempts=2)
    validations = iter(
        [
            ValidationResult(False, summary="test failed"),
            ValidationResult(True, summary="tests pass"),
        ]
    )

    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: {"attempt": work.attempts},
        validate=lambda work, changed: next(validations),
        policy=LoopPolicy(max_iterations=4, max_no_progress_iterations=3),
    )

    report = loop.run([item])

    assert report.state == LoopState.COMPLETED
    assert item.attempts == 2
    assert [record.outcome for record in report.records] == ["VALIDATION_RETRY", "SUCCEEDED"]


def test_exhausted_item_halts_when_blocked_work_remains():
    item = UpgradeWorkItem("blocked update", WorkKind.UPDATE, max_attempts=1)
    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: None,
        validate=lambda work, changed: ValidationResult(False, summary="still failing"),
        policy=LoopPolicy(max_iterations=2),
    )

    report = loop.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "blocked_work_remaining"
    assert report.blocked_item_ids == (item.item_id,)


def test_regression_guard_rolls_back_and_halts():
    item = UpgradeWorkItem("risky update", WorkKind.UPDATE)
    rolled_back = []

    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: {"diff": "changed"},
        validate=lambda work, changed: ValidationResult(
            False,
            summary="new test regression",
            regressions=("tests/test_api.py::test_contract",),
        ),
        rollback=lambda work, changed: rolled_back.append(work.item_id),
    )

    report = loop.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "regression_guard"
    assert report.blocked_item_ids == (item.item_id,)
    assert rolled_back == [item.item_id]


def test_regressions_halt_even_when_validator_marks_passed():
    item = UpgradeWorkItem("inconsistent validator", WorkKind.REPAIR)
    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: None,
        validate=lambda work, changed: ValidationResult(
            True,
            summary="validator passed but delta found a regression",
            regressions=("test_new_regression",),
        ),
    )

    report = loop.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "regression_guard"


def test_no_progress_budget_halts_repeated_executor_failures():
    item = UpgradeWorkItem("broken implementation", WorkKind.REPAIR, max_attempts=10)

    def explode(work):
        raise RuntimeError("executor unavailable")

    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=explode,
        validate=lambda work, changed: ValidationResult(True),
        policy=LoopPolicy(max_iterations=10, max_no_progress_iterations=2),
    )

    report = loop.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "no_progress_budget_exhausted"
    assert item.attempts == 2


def test_discovery_failure_halts_without_executing_work():
    item = UpgradeWorkItem("queued feature", WorkKind.IMPLEMENT_FEATURE)

    def fail_discovery():
        raise ConnectionError("source unavailable")

    loop = ContinuousUpgradeLoop(
        discover=fail_discovery,
        implement=lambda work: None,
        validate=lambda work, changed: ValidationResult(True),
    )

    report = loop.run([item])

    assert report.state == LoopState.HALTED
    assert report.halt_reason == "discovery_error:ConnectionError"
    assert report.pending_item_ids == (item.item_id,)


def test_checkpoints_capture_final_state_and_pending_work():
    checkpoints = []
    item = feature_work("feature", "description")

    loop = ContinuousUpgradeLoop(
        discover=lambda: (),
        implement=lambda work: None,
        validate=lambda work, changed: ValidationResult(True),
        checkpoint=checkpoints.append,
    )

    report = loop.run([item])

    assert report.state == LoopState.COMPLETED
    assert checkpoints[-1].state == LoopState.COMPLETED
    assert checkpoints[-1].pending_item_ids == ()
    assert item.item_id in checkpoints[-1].completed_item_ids


@dataclass
class FakeRecommendation:
    id: str = "rec-1"
    repository: str = "cvsz/zcoder"
    type: str = "PATCH_DEPENDENCY"
    priority: int = 7
    risk: str = "low"
    reason: str = "Dependency outdated: demo"


def test_upgrade23_maintenance_recommendation_adapts_to_update_work():
    item = work_from_maintenance_recommendation(FakeRecommendation())

    assert item.kind == WorkKind.UPDATE
    assert item.priority == 7
    assert item.payload["repository"] == "cvsz/zcoder"
    assert item.payload["recommendation_id"] == "rec-1"


def test_feature_work_rejects_empty_title():
    try:
        feature_work("   ", "description")
    except ValueError as exc:
        assert "title" in str(exc)
    else:
        raise AssertionError("feature_work must reject an empty title")

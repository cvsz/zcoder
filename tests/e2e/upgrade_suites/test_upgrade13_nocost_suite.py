"""tests/test_upgrade13_nocost_suite.py — Comprehensive Test Suite for Upgrade-13 No-Cost Core.

Verifies:
  1. Cost Classification & Zero-Cost Routing (--max-cost 0 / zero-spend policy)
  2. Model Recommender without external LLM (deterministic rule engine)
  3. LocalObjectStorage (filesystem storage with path traversal protection)
  4. In-App Notification Center (in-app notifications, read state, deduplication)
  5. Privacy-First Local Analytics Engine (in-memory offline stats)
  6. Workflow Builder & Versioned Templates (step planning & validation)
"""

import pytest

from zcoder.enterprise.no_cost_platform import (
    CostClass,
    CostOptimizer,
    CostPolicy,
    LocalAnalyticsEngine,
    LocalObjectStorage,
    NotificationCenter,
    NotificationSeverity,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowStep,
)


def test_cost_optimizer_zero_cost_policy():
    optimizer = CostOptimizer()

    # 1. Zero cost only policy -> selects local model
    model_id, reason, cost_class = optimizer.recommend(
        task_description="Fix syntax error",
        policy=CostPolicy.ZERO_COST_ONLY,
        max_cost_usd=0.0,
    )
    assert cost_class == CostClass.FREE_LOCAL
    assert model_id.startswith("local:")
    assert "zero-cost" in reason.lower()

    # 2. Paid model requested with zero budget -> must reject and fallback safely to zero cost
    model_id2, reason2, cost_class2 = optimizer.recommend(
        task_description="Heavy refactor",
        policy=CostPolicy.PREFER_ZERO_COST,
        max_cost_usd=0.0,
        requires_thinking=True,
    )
    assert cost_class2 == CostClass.FREE_LOCAL


def test_local_object_storage_and_path_traversal_defense(tmp_path):
    storage = LocalObjectStorage(base_dir=str(tmp_path))

    # 1. Put and Get
    data = b"Hello, local artifact world!"
    sha = storage.put_object("org_test", "artifacts/build.log", data)
    assert len(sha) == 64

    retrieved = storage.get_object("org_test", "artifacts/build.log")
    assert retrieved == data

    # 2. Path traversal attack attempt -> must raise ValueError
    with pytest.raises(ValueError, match="Path traversal blocked"):
        storage.put_object("org_test", "../../etc/passwd", b"evil")

    # 3. Delete
    deleted = storage.delete_object("org_test", "artifacts/build.log")
    assert deleted is True
    with pytest.raises(FileNotFoundError):
        storage.get_object("org_test", "artifacts/build.log")


def test_in_app_notification_center_and_deduplication():
    center = NotificationCenter()

    # 1. Dispatch notification
    n1 = center.notify(
        organization_id="org_dev",
        principal_id="user_alice",
        title="Job Complete",
        message="Build job succeeded in 12s",
        severity=NotificationSeverity.INFO,
        dedup_key="job_success_1001",
    )
    assert n1 is not None

    # 2. Duplicate dispatch with same dedup_key -> ignored
    n2 = center.notify(
        organization_id="org_dev",
        principal_id="user_alice",
        title="Job Complete",
        message="Build job succeeded in 12s",
        severity=NotificationSeverity.INFO,
        dedup_key="job_success_1001",
    )
    assert n2 is None

    # 3. Read status
    unread = center.get_unread("org_dev", "user_alice")
    assert len(unread) == 1
    assert unread[0].title == "Job Complete"

    ok = center.mark_read(unread[0].id)
    assert ok is True
    assert len(center.get_unread("org_dev", "user_alice")) == 0


def test_local_analytics_engine():
    analytics = LocalAnalyticsEngine()
    analytics.track("job.completed", "org_acme", {"duration": 5.2})
    analytics.track("job.completed", "org_acme", {"duration": 3.1})
    analytics.track("job.failed", "org_acme", {"error": "syntax"})

    stats = analytics.get_aggregate_stats("org_acme")
    assert stats["jobs_completed"] == 2
    assert stats["jobs_failed"] == 1
    assert stats["total_events"] == 3
    assert stats["success_rate"] == pytest.approx(66.66, 0.1)


def test_workflow_builder_and_templates():
    engine = WorkflowEngine()

    # 1. Built-in template dry-run
    plan = engine.execute_workflow_dry_run("tmpl_fix_failing_tests")
    assert len(plan) == 3
    assert "Run Pytest" in plan[0]

    # 2. Register custom workflow
    custom_wf = WorkflowDefinition(
        id="wf_custom_lint",
        name="Custom Linter",
        organization_id="org_dev",
        steps=[
            WorkflowStep(
                id="st_1", name="Ruff Lint", action_type="command", parameters={"command": "ruff check ."}
            ),
            WorkflowStep(
                id="st_2", name="Notify Slack", action_type="notification", parameters={"channel": "#dev"}
            ),
        ],
    )
    engine.register_workflow(custom_wf)
    plan_custom = engine.execute_workflow_dry_run("wf_custom_lint")
    assert len(plan_custom) == 2

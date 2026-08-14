"""Integration coverage for the Upgrade-28 EngineeringStore ledger adapter."""

import pytest

from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from zcoder.services.upgrade_loop import LoopCheckpoint, LoopState, UpgradeWorkItem, WorkKind, feature_work
from zcoder.services.upgrade_state import UpgradeLedgerError
from zcoder.services.upgrade_store_ledger import EngineeringStoreUpgradeLedger


def _checkpoint(item, *, state, completed=(), blocked=(), pending=()):
    return LoopCheckpoint(
        iteration=1,
        state=state,
        active_item_id=None,
        completed_item_ids=completed,
        blocked_item_ids=blocked,
        pending_item_ids=pending,
    )


def test_store_ledger_survives_sqlite_restart_and_deduplicates(tmp_path):
    db_path = tmp_path / "engineering.db"
    store = SQLiteEngineeringStore(db_path=db_path)
    ledger = EngineeringStoreUpgradeLedger(store, namespace="restart-test")
    item = feature_work("Persist feature", "Survive process restart")

    assert ledger.restore_or_register(item) is item
    assert ledger.state_for(item.fingerprint) == "PENDING"
    assert store.list_tasks(status="CREATED") == []

    ledger.record_checkpoint(
        _checkpoint(item, state=LoopState.COMPLETED, completed=(item.item_id,)),
        {item.item_id: item},
    )
    assert ledger.state_for(item.fingerprint) == "SUCCEEDED"

    restarted_store = SQLiteEngineeringStore(db_path=db_path)
    restarted = EngineeringStoreUpgradeLedger(restarted_store, namespace="restart-test")

    assert restarted.load_resumable() == []
    assert restarted.restore_or_register(feature_work("Persist feature", "Survive process restart")) is None
    assert restarted.terminal_counts() == {"SUCCEEDED": 1, "BLOCKED": 0}


def test_store_ledger_blocked_work_requires_explicit_retry(tmp_path):
    store = SQLiteEngineeringStore(db_path=tmp_path / "engineering.db")
    ledger = EngineeringStoreUpgradeLedger(store, namespace="blocked-test")
    item = UpgradeWorkItem("Blocked update", WorkKind.UPDATE, max_attempts=1)
    ledger.restore_or_register(item)

    ledger.record_checkpoint(
        _checkpoint(item, state=LoopState.HALTED, blocked=(item.item_id,)),
        {item.item_id: item},
    )

    restarted = EngineeringStoreUpgradeLedger(
        SQLiteEngineeringStore(db_path=tmp_path / "engineering.db"),
        namespace="blocked-test",
    )
    assert restarted.load_resumable() == []
    assert restarted.blocked_item_ids() == (item.item_id,)

    retried = restarted.load_resumable(retry_blocked=True)
    assert len(retried) == 1
    assert retried[0].attempts == 0
    assert restarted.state_for(item.fingerprint) == "PENDING"


def test_store_ledger_namespaces_share_store_without_collision(tmp_path):
    store = SQLiteEngineeringStore(db_path=tmp_path / "engineering.db")
    first = EngineeringStoreUpgradeLedger(store, namespace="fleet-a")
    second = EngineeringStoreUpgradeLedger(store, namespace="fleet-b")
    item_a = feature_work("Same feature", "Same content")
    item_b = feature_work("Same feature", "Same content")

    first.restore_or_register(item_a)
    second.restore_or_register(item_b)

    assert len(first.load_resumable()) == 1
    assert len(second.load_resumable()) == 1
    assert store.list_tasks(status="CREATED") == []
    assert len(store.list_tasks(status="PAUSED")) == 2


def test_store_ledger_checkpoint_history_is_bounded(tmp_path):
    store = SQLiteEngineeringStore(db_path=tmp_path / "engineering.db")
    ledger = EngineeringStoreUpgradeLedger(store, namespace="checkpoint-test", max_checkpoints=2)
    item = feature_work("Checkpoint feature", "Bound history")
    ledger.restore_or_register(item)

    for iteration in range(1, 4):
        checkpoint = LoopCheckpoint(
            iteration=iteration,
            state=LoopState.RUNNING,
            active_item_id=item.item_id,
            completed_item_ids=(),
            blocked_item_ids=(),
            pending_item_ids=(item.item_id,),
        )
        ledger.record_checkpoint(checkpoint, {item.item_id: item})

    control = store.get_task(ledger.control_task_id)
    assert control is not None
    marker = control.metadata["zcoder_upgrade_ledger"]
    assert [entry["iteration"] for entry in marker["checkpoints"]] == [2, 3]
    assert control.status == TaskStatus.PAUSED


def test_store_ledger_corrupt_namespaced_metadata_fails_closed(tmp_path):
    store = SQLiteEngineeringStore(db_path=tmp_path / "engineering.db")
    ledger = EngineeringStoreUpgradeLedger(store, namespace="corrupt-test")
    item = feature_work("Corrupt feature", "Detect metadata corruption")
    ledger.restore_or_register(item)

    task = next(task for task in store.list_tasks() if task.id != ledger.control_task_id)
    store.save_task(
        EngineeringTask(
            id=task.id,
            task_description=task.task_description,
            status=TaskStatus.PAUSED,
            created_at=task.created_at,
            metadata={},
        )
    )

    with pytest.raises(UpgradeLedgerError, match="invalid EngineeringStore upgrade metadata"):
        ledger.load_resumable()

"""Live PostgreSQL integration coverage for Upgrade-32 fenced runtime composition."""

from __future__ import annotations

import os
import uuid

import psycopg2
import pytest

from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore
from zcoder.services.upgrade_loop import LoopCheckpoint, LoopState, feature_work
from zcoder.services.upgrade_postgres_fence import PostgresUpgradeFence, StalePostgresUpgradeFenceError
from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease
from zcoder.services.upgrade_postgres_runtime import (
    FencedUpgradeEngineeringStore,
    PostgresFencedRunLease,
    PostgresFencedRunLeaseError,
)
from zcoder.services.upgrade_store_ledger import EngineeringStoreUpgradeLedger

PG_URL = os.environ.get("DATABASE_URL", "")


def pg_is_available() -> bool:
    if not PG_URL:
        return False
    try:
        connection = psycopg2.connect(PG_URL, connect_timeout=2)
        connection.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not pg_is_available(), reason="DATABASE_URL PostgreSQL instance not reachable"
)


def _runtime(store, namespace):
    probe = EngineeringStoreUpgradeLedger(store, namespace=namespace)
    fence = PostgresUpgradeFence(
        store.connection_scope,
        namespace=namespace,
        control_task_id=probe.control_task_id,
    )
    lease = PostgresFencedRunLease(
        PostgresAdvisoryRunLease(store.connection_scope, f"{namespace}:continuous-run"),
        fence,
    )
    fenced_store = FencedUpgradeEngineeringStore(store, fence, lease.require_token)
    ledger = EngineeringStoreUpgradeLedger(fenced_store, namespace=namespace)
    return fence, lease, ledger


def test_live_fenced_ledger_rejects_stale_runner_after_generation_advances():
    namespace = f"upgrade32-live-{uuid.uuid4().hex}"
    store = PostgresEngineeringStore(dsn=PG_URL, min_conn=1, max_conn=8, connect_timeout=2)
    try:
        store.init_schema()
        fence, first_lease, first_ledger = _runtime(store, namespace)
        first_item = feature_work("First fenced feature", "Persist under generation one")

        with first_lease:
            first_token = first_lease.require_token()
            assert first_token.generation == 1
            assert first_ledger.restore_or_register(first_item) is first_item
            first_ledger.record_checkpoint(
                LoopCheckpoint(
                    iteration=1,
                    state=LoopState.COMPLETED,
                    active_item_id=None,
                    completed_item_ids=(first_item.item_id,),
                    blocked_item_ids=(),
                    pending_item_ids=(),
                ),
                {first_item.item_id: first_item},
            )
            assert first_ledger.state_for(first_item.fingerprint) == "SUCCEEDED"

        second_lease = PostgresFencedRunLease(
            PostgresAdvisoryRunLease(store.connection_scope, f"{namespace}:continuous-run"),
            fence,
        )
        second_store = FencedUpgradeEngineeringStore(store, fence, second_lease.require_token)
        second_ledger = EngineeringStoreUpgradeLedger(second_store, namespace=namespace)

        with second_lease:
            second_token = second_lease.require_token()
            assert second_token.generation == first_token.generation + 1

            stale_store = FencedUpgradeEngineeringStore(store, fence, lambda: first_token)
            stale_ledger = EngineeringStoreUpgradeLedger(stale_store, namespace=namespace)
            stale_item = feature_work("Stale fenced feature", "This row must never persist")
            with pytest.raises(StalePostgresUpgradeFenceError, match="stale PostgreSQL upgrade fence"):
                stale_ledger.restore_or_register(stale_item)
            assert stale_ledger.state_for(stale_item.fingerprint) is None

            current_item = feature_work("Current fenced feature", "Persist under generation two")
            assert second_ledger.restore_or_register(current_item) is current_item
            assert second_ledger.state_for(current_item.fingerprint) == "PENDING"

        with pytest.raises(PostgresFencedRunLeaseError, match="not acquired"):
            second_ledger.restore_or_register(feature_work("Outside lease", "Must fail closed"))
    finally:
        store.close()

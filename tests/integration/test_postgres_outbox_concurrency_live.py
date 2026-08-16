"""Upgrade-43 live PostgreSQL outbox concurrency regression.

This test is intentionally integration-only and skips when the repository's
real PostgreSQL test service is unavailable. It verifies the production store
boundary partitions one finite outbox backlog across concurrent workers without
duplicate delivery.
"""

import multiprocessing
import os
import time

import psycopg2
import pytest

from postgres_store import PostgresControlPlaneStore

PG_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@172.17.0.2:5432/zcoder")


def pg_is_available():
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not pg_is_available(), reason="PostgreSQL test container not reachable")


def _process_outbox_once(delivered, errors):
    store = None
    try:
        store = PostgresControlPlaneStore(dsn=PG_URL)

        def handler(action, payload):
            if action == "upgrade43.concurrent":
                delivered.append(payload["sequence"])
                time.sleep(0.02)

        store.process_outbox(handler, max_attempts=2)
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if store is not None:
            store.close()


def test_concurrent_outbox_workers_do_not_duplicate_delivery():
    store = PostgresControlPlaneStore(dsn=PG_URL)
    store.init_schema()
    try:
        with store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM outbox WHERE action = %s", ("upgrade43.concurrent",))

        message_count = 12
        for sequence in range(message_count):
            store.enqueue_outbox("upgrade43.concurrent", {"sequence": sequence})

        manager = multiprocessing.Manager()
        delivered = manager.list()
        errors = manager.list()
        workers = [
            multiprocessing.Process(target=_process_outbox_once, args=(delivered, errors)) for _ in range(3)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10.0)
            assert not worker.is_alive(), "outbox worker exceeded the bounded test timeout"

        assert list(errors) == []
        assert sorted(delivered) == list(range(message_count))
        assert len(set(delivered)) == message_count

        with store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, COUNT(*) FROM outbox WHERE action = %s GROUP BY status",
                    ("upgrade43.concurrent",),
                )
                status_counts = dict(cur.fetchall())
        assert status_counts == {"DELIVERED": message_count}
    finally:
        with store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM outbox WHERE action = %s", ("upgrade43.concurrent",))
        store.close()

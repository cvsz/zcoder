from contextlib import contextmanager

import pytest

from zcoder.infrastructure.stores.postgres_outbox import process_postgres_outbox_once


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.conn.executed.append((normalized, params))
        if normalized.startswith("SELECT id, action, payload, attempts FROM outbox"):
            max_attempts, max_messages = params
            self._rows = [row for row in self.conn.rows if row[4] == "PENDING" and row[3] < max_attempts][
                :max_messages
            ]
        elif normalized.startswith("UPDATE outbox SET attempts"):
            attempts, status, error, message_id = params
            self.conn.failure_updates.append((message_id, attempts, status, error))
        elif normalized.startswith("UPDATE outbox SET status = 'DELIVERED'"):
            _delivered_at, message_id = params
            self.conn.delivered.append(message_id)

    def fetchall(self):
        return [(row[0], row[1], row[2], row[3]) for row in self._rows]


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.delivered = []
        self.failure_updates = []

    def cursor(self):
        return FakeCursor(self)


class FakeStore:
    def __init__(self, rows):
        self.conn = FakeConnection(rows)

    @contextmanager
    def _get_conn(self):
        yield self.conn


def test_process_postgres_outbox_once_honors_batch_budget_and_order():
    store = FakeStore(
        [
            ("out_1", "a", {"n": 1}, 0, "PENDING"),
            ("out_2", "a", {"n": 2}, 0, "PENDING"),
            ("out_3", "a", {"n": 3}, 0, "PENDING"),
        ]
    )
    seen = []

    delivered = process_postgres_outbox_once(
        store,
        lambda action, payload: seen.append((action, payload["n"])),
        max_messages=2,
        max_attempts=3,
    )

    assert delivered == 2
    assert seen == [("a", 1), ("a", 2)]
    assert store.conn.delivered == ["out_1", "out_2"]
    select_sql, select_params = store.conn.executed[0]
    assert "ORDER BY created_at ASC" in select_sql
    assert "FOR UPDATE SKIP LOCKED" in select_sql
    assert select_params == (3, 2)


def test_process_postgres_outbox_once_persists_bounded_failure_transition():
    store = FakeStore([("out_1", "a", "{\"n\": 1}", 1, "PENDING")])
    calls = 0

    def fail_once(_action, _payload):
        nonlocal calls
        calls += 1
        raise RuntimeError("downstream unavailable")

    delivered = process_postgres_outbox_once(
        store,
        fail_once,
        max_messages=1,
        max_attempts=2,
    )

    assert delivered == 0
    assert calls == 1
    assert store.conn.failure_updates == [("out_1", 2, "DEAD", "downstream unavailable")]


@pytest.mark.parametrize(
    "kwargs",
    [{"max_messages": 0, "max_attempts": 1}, {"max_messages": 1, "max_attempts": 0}],
)
def test_process_postgres_outbox_once_rejects_non_positive_budgets_before_io(kwargs):
    store = FakeStore([])

    with pytest.raises(ValueError):
        process_postgres_outbox_once(store, lambda _a, _p: None, **kwargs)

    assert store.conn.executed == []

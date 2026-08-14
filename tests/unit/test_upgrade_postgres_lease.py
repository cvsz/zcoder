"""Unit coverage for the Upgrade-30 PostgreSQL advisory run lease."""

import pytest

from zcoder.services.upgrade_postgres_lease import (
    PostgresAdvisoryRunLease,
    PostgresUpgradeRunLeaseError,
    advisory_lock_key,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql, params):
        self.connection.queries.append((sql, params))
        if self.connection.execute_error is not None:
            raise self.connection.execute_error

    def fetchone(self):
        return (self.connection.results.pop(0),)


class FakeConnection:
    def __init__(self, results, *, execute_error=None):
        self.results = list(results)
        self.execute_error = execute_error
        self.queries = []

    def cursor(self):
        return FakeCursor(self)


class FakeConnectionScope:
    def __init__(self, connection, *, exit_error=None):
        self.connection = connection
        self.exit_error = exit_error
        self.enter_count = 0
        self.exit_count = 0
        self.exit_args = []

    def __enter__(self):
        self.enter_count += 1
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        self.exit_count += 1
        self.exit_args.append((exc_type, exc, tb))
        if self.exit_error is not None:
            raise self.exit_error
        return None


def test_advisory_lock_key_is_stable_signed_bigint():
    key = advisory_lock_key("zcoder-fleet")

    assert key == advisory_lock_key(" zcoder-fleet ")
    assert -(2**63) <= key < 2**63
    assert key != advisory_lock_key("another-fleet")


def test_advisory_lock_key_rejects_empty_namespace():
    with pytest.raises(ValueError, match="namespace must not be empty"):
        advisory_lock_key("   ")


def test_lease_holds_same_session_until_explicit_release():
    connection = FakeConnection([True, True])
    scope = FakeConnectionScope(connection)
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")

    lease.acquire()

    assert scope.enter_count == 1
    assert scope.exit_count == 0
    assert connection.queries == [("SELECT pg_try_advisory_lock(%s)", (lease.lock_key,))]

    lease.release()

    assert scope.exit_count == 1
    assert connection.queries[-1] == ("SELECT pg_advisory_unlock(%s)", (lease.lock_key,))


def test_competing_runner_fails_closed_and_returns_connection():
    connection = FakeConnection([False])
    scope = FakeConnectionScope(connection)
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")

    with pytest.raises(PostgresUpgradeRunLeaseError, match="already held"):
        lease.acquire()

    assert scope.enter_count == 1
    assert scope.exit_count == 1
    assert connection.queries == [("SELECT pg_try_advisory_lock(%s)", (lease.lock_key,))]


def test_acquire_error_returns_connection_and_is_normalized():
    connection = FakeConnection([], execute_error=RuntimeError("database unavailable"))
    scope = FakeConnectionScope(connection)
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")

    with pytest.raises(PostgresUpgradeRunLeaseError, match="unable to acquire"):
        lease.acquire()

    assert scope.exit_count == 1
    assert scope.exit_args[0][0] is RuntimeError


def test_release_detects_lost_advisory_lock_and_still_returns_connection():
    connection = FakeConnection([True, False])
    scope = FakeConnectionScope(connection)
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")
    lease.acquire()

    with pytest.raises(PostgresUpgradeRunLeaseError, match="ownership lost"):
        lease.release()

    assert scope.exit_count == 1
    lease.release()


def test_connection_return_failure_is_fail_closed():
    connection = FakeConnection([True, True])
    scope = FakeConnectionScope(connection, exit_error=RuntimeError("pool rejected connection"))
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")
    lease.acquire()

    with pytest.raises(PostgresUpgradeRunLeaseError, match="unable to return"):
        lease.release()


def test_context_manager_releases_session_lock():
    connection = FakeConnection([True, True])
    scope = FakeConnectionScope(connection)
    lease = PostgresAdvisoryRunLease(lambda: scope, "fleet-a")

    with lease:
        assert scope.exit_count == 0

    assert scope.exit_count == 1

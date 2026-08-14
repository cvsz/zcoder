"""Live PostgreSQL integration coverage for the Upgrade-30 advisory run lease."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import psycopg2
import pytest

from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease, PostgresUpgradeRunLeaseError

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


pytestmark = pytest.mark.skipif(not pg_is_available(), reason="DATABASE_URL PostgreSQL instance not reachable")


@contextmanager
def connection_scope():
    connection = psycopg2.connect(PG_URL, connect_timeout=2)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def test_live_postgres_advisory_lease_excludes_other_sessions_and_releases():
    namespace = f"zcoder-upgrade-live-{uuid.uuid4().hex}"
    first = PostgresAdvisoryRunLease(connection_scope, namespace)
    second = PostgresAdvisoryRunLease(connection_scope, namespace)

    with first:
        with pytest.raises(PostgresUpgradeRunLeaseError, match="already held"):
            second.acquire()

    with second:
        pass

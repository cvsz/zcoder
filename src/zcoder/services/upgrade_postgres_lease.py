"""PostgreSQL session advisory lease for distributed continuous-engineering runners."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any


class PostgresUpgradeRunLeaseError(RuntimeError):
    """Raised when a PostgreSQL-backed continuous run cannot hold its session lease."""


def advisory_lock_key(namespace: str) -> int:
    """Derive a stable signed BIGINT advisory-lock key from a non-empty namespace."""

    normalized = namespace.strip()
    if not normalized:
        raise ValueError("namespace must not be empty")
    unsigned = int.from_bytes(hashlib.sha256(normalized.encode("utf-8")).digest()[:8], "big")
    return unsigned if unsigned < 2**63 else unsigned - 2**64


ConnectionScopeFactory = Callable[[], AbstractContextManager[Any]]


class PostgresAdvisoryRunLease:
    """Hold one PostgreSQL session advisory lock for the full pipeline run.

    The supplied connection scope must keep one database connection checked out
    until its context exits. PostgreSQL automatically releases the advisory lock
    if that session terminates, which provides cross-process/cross-host mutual
    exclusion without a filesystem dependency.

    This is an exclusivity primitive, not a fencing token. Callers must not
    enable the PostgreSQL continuous-fleet backend until stale-writer fencing is
    enforced at the durable ledger mutation boundary.
    """

    def __init__(self, connection_scope: ConnectionScopeFactory, namespace: str) -> None:
        self.connection_scope = connection_scope
        self.namespace = namespace.strip()
        self.lock_key = advisory_lock_key(self.namespace)
        self._scope: AbstractContextManager[Any] | None = None
        self._connection: Any = None
        self._acquired = False

    def acquire(self) -> None:
        if self._acquired:
            raise PostgresUpgradeRunLeaseError("PostgreSQL upgrade run lease is already acquired")

        scope = self.connection_scope()
        entered = False
        try:
            connection = scope.__enter__()
            entered = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (self.lock_key,))
                row = cursor.fetchone()
            if not row or row[0] is not True:
                scope.__exit__(None, None, None)
                entered = False
                raise PostgresUpgradeRunLeaseError(
                    f"PostgreSQL upgrade run lease already held: {self.namespace}"
                )
            self._scope = scope
            self._connection = connection
            self._acquired = True
        except PostgresUpgradeRunLeaseError:
            raise
        except Exception as exc:
            if entered:
                try:
                    scope.__exit__(type(exc), exc, exc.__traceback__)
                except Exception:
                    pass
            raise PostgresUpgradeRunLeaseError(
                f"unable to acquire PostgreSQL upgrade run lease: {exc}"
            ) from exc

    def release(self) -> None:
        if not self._acquired:
            return

        scope = self._scope
        connection = self._connection
        self._scope = None
        self._connection = None
        self._acquired = False
        failure: PostgresUpgradeRunLeaseError | None = None

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (self.lock_key,))
                row = cursor.fetchone()
            if not row or row[0] is not True:
                failure = PostgresUpgradeRunLeaseError(
                    f"PostgreSQL upgrade run lease ownership lost before release: {self.namespace}"
                )
        except Exception as exc:
            failure = PostgresUpgradeRunLeaseError(f"unable to release PostgreSQL upgrade run lease: {exc}")
        finally:
            if scope is not None:
                try:
                    scope.__exit__(None, None, None)
                except Exception as exc:
                    if failure is None:
                        failure = PostgresUpgradeRunLeaseError(
                            f"unable to return PostgreSQL lease connection: {exc}"
                        )

        if failure is not None:
            raise failure

    def __enter__(self) -> PostgresAdvisoryRunLease:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

"""Regression tests for deterministic SQLite connection cleanup.

``sqlite3.Connection`` used as a context manager only commits/rolls back; it
does not close the handle. These tests guard the project helper and every
short-lived store connection against reintroducing ``ResourceWarning:
unclosed database`` leaks.
"""

from __future__ import annotations

import gc
import sqlite3
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import zcoder.core.sqlite as sqlite_helper
from zcoder.domain.models.legacy_job import JobStore
from zcoder.domain.services.control_plane import ControlPlaneStore
from zcoder.infrastructure.stores.portfolio import PortfolioStore
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore


def _unclosed_database_warnings() -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        gc.collect()
    return [str(item.message) for item in caught if "unclosed database" in str(item.message).lower()]


def test_helper_closes_connection(tmp_path: Path) -> None:
    with sqlite_helper.sqlite_connection(tmp_path / "closed.db") as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")


def test_helper_commits_on_success_and_rolls_back_on_error(tmp_path: Path) -> None:
    db = tmp_path / "tx.db"
    with sqlite_helper.sqlite_connection(db) as conn:
        conn.execute("CREATE TABLE t (id INTEGER)")

    with sqlite_helper.sqlite_connection(db) as conn:
        conn.execute("INSERT INTO t (id) VALUES (1)")

    try:
        with sqlite_helper.sqlite_connection(db) as conn:
            conn.execute("INSERT INTO t (id) VALUES (2)")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with sqlite_helper.sqlite_connection(db) as conn:
        rows = conn.execute("SELECT id FROM t ORDER BY id").fetchall()
    assert rows == [(1,)]


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda path: SQLiteEngineeringStore(path / "engineering.db"), id="engineering"),
        pytest.param(lambda path: PortfolioStore(path / "portfolio.db"), id="portfolio"),
        pytest.param(lambda path: JobStore(path / "jobs.db"), id="jobs"),
        pytest.param(lambda path: ControlPlaneStore(path / "control.db"), id="control-plane"),
    ],
)
def test_store_connections_are_closed(
    tmp_path: Path,
    factory: Callable[[Path], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every short-lived store connection is closed, even before garbage collection."""
    connections: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def recording_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite_helper.sqlite3, "connect", recording_connect)

    store = factory(tmp_path)
    del store
    assert connections, "store did not open any SQLite connection"

    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")
    assert _unclosed_database_warnings() == []

"""sqlite.py — deterministic SQLite connection lifecycle helpers.

A ``sqlite3.Connection`` used as a context manager only commits or rolls back
the active transaction; it does **not** close the underlying database handle.
Leaving connections to garbage collection leaks file descriptors and emits
``ResourceWarning: unclosed database`` under CPython. These helpers own the
handle for the duration of the block and always close it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def sqlite_connection(
    db_path: str | Path,
    *,
    timeout: float = 5.0,
    pragmas: tuple[str, ...] = (),
) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection, commit on success, roll back on error, close.

    ``pragmas`` are applied once per fresh connection before the transaction
    block begins (for example ``("PRAGMA journal_mode=WAL",)``).
    """

    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        for pragma in pragmas:
            conn.execute(pragma)
        with conn:
            yield conn
    finally:
        conn.close()

"""Compatibility boundary for bounded PostgreSQL outbox processing.

This module preserves the existing ``PostgresControlPlaneStore.process_outbox``
call defaults while delegating execution to the Upgrade-41 one-shot processor.
It deliberately contains no polling, retry loop, sleep, scheduling, or backoff.
"""

from __future__ import annotations

from typing import Any

from zcoder.infrastructure.stores.postgres_outbox import process_postgres_outbox_once


def process_postgres_store_outbox(
    store: Any,
    handler: Any,
    max_attempts: int = 5,
    backoff_base: float = 2.0,
    max_messages: int = 50,
) -> int:
    """Run one bounded batch using the legacy PostgreSQL store defaults.

    ``backoff_base`` is retained only for call compatibility. Retry cadence and
    backoff remain external under the Upgrade-20/24 bounded execution model.
    """
    del backoff_base
    return process_postgres_outbox_once(
        store,
        handler,
        max_messages=max_messages,
        max_attempts=max_attempts,
    )

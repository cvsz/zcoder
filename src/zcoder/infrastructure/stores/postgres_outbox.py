"""Bounded PostgreSQL outbox processing for multi-worker delivery.

This adapter is intentionally one-shot: one call claims at most ``max_messages``
rows with ``FOR UPDATE SKIP LOCKED`` and invokes the handler at most once per
claimed row. Scheduling, cadence, retry timing, and backoff remain external.
"""

from __future__ import annotations

import json
import time
from typing import Any

from zcoder.domain.services.outbox_policy import transition_after_failure


def process_postgres_outbox_once(
    store: Any,
    handler: Any,
    *,
    max_messages: int,
    max_attempts: int,
) -> int:
    """Process one finite PostgreSQL outbox batch.

    ``store`` must expose the existing ``_get_conn()`` transaction context used
    by ``PostgresControlPlaneStore``. Both budgets are explicit and positive so
    a worker invocation cannot expand with backlog size or retry indefinitely.
    """
    if max_messages < 1:
        raise ValueError("max_messages must be >= 1")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    delivered = 0
    with store._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, action, payload, attempts
                FROM outbox
                WHERE status = 'PENDING' AND attempts < %s
                ORDER BY created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (max_attempts, max_messages),
            )
            rows = cur.fetchall()

        for message_id, action, payload_raw, attempts in rows:
            payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw)
            try:
                handler(action, payload)
            except Exception as exc:
                transition = transition_after_failure(attempts, max_attempts)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE outbox SET attempts = %s, status = %s, error = %s WHERE id = %s",
                        (transition.attempts, transition.status, str(exc), message_id),
                    )
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE outbox SET status = 'DELIVERED', delivered_at = %s, error = NULL WHERE id = %s",
                        (time.time(), message_id),
                    )
                delivered += 1

    return delivered

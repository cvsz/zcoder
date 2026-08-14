"""Monotonic PostgreSQL fencing for continuous-engineering ledger mutations."""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from zcoder.domain.models.engineering import EngineeringTask

_METADATA_KEY = "zcoder_upgrade_ledger"
_SCHEMA_VERSION = 1


class PostgresUpgradeFenceError(RuntimeError):
    """Raised when an upgrade fence cannot be acquired or validated safely."""


class StalePostgresUpgradeFenceError(PostgresUpgradeFenceError):
    """Raised when a stale runner attempts a durable mutation."""


@dataclass(frozen=True)
class UpgradeFenceToken:
    """Monotonic ownership generation for one upgrade-ledger namespace."""

    namespace: str
    control_task_id: str
    generation: int


ConnectionScopeFactory = Callable[[], AbstractContextManager[Any]]


class PostgresUpgradeFence:
    """Issue and validate monotonic fence generations on an engineering control row.

    Each token acquisition locks the namespace control row with ``FOR UPDATE`` and
    increments ``fence_generation``. Every fenced task write locks and validates
    the same row in the *same transaction* as the task upsert. Once a newer token
    exists, a stale token can no longer persist work or checkpoint state.
    """

    def __init__(
        self, connection_scope: ConnectionScopeFactory, *, namespace: str, control_task_id: str
    ) -> None:
        normalized_namespace = namespace.strip()
        normalized_control_id = control_task_id.strip()
        if not normalized_namespace:
            raise ValueError("namespace must not be empty")
        if not normalized_control_id:
            raise ValueError("control_task_id must not be empty")
        self.connection_scope = connection_scope
        self.namespace = normalized_namespace
        self.control_task_id = normalized_control_id

    def acquire_token(self) -> UpgradeFenceToken:
        now = time.time()
        try:
            with self.connection_scope() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT created_at, metadata FROM engineering_tasks WHERE id = %s FOR UPDATE",
                        (self.control_task_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        generation = 1
                        metadata = self._new_control_metadata(generation)
                        cursor.execute(
                            """
                            INSERT INTO engineering_tasks
                                (id, task_description, status, created_at, updated_at, metadata)
                            VALUES (%s, %s, 'PAUSED', %s, %s, %s)
                            """,
                            (
                                self.control_task_id,
                                f"Continuous upgrade ledger control: {self.namespace}",
                                now,
                                now,
                                json.dumps(metadata),
                            ),
                        )
                    else:
                        metadata = self._decode_metadata(row[1])
                        marker = self._validated_marker(metadata)
                        generation = self._generation(marker) + 1
                        marker["fence_generation"] = generation
                        cursor.execute(
                            """
                            UPDATE engineering_tasks
                            SET status = 'PAUSED', updated_at = %s, metadata = %s
                            WHERE id = %s
                            """,
                            (now, json.dumps(metadata), self.control_task_id),
                        )
        except PostgresUpgradeFenceError:
            raise
        except Exception as exc:
            raise PostgresUpgradeFenceError(f"unable to acquire PostgreSQL upgrade fence: {exc}") from exc
        return UpgradeFenceToken(self.namespace, self.control_task_id, generation)

    def assert_current(self, token: UpgradeFenceToken) -> None:
        """Validate a token against the durable control row without mutating work."""

        self._validate_token_identity(token)
        try:
            with self.connection_scope() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT metadata FROM engineering_tasks WHERE id = %s FOR UPDATE",
                        (self.control_task_id,),
                    )
                    row = cursor.fetchone()
                    self._assert_generation(row, token)
        except PostgresUpgradeFenceError:
            raise
        except Exception as exc:
            raise PostgresUpgradeFenceError(f"unable to validate PostgreSQL upgrade fence: {exc}") from exc

    def save_task(self, task: EngineeringTask, token: UpgradeFenceToken) -> None:
        """Upsert an EngineeringTask only while ``token`` is the current generation."""

        self._validate_token_identity(token)
        now = time.time()
        try:
            with self.connection_scope() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT metadata FROM engineering_tasks WHERE id = %s FOR UPDATE",
                        (self.control_task_id,),
                    )
                    row = cursor.fetchone()
                    self._assert_generation(row, token)
                    metadata = copy.deepcopy(task.metadata)
                    if task.id == self.control_task_id:
                        marker = self._validated_marker(metadata)
                        marker["fence_generation"] = token.generation
                    cursor.execute(
                        """
                        INSERT INTO engineering_tasks
                            (id, task_description, status, created_at, updated_at, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET task_description = EXCLUDED.task_description,
                            status = EXCLUDED.status,
                            updated_at = EXCLUDED.updated_at,
                            metadata = EXCLUDED.metadata
                        """,
                        (
                            task.id,
                            task.task_description,
                            task.status.value,
                            task.created_at,
                            now,
                            json.dumps(metadata),
                        ),
                    )
                    task.updated_at = now
        except PostgresUpgradeFenceError:
            raise
        except Exception as exc:
            raise PostgresUpgradeFenceError(f"unable to save fenced PostgreSQL upgrade task: {exc}") from exc

    def _assert_generation(self, row: Any, token: UpgradeFenceToken) -> None:
        if row is None:
            raise StalePostgresUpgradeFenceError("PostgreSQL upgrade fence control row is missing")
        metadata = self._decode_metadata(row[0])
        marker = self._validated_marker(metadata)
        current = self._generation(marker)
        if current != token.generation:
            raise StalePostgresUpgradeFenceError(
                f"stale PostgreSQL upgrade fence: expected generation {token.generation}, current {current}"
            )

    def _validate_token_identity(self, token: UpgradeFenceToken) -> None:
        if token.namespace != self.namespace or token.control_task_id != self.control_task_id:
            raise StalePostgresUpgradeFenceError("PostgreSQL upgrade fence token identity mismatch")
        if token.generation < 1:
            raise StalePostgresUpgradeFenceError("PostgreSQL upgrade fence generation must be >= 1")

    def _validated_marker(self, metadata: dict[str, Any]) -> dict[str, Any]:
        marker = metadata.get(_METADATA_KEY)
        if not isinstance(marker, dict):
            raise PostgresUpgradeFenceError("invalid PostgreSQL upgrade fence metadata")
        if marker.get("schema_version") != _SCHEMA_VERSION:
            raise PostgresUpgradeFenceError("unsupported PostgreSQL upgrade fence schema")
        if marker.get("record_type") != "control":
            raise PostgresUpgradeFenceError("PostgreSQL upgrade fence requires a control record")
        if marker.get("namespace") != self.namespace:
            raise PostgresUpgradeFenceError("PostgreSQL upgrade fence namespace mismatch")
        return marker

    @staticmethod
    def _decode_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise PostgresUpgradeFenceError("invalid PostgreSQL upgrade fence metadata")
        return value

    @staticmethod
    def _generation(marker: dict[str, Any]) -> int:
        value = marker.get("fence_generation", 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PostgresUpgradeFenceError("invalid PostgreSQL upgrade fence generation")
        return value

    def _new_control_metadata(self, generation: int) -> dict[str, Any]:
        return {
            _METADATA_KEY: {
                "schema_version": _SCHEMA_VERSION,
                "record_type": "control",
                "namespace": self.namespace,
                "checkpoints": [],
                "fence_generation": generation,
            }
        }

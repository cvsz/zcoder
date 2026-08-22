"""Cross-process contention tests for PostgreSQL upgrade lease and stale-writer fence.

Two OS processes contend for (a) one advisory run-lease namespace and (b) one
monotonic fence generation namespace. The loser must observe
``PostgresUpgradeRunLeaseError`` / ``StalePostgresUpgradeFenceError``.

Skips cleanly when no PostgreSQL instance is reachable so CI passes without PG.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

try:
    import psycopg2
except ImportError:  # pragma: no cover - psycopg2 optional in minimal envs
    psycopg2 = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
PG_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
WAIT_TIMEOUT = 60.0


def _pg_available() -> bool:
    if psycopg2 is None:
        return False
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL instance not reachable")


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


# ─── Subprocess runner sources ────────────────────────────────────────────────
#
# Each runner receives its arguments positionally via argv:
#   argv[1] = repo src path, argv[2] = PostgreSQL DSN, remaining args per runner.
# Coordination happens through small JSON/text marker files in tmp_path.

_RUNNER_PREAMBLE = """
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

SRC_PATH, DSN = sys.argv[1], sys.argv[2]
sys.path.insert(0, SRC_PATH)

import psycopg2


@contextmanager
def connection_scope():
    connection = psycopg2.connect(DSN, connect_timeout=5)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def wait_for_file(path, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if Path(path).exists():
            return
        time.sleep(0.1)
    raise AssertionError(f"runner timed out waiting for {path}")
"""

_HOLDER_SOURCE = (
    _RUNNER_PREAMBLE
    + """
from zcoder.services.upgrade_postgres_lease import PostgresAdvisoryRunLease

_, _, _, NAMESPACE, HELD_MARKER, STOP_MARKER, RELEASED_MARKER = sys.argv

lease = PostgresAdvisoryRunLease(connection_scope, namespace=NAMESPACE)
lease.acquire()
Path(HELD_MARKER).write_text("HELD")
deadline = time.monotonic() + 90
while not Path(STOP_MARKER).exists() and time.monotonic() < deadline:
    time.sleep(0.1)
lease.release()
Path(RELEASED_MARKER).write_text("RELEASED")
"""
)

_CONTENDER_SOURCE = (
    _RUNNER_PREAMBLE
    + """
from zcoder.services.upgrade_postgres_lease import (
    PostgresAdvisoryRunLease,
    PostgresUpgradeRunLeaseError,
)

_, _, _, NAMESPACE, HELD_MARKER, LOST_MARKER, RELEASED_MARKER, REACQUIRED_MARKER = sys.argv

wait_for_file(HELD_MARKER, 90)
outcome = {"result": "LOST", "error": ""}
try:
    lease = PostgresAdvisoryRunLease(connection_scope, namespace=NAMESPACE)
    lease.acquire()
except PostgresUpgradeRunLeaseError as exc:
    outcome["error"] = str(exc)
else:
    lease.release()
    outcome["result"] = "BUG_ACQUIRED_WHILE_HELD"

Path(LOST_MARKER).write_text(json.dumps(outcome))
if outcome["result"] != "LOST":
    sys.exit(0)

wait_for_file(RELEASED_MARKER, 90)
retry = PostgresAdvisoryRunLease(connection_scope, namespace=NAMESPACE)
retry.acquire()
retry.release()
Path(REACQUIRED_MARKER).write_text(json.dumps({"result": "REACQUIRED"}))
"""
)

_FIRST_RUNNER_SOURCE = (
    _RUNNER_PREAMBLE
    + """
from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.upgrade_postgres_fence import (
    PostgresUpgradeFence,
    StalePostgresUpgradeFenceError,
)

_, _, _, NAMESPACE, CONTROL_ID, TOKEN_FILE, GO_MARKER, OUTCOME_FILE = sys.argv

fence = PostgresUpgradeFence(connection_scope, namespace=NAMESPACE, control_task_id=CONTROL_ID)
token = fence.acquire_token()
assert token.generation == 1, f"expected first generation 1, got {token.generation}"
Path(TOKEN_FILE).write_text(json.dumps({"generation": token.generation}))

wait_for_file(GO_MARKER, 90)
stale_task = EngineeringTask(
    id=f"{CONTROL_ID}-work-stale",
    task_description="stale generation write must never persist",
    status=TaskStatus.PAUSED,
    created_at=time.time(),
    metadata={"generation": token.generation},
)
outcome = {"result": "STALE_REJECTED", "error": ""}
try:
    fence.save_task(stale_task, token)
except StalePostgresUpgradeFenceError as exc:
    outcome["error"] = str(exc)
else:
    outcome["result"] = "BUG_STALE_WRITE_ACCEPTED"
Path(OUTCOME_FILE).write_text(json.dumps(outcome))
if outcome["result"] != "STALE_REJECTED":
    sys.exit(0)
"""
)

_SECOND_RUNNER_SOURCE = (
    _RUNNER_PREAMBLE
    + """
from zcoder.domain.models.engineering import EngineeringTask, TaskStatus
from zcoder.services.upgrade_postgres_fence import PostgresUpgradeFence

_, _, _, NAMESPACE, CONTROL_ID, GEN1_FILE, GEN2_FILE, SAVED_FILE = sys.argv

fence = PostgresUpgradeFence(connection_scope, namespace=NAMESPACE, control_task_id=CONTROL_ID)
newer = fence.acquire_token()
assert newer.generation == 2, f"expected second generation 2, got {newer.generation}"
Path(GEN2_FILE).write_text(json.dumps({"generation": newer.generation}))

current = EngineeringTask(
    id=f"{CONTROL_ID}-work-current",
    task_description="current generation write",
    status=TaskStatus.PAUSED,
    created_at=time.time(),
    metadata={"generation": newer.generation},
)
fence.save_task(current, newer)
Path(SAVED_FILE).write_text("SAVED")
"""
)


def _spawn(script: Path, *args: object) -> subprocess.Popen:
    env = os.environ.copy()
    src_path = REPO_ROOT / "src"
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_path}:{REPO_ROOT}:{existing_pp}" if existing_pp else f"{src_path}:{REPO_ROOT}"
    return subprocess.Popen(
        [sys.executable, str(script), *[str(a) for a in args]],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _wait_for_file(path: Path, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


def _wait_until_json(path: Path, timeout: float, description: str) -> dict:
    _wait_for_file(path, timeout, description)
    return _read_json(path)


def _ensure_schema() -> None:
    with connection_scope() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS engineering_tasks (
                    id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
                """
            )


class TestCrossProcessUpgradeFence:
    def test_advisory_lease_mutual_exclusion_across_processes(self, tmp_path):
        """Winner holds the session advisory lock; loser's pg_try_advisory_lock fails;
        after release the loser can re-acquire."""
        holder_script = tmp_path / "holder.py"
        contender_script = tmp_path / "contender.py"
        holder_script.write_text(_HOLDER_SOURCE)
        contender_script.write_text(_CONTENDER_SOURCE)

        namespace = f"upgrade-f3-lease-{uuid.uuid4().hex}"
        held_marker = tmp_path / "held.marker"
        lost_file = tmp_path / "lost.json"
        stop_marker = tmp_path / "stop.marker"
        released_marker = tmp_path / "released.marker"
        reacquired_file = tmp_path / "reacquired.json"

        holder = _spawn(
            holder_script,
            REPO_ROOT / "src",
            PG_URL,
            namespace,
            held_marker,
            stop_marker,
            released_marker,
        )
        try:
            _wait_for_file(held_marker, WAIT_TIMEOUT, "holder to acquire the lease")

            contender = _spawn(
                contender_script,
                REPO_ROOT / "src",
                PG_URL,
                namespace,
                held_marker,
                lost_file,
                released_marker,
                reacquired_file,
            )
            try:
                outcome = _wait_until_json(lost_file, WAIT_TIMEOUT, "contender attempt result")
                assert outcome["result"] == "LOST", outcome
                assert "already held" in outcome["error"]

                stop_marker.write_text("release")
                _wait_for_file(released_marker, WAIT_TIMEOUT, "holder to release the lease")
                final = _wait_until_json(reacquired_file, WAIT_TIMEOUT, "contender re-acquire after release")
                assert final["result"] == "REACQUIRED", final
            finally:
                contender.wait(timeout=30)
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=10)

    def test_stale_generation_fenced_writer_rejected_across_processes(self, tmp_path):
        """Process A takes gen 1; process B then takes gen 2; A's durable write via
        its now-stale token must raise StalePostgresUpgradeFenceError while B's
        write succeeds."""
        first_script = tmp_path / "first_runner.py"
        second_script = tmp_path / "second_runner.py"
        first_script.write_text(_FIRST_RUNNER_SOURCE)
        second_script.write_text(_SECOND_RUNNER_SOURCE)

        unique = uuid.uuid4().hex
        namespace = f"upgrade-f3-fence-{unique}"
        control_id = f"upgrade-ledger-{unique}-control"
        _ensure_schema()

        gen1_file = tmp_path / "gen1.json"
        gen2_file = tmp_path / "gen2.json"
        saved_marker = tmp_path / "saved.marker"
        go_marker = tmp_path / "go.marker"
        outcome_file = tmp_path / "outcome.json"

        first = _spawn(
            first_script,
            REPO_ROOT / "src",
            PG_URL,
            namespace,
            control_id,
            gen1_file,
            go_marker,
            outcome_file,
        )
        try:
            _wait_for_file(gen1_file, WAIT_TIMEOUT, "first runner gen-1 token")
            assert _read_json(gen1_file)["generation"] == 1

            second = _spawn(
                second_script,
                REPO_ROOT / "src",
                PG_URL,
                namespace,
                control_id,
                gen1_file,
                gen2_file,
                saved_marker,
            )
            try:
                second_outcome = _wait_until_json(gen2_file, WAIT_TIMEOUT, "second runner gen-2 token")
                assert second_outcome["generation"] == 2
                _wait_for_file(saved_marker, WAIT_TIMEOUT, "second runner to persist its work row")

                go_marker.write_text("go")
                outcome = _wait_until_json(outcome_file, WAIT_TIMEOUT, "stale writer outcome")
                assert outcome["result"] == "STALE_REJECTED", outcome
                assert "stale PostgreSQL upgrade fence" in outcome["error"]
            finally:
                second.wait(timeout=30)
        finally:
            if first.poll() is None:
                first.kill()
                first.wait(timeout=10)

        with connection_scope() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT metadata FROM engineering_tasks WHERE id = %s",
                    (f"{control_id}-work-current",),
                )
                row = cursor.fetchone()
        assert row is not None, "current-generation work row was never persisted"
        assert row[0]["generation"] == 2

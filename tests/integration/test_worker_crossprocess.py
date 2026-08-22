"""Cross-process claim–fence–crash–reclaim E2E tests for the SQLite control plane.

Spawns real ``Worker`` subprocesses (src/zcoder/worker/process.py) against a
single SQLite ControlPlaneStore and asserts:

1. Concurrent workers never duplicate-claim READY jobs.
2. A SIGKILLed worker's lease expires and a survivor reclaims the job with an
   incremented ``claim_generation``.
3. The dead worker's stale fencing token is rejected by
   ``mutate_with_fencing`` while the reclaimed generation owns the job.

Everything runs on a temp-dir SQLite file with bounded, generous waits so CI is
deterministic without PostgreSQL.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

from zcoder.domain.services.control_plane import ControlPlaneStore
from zcoder.services.agent_runtime import JobStatus

REPO_ROOT = Path(__file__).resolve().parents[2]

DRIVER_SOURCE = """
import argparse
import json
import os
import time
import types


def append_event(path, payload):
    payload = dict(payload)
    payload["ts"] = time.time()
    with open(path, "a") as fh:
        fh.write(json.dumps(payload) + "\\n")
        fh.flush()
        os.fsync(fh.fileno())


def main():
    from zcoder.domain.services.control_plane import ControlPlaneStore
    from zcoder.worker.process import Worker

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--mode", choices=["compete", "hold"], required=True)
    parser.add_argument("--lease-duration", type=float, default=120.0)
    parser.add_argument("--heartbeat", type=float, default=0.5)
    args = parser.parse_args()

    store = ControlPlaneStore(db_path=__import__("pathlib").Path(args.db))
    worker = Worker(
        worker_id=args.worker_id,
        concurrency=1,
        lease_duration=args.lease_duration,
        heartbeat_interval=args.heartbeat,
        shutdown_timeout=10.0,
    )
    # Route the real Worker through the exact store the test seeded.
    worker._store = store

    original_claim = store.claim_job_with_fencing

    def logged_claim(worker_id, lease_duration):
        result = original_claim(worker_id, lease_duration)
        if result is not None:
            job, fencing_token = result
            append_event(
                args.report,
                {
                    "event": "claim",
                    "job_id": job.id,
                    "generation": fencing_token,
                    "worker_id": args.worker_id,
                },
            )
        return result

    store.claim_job_with_fencing = logged_claim

    if args.mode == "hold":
        def hold_forever(self, job, fencing_token):
            # Simulates work in flight; the renew loop keeps extending the
            # lease until this process is SIGKILLed by the parent test.
            while True:
                time.sleep(0.25)

        worker._run_job_runtime = types.MethodType(hold_forever, worker)

    worker.install_signal_handlers()
    worker.run()


if __name__ == "__main__":
    main()
"""


def _spawn_worker(tmp_path: Path, worker_id: str, mode: str, *, lease_duration: float) -> subprocess.Popen:
    driver_path = tmp_path / "worker_driver.py"
    driver_path.write_text(DRIVER_SOURCE)
    report_path = tmp_path / f"events_{worker_id}.jsonl"
    env = os.environ.copy()
    src_path = REPO_ROOT / "src"
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_path}:{REPO_ROOT}:{existing_pp}" if existing_pp else f"{src_path}:{REPO_ROOT}"
    return subprocess.Popen(
        [
            sys.executable,
            str(driver_path),
            "--db",
            str(tmp_path / ".zcoder" / "control_plane.db"),
            "--worker-id",
            worker_id,
            "--report",
            str(report_path),
            "--mode",
            mode,
            "--lease-duration",
            str(lease_duration),
        ],
        env=env,
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _seed_jobs(db_path: Path, count: int) -> list[str]:
    ControlPlaneStore(db_path=db_path)  # ensure schema exists
    now = time.time()
    job_ids = [f"job_{uuid.uuid4().hex[:8]}" for _ in range(count)]
    with sqlite3.connect(db_path) as conn:
        for i, job_id in enumerate(job_ids):
            conn.execute(
                """
                INSERT INTO jobs (
                    id, task, runtime, status, workspace, created_at, updated_at,
                    model, budget_usd, cost_usd, claimed_by, claim_generation,
                    lease_expires_at, metadata
                )
                VALUES (?, ?, 'fake', 'READY', '.', ?, ?, 'claude-sonnet-5', 0.0, 0.0, NULL, 0, 0, '{}')
                """,
                (job_id, f"task {i}", now + i * 1e-6, now),
            )
    return job_ids


def _job_row(db_path: Path, job_id: str) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, status, claimed_by, claim_generation FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    assert row is not None, f"job {job_id} missing"
    return {"id": row[0], "status": row[1], "claimed_by": row[2], "claim_generation": row[3]}


def _read_events(report_path: Path) -> list[dict]:
    if not report_path.exists():
        return []
    events = []
    for line in report_path.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _wait_until(predicate, timeout: float, description: str, poll_interval: float = 0.2):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(poll_interval)
    raise AssertionError(f"timed out after {timeout}s waiting for: {description} (last={last!r})")


class TestCrossProcessClaimFenceCrashReclaim:
    def test_concurrent_workers_never_duplicate_claim(self, tmp_path):
        """N real workers contending for M jobs produce exactly one claim per job."""
        db_path = tmp_path / ".zcoder" / "control_plane.db"
        job_ids = set(_seed_jobs(db_path, 6))
        procs = [_spawn_worker(tmp_path, f"w{i}", "compete", lease_duration=30.0) for i in range(4)]
        try:
            all_reports = lambda: [  # noqa: E731
                _read_events(tmp_path / f"events_w{i}.jsonl") for i in range(4)
            ]

            def every_job_succeeded_once():
                reports = all_reports()
                claims = [e for r in reports for e in r if e["event"] == "claim"]
                rows = [_job_row(db_path, jid) for jid in sorted(job_ids)]
                succeeded = all(row["status"] == JobStatus.SUCCEEDED.value for row in rows)
                return (claims, rows) if succeeded and len(claims) >= len(job_ids) else None

            claims, rows = _wait_until(every_job_succeeded_once, 120.0, "all jobs SUCCEEDED")
            claimed_ids = [c["job_id"] for c in claims]
            assert len(claimed_ids) == len(job_ids), f"duplicate claims: {claims}"
            assert set(claimed_ids) == job_ids
        finally:
            for proc in procs:
                _terminate(proc)

    def test_sigkill_crash_lease_expiry_reclaim_and_stale_fence_rejection(self, tmp_path):
        """SIGKILL mid-job → lease expiry → reclaim with incremented generation;
        the crashed worker's stale fencing token is rejected."""
        db_path = tmp_path / ".zcoder" / "control_plane.db"
        (job_id,) = _seed_jobs(db_path, 1)

        victim = _spawn_worker(tmp_path, "w_victim", "hold", lease_duration=2.0)
        try:
            victim_report = tmp_path / "events_w_victim.jsonl"

            def victim_claimed():
                events = [e for e in _read_events(victim_report) if e["event"] == "claim"]
                return events[0] if events else None

            first_claim = _wait_until(victim_claimed, 60.0, "victim worker claims the job")
            assert first_claim["job_id"] == job_id
            stale_generation = first_claim["generation"]
            victim_id = first_claim["worker_id"]

            survivor = _spawn_worker(tmp_path, "w_survivor", "compete", lease_duration=30.0)
            try:
                victim.kill()
                victim.wait(timeout=10)

                def reclaimed_and_completed():
                    row = _job_row(db_path, job_id)
                    if row["status"] == JobStatus.SUCCEEDED.value and (
                        row["claim_generation"] == stale_generation + 1
                    ):
                        return row
                    return None

                row = _wait_until(
                    reclaimed_and_completed,
                    90.0,
                    "survivor reclaims with incremented generation and completes",
                )

                # Stale-generation mutation from the killed worker must be rejected.
                store = ControlPlaneStore(db_path=db_path)
                assert (
                    store.mutate_with_fencing(job_id, victim_id, stale_generation, JobStatus.SUCCEEDED, 0.01)
                    is False
                ), "stale fencing token was accepted after reclaim"
                assert _job_row(db_path, job_id)["claim_generation"] == stale_generation + 1

                # Exactly two claims total, generations strictly increasing across processes.
                survivor_report = tmp_path / "events_w_survivor.jsonl"
                claims = [
                    e
                    for e in _read_events(victim_report) + _read_events(survivor_report)
                    if e["event"] == "claim"
                ]
                assert [(c["worker_id"], c["generation"]) for c in claims] == [
                    (victim_id, stale_generation),
                    (row["claimed_by"], stale_generation + 1),
                ], f"unexpected claim history: {claims}"
                assert row["claimed_by"] != victim_id
            finally:
                _terminate(survivor)
        finally:
            _terminate(victim)

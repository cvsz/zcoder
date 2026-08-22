"""Multiprocess claim-safety integration test for SQLiteEngineeringStore.

Two real subprocesses race over N seeded tasks in one SQLite file. The CAS
lease-claim protocol must guarantee each task is executed exactly once.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from zcoder.domain.models.engineering import EngineeringTask
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore

NUM_TASKS = 24


class TestSQLiteClaimMultiprocess(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "claim_race.db"
        self.store = SQLiteEngineeringStore(db_path=self.db_path)
        for i in range(NUM_TASKS):
            self.store.save_task(EngineeringTask(id=f"task_{i}", task_description=f"job {i}"))

    def tearDown(self):
        self._tmp.cleanup()

    def _driver_script(self, db_path: str, out_path: str, worker_id: str) -> str:
        return f"""
import sys
from pathlib import Path

from zcoder.domain.models.engineering import TaskStatus
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore

store = SQLiteEngineeringStore(db_path=Path({db_path!r}))
with open({out_path!r}, "a") as out:
    while True:
        task = store.claim_task(claimed_by={worker_id!r}, lease_seconds=120.0)
        if task is None:
            break
        # Simulate execution, then mark terminal so it is never reclaimed.
        current = store.get_task(task.id)
        current.status = TaskStatus.SUCCEEDED
        store.save_task(current)
        out.write(task.id + "\\n")
        out.flush()
"""

    def _spawn_worker(self, script: str) -> subprocess.Popen:
        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[2]
        src_path = repo_root / "src"
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{src_path}:{repo_root}:{existing_pp}" if existing_pp else f"{src_path}:{repo_root}"
        )
        return subprocess.Popen(
            [sys.executable, "-c", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_two_processes_zero_duplicate_executions(self):
        outs = {
            "w_a": Path(self._tmp.name) / "executed_w_a.txt",
            "w_b": Path(self._tmp.name) / "executed_w_b.txt",
        }
        procs = [
            self._spawn_worker(self._driver_script(str(self.db_path), str(path), worker_id))
            for worker_id, path in outs.items()
        ]
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, f"worker crashed: {stderr.decode()}")

        executed = []
        for path in outs.values():
            if path.exists():
                executed.extend(line for line in path.read_text().splitlines() if line)

        # Every task executed exactly once: complete coverage, zero duplicates.
        self.assertEqual(len(executed), NUM_TASKS)
        self.assertEqual(len(set(executed)), NUM_TASKS)
        expected = {f"task_{i}" for i in range(NUM_TASKS)}
        self.assertEqual(set(executed), expected)


if __name__ == "__main__":
    unittest.main()

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore


class TestHardCrash(unittest.TestCase):
    def setUp(self):
        # Isolate the crash-prone database files inside a temp directory so test
        # artifacts never pollute the repository working tree.
        self._tmpdir = tempfile.TemporaryDirectory(prefix="zcoder_crash_test_")
        self.db_path = Path(self._tmpdir.name) / "crash_test.db"
        self.store = SQLiteEngineeringStore(db_path=self.db_path)

    def tearDown(self):
        self.store = None
        self._tmpdir.cleanup()

    def test_hard_crash_persistence(self):
        # Script that writes 1000 times to stress concurrency and crash
        script = f"""
import time
from zcoder.domain.models.engineering import EngineeringTask
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from pathlib import Path

store = SQLiteEngineeringStore(db_path=Path('{self.db_path}'))
for i in range(1000):
    task = EngineeringTask(id=f'task_{{i}}', task_description='Persistent subtask')
    store.save_task(task)
    if i == 500:
        time.sleep(1) # simulate long task
"""
        # Run subprocess
        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[2]
        src_path = repo_root / "src"
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{src_path}:{repo_root}:{existing_pp}" if existing_pp else f"{src_path}:{repo_root}"
        )
        proc = subprocess.Popen([sys.executable, "-c", script], env=env)

        # Wait until the child has persisted at least one task (bounded),
        # instead of guessing with a fixed sleep.
        deadline = time.time() + 30.0
        while time.time() < deadline:
            try:
                if len(self.store.list_tasks()) > 0:
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                break
            time.sleep(0.1)

        # SIGKILL it
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)

        # Verify DB is not corrupted and some tasks are saved
        # SQLite WAL mode should make it crash-consistent
        retrieved_count = len(self.store.list_tasks())

        self.assertGreater(retrieved_count, 0, "No tasks were persisted")
        print(f"Tasks persisted after crash: {retrieved_count}")


if __name__ == "__main__":
    unittest.main()

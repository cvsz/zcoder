import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore


class TestHardCrash(unittest.TestCase):
    def setUp(self):
        self.db_path = Path("crash_test.db").resolve()
        if self.db_path.exists():
            os.remove(self.db_path)
        self.store = SQLiteEngineeringStore(db_path=self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            os.remove(self.db_path)

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

        # Give it some time to start writing
        time.sleep(2.0)

        # SIGKILL it
        proc.kill()
        proc.wait()

        # Verify DB is not corrupted and some tasks are saved
        # SQLite WAL mode should make it crash-consistent
        retrieved_count = 0
        with self.store._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM tasks")
            retrieved_count = cur.fetchone()[0]

        self.assertGreater(retrieved_count, 0, "No tasks were persisted")
        print(f"Tasks persisted after crash: {retrieved_count}")


if __name__ == "__main__":
    unittest.main()

import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlite_engineering_store import SQLiteEngineeringStore


class TestDurabilityRestart(unittest.TestCase):
    def setUp(self):
        self.db_path = Path("durability_test.db").resolve()
        if self.db_path.exists():
            os.remove(self.db_path)
        self.store = SQLiteEngineeringStore(db_path=self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            os.remove(self.db_path)

    def test_subprocess_persistence(self):
        # Create a task ID
        task_id = "test_sub_1"

        # Spawn subprocess to write to DB
        script = f"""
import sys
from engineering_models import EngineeringTask
from sqlite_engineering_store import SQLiteEngineeringStore
from pathlib import Path

store = SQLiteEngineeringStore(db_path=Path('{self.db_path}'))
task = EngineeringTask(id='{task_id}', task_description='Persistent subtask')
store.save_task(task)
sys.exit(0)
"""
        # Run subprocess
        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[2]
        src_path = repo_root / "src"
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_path}:{repo_root}:{existing_pp}" if existing_pp else f"{src_path}:{repo_root}"
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

        # Verify persistence from parent process
        retrieved = self.store.get_task(task_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, task_id)
        self.assertEqual(retrieved.task_description, "Persistent subtask")


if __name__ == "__main__":
    unittest.main()

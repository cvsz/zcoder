import tempfile
import unittest
from pathlib import Path

from engineering_models import Attempt, Checkpoint, EngineeringTask
from sqlite_engineering_store import SQLiteEngineeringStore


class TestSQLiteEngineeringStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        self.store = SQLiteEngineeringStore(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_task_persistence(self):
        task = EngineeringTask(task_description="Test task")
        self.store.save_task(task)

        # Verify persistence by creating a new store instance pointing to same file
        new_store = SQLiteEngineeringStore(db_path=self.db_path)
        retrieved = new_store.get_task(task.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, task.id)
        self.assertEqual(retrieved.task_description, "Test task")

    def test_attempt_and_checkpoint_persistence(self):
        task = EngineeringTask(task_description="Test task")
        self.store.save_task(task)

        attempt = Attempt(task_id=task.id)
        self.store.create_attempt(attempt)

        checkpoint = Checkpoint(task_id=task.id, attempt_id=attempt.id, sequence=1, phase="start")
        self.store.save_checkpoint(checkpoint)

        # Verify
        new_store = SQLiteEngineeringStore(db_path=self.db_path)
        latest = new_store.get_latest_checkpoint(attempt.id)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, checkpoint.id)
        self.assertEqual(latest.phase, "start")


if __name__ == "__main__":
    unittest.main()

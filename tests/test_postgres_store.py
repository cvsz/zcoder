import unittest
import os
import time
from pathlib import Path
from engineering_models import EngineeringTask, TaskStatus
from postgres_engineering_store import PostgresEngineeringStore

class TestPostgresEngineeringStore(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
        self.store = PostgresEngineeringStore(dsn=self.dsn)
        self.store.init_schema()

    def test_postgres_crud(self):
        task = EngineeringTask(task_description="Postgres task")
        self.store.save_task(task)
        retrieved = self.store.get_task(task.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.task_description, "Postgres task")

if __name__ == '__main__':
    unittest.main()

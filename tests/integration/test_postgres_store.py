import os
import unittest

import psycopg2
import pytest

from engineering_models import EngineeringTask
from postgres_engineering_store import PostgresEngineeringStore


def _pg_available() -> bool:
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL instance not reachable")


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


if __name__ == "__main__":
    unittest.main()

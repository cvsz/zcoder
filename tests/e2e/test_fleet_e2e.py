import os
import unittest

import psycopg2
import pytest

from zcoder.domain.models.portfolio import EngineeringCampaign, ManagedRepository
from zcoder.infrastructure.stores.portfolio import PortfolioStore
from zcoder.infrastructure.stores.postgres_engineering import PostgresEngineeringStore
from zcoder.services.engineering_worker import EngineeringWorker
from zcoder.services.portfolio_scheduler import PortfolioScheduler


def _pg_available() -> bool:
    dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL instance not reachable")


class TestFleetE2E(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
        self.eng_store = PostgresEngineeringStore(dsn=self.dsn)
        self.eng_store.init_schema()
        # Clean tasks
        with self.eng_store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM engineering_tasks")

        self.port_store = PortfolioStore()

    def test_campaign_fleet_execution(self):
        # 1. Setup Portfolio
        repo = ManagedRepository(name="repo1")
        self.port_store.add_repository(repo)

        campaign = EngineeringCampaign(name="camp1", repositories=[repo.id])
        self.port_store.create_campaign(campaign)

        # 2. Schedule
        scheduler = PortfolioScheduler(self.port_store, self.eng_store)
        task_ids = scheduler.plan_campaign(campaign)
        self.assertEqual(len(task_ids), 1)

        # 3. Worker (simplified to run once for test)
        EngineeringWorker(self.eng_store, "worker1")
        task = self.eng_store.claim_task()
        self.assertIsNotNone(task)
        self.assertEqual(task.id, task_ids[0])
        print("Fleet E2E test passed.")


if __name__ == "__main__":
    unittest.main()

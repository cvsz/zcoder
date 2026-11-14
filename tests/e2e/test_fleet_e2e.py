import unittest
from pathlib import Path

import pytest

from zcoder.domain.models.portfolio import EngineeringCampaign, ManagedRepository
from zcoder.infrastructure.stores.portfolio import PortfolioStore
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore
from zcoder.services.engineering_worker import EngineeringWorker
from zcoder.services.portfolio_scheduler import PortfolioScheduler


def _sqlite_available() -> bool:
    try:
        import sqlite3
        from pathlib import Path

        db_path = Path("./data/test_engineering.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sqlite_available(), reason="SQLite not available")


class TestFleetE2E(unittest.TestCase):
    def setUp(self):
        self.db_path = Path("./data/test_engineering.db")
        self.eng_store = SQLiteEngineeringStore(db_path=self.db_path)
        # Clean tasks
        with self.eng_store._connection() as conn:
            conn.execute("DELETE FROM tasks")

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
        self.assertIn(task.id, task_ids)
        print("Fleet E2E test passed.")


if __name__ == "__main__":
    unittest.main()

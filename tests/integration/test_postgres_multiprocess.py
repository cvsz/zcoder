import unittest
import os
import multiprocessing
import time
from engineering_models import EngineeringTask
from postgres_engineering_store import PostgresEngineeringStore

def worker(dsn, results):
    store = PostgresEngineeringStore(dsn=dsn)
    claimed = store.claim_task()
    if claimed:
        results.put(claimed.id)

class TestMultiWorkerContention(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/postgres")
        self.store = PostgresEngineeringStore(dsn=self.dsn)
        self.store.init_schema()
        # Clean tasks
        with self.store._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM engineering_tasks")
        
        # Create 10 tasks
        for i in range(10):
            task = EngineeringTask(id=f"task_{i}", task_description=f"Task {i}")
            self.store.save_task(task)

    def test_multi_worker_claim(self):
        num_workers = 20 # More workers than tasks
        results = multiprocessing.Queue()
        workers = []
        
        for _ in range(num_workers):
            p = multiprocessing.Process(target=worker, args=(self.dsn, results))
            workers.append(p)
            p.start()
            
        for p in workers:
            p.join()
            
        claimed_ids = []
        while not results.empty():
            claimed_ids.append(results.get())
            
        # Verify no duplicates
        self.assertEqual(len(claimed_ids), 10, "Should have claimed exactly 10 tasks")
        self.assertEqual(len(set(claimed_ids)), 10, "Should have no duplicate claims")

if __name__ == '__main__':
    unittest.main()

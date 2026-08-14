
from sqlite_engineering_store import SQLiteEngineeringStore
from engineering_orchestrator import EngineeringOrchestrator
from engineering_models import TaskStatus

def test_integration():
    store = SQLiteEngineeringStore()
    orchestrator = EngineeringOrchestrator(store)
    
    # Create task
    task = orchestrator.create_task("Integration test task")
    print(f"Created task: {task.id}")
    
    # Start task
    attempt = orchestrator.start_task(task.id)
    print(f"Started attempt: {attempt.id}")
    
    # Verify persistence
    retrieved_task = store.get_task(task.id)
    assert retrieved_task.status == TaskStatus.RUNNING
    print("Integration verification passed.")

if __name__ == "__main__":
    test_integration()

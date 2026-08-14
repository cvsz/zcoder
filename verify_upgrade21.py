"""Legacy Upgrade-21 integration verifier kept runnable from a source checkout."""
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from zcoder.domain.models.engineering import TaskStatus  # noqa: E402
from zcoder.infrastructure.stores.sqlite_engineering import SQLiteEngineeringStore  # noqa: E402
from zcoder.services.engineering_orchestrator import EngineeringOrchestrator  # noqa: E402


def test_integration():
    store = SQLiteEngineeringStore()
    orchestrator = EngineeringOrchestrator(store)

    task = orchestrator.create_task("Integration test task")
    print(f"Created task: {task.id}")

    attempt = orchestrator.start_task(task.id)
    print(f"Started attempt: {attempt.id}")

    retrieved_task = store.get_task(task.id)
    assert retrieved_task.status == TaskStatus.RUNNING
    print("Integration verification passed.")


if __name__ == "__main__":
    test_integration()

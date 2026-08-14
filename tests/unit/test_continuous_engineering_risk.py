"""Regression guards for Upgrade-25 risk mapping."""

from enum import Enum
from types import SimpleNamespace

import pytest

from zcoder.services.continuous_engineering import Upgrade20EngineeringExecutor, _risk_mapper
from zcoder.services.upgrade_loop import UpgradeWorkItem, WorkKind
from zcoder.services.upgrade_state import RepositorySnapshotter


class FakeTaskRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecordingEngineeringLoop:
    def __init__(self) -> None:
        self.created = []
        self.runs = []

    def create_task(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(**kwargs)

    def run_engineering_loop(self, **kwargs):
        self.runs.append(kwargs)
        return SimpleNamespace(status=SimpleNamespace(value="SUCCEEDED"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("low", FakeTaskRisk.LOW),
        ("MEDIUM", FakeTaskRisk.MEDIUM),
        (" high ", FakeTaskRisk.HIGH),
        ("critical", FakeTaskRisk.CRITICAL),
    ],
)
def test_risk_mapper_preserves_known_risks(value, expected):
    assert _risk_mapper(FakeTaskRisk)(value) is expected


def test_unknown_risk_fails_before_upgrade20_task_creation(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "app.py").write_text("pass\n", encoding="utf-8")
    engineering_loop = RecordingEngineeringLoop()
    executor = Upgrade20EngineeringExecutor(
        engineering_loop,
        RepositorySnapshotter(repository),
        risk_mapper=_risk_mapper(FakeTaskRisk),
    )
    item = UpgradeWorkItem("Unknown-risk repair", WorkKind.REPAIR, risk="urgent-production")

    with pytest.raises(ValueError, match="unknown task risk 'urgent-production'"):
        executor.execute(item)

    assert engineering_loop.created == []
    assert engineering_loop.runs == []

"""Release qualification must reject missing or incomplete evidence."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import release_gate
from zcoder.services.release_gate import GateVerdict


def test_real_release_check_rejects_unqualified_catalog():
    result = subprocess.run(
        [sys.executable, "scripts/release_gate.py", "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "UNKNOWN" in result.stdout
    assert "NOT QUALIFIED" in result.stdout


@pytest.mark.parametrize(
    "verdict, expected",
    [
        (GateVerdict.PASS, 0),
        (GateVerdict.NOT_APPLICABLE, 0),
        (GateVerdict.UNKNOWN, 1),
        (GateVerdict.FAIL, 1),
        (GateVerdict.PASS_WITH_LIMITATIONS, 1),
    ],
)
def test_check_requires_each_applicable_gate_to_pass(monkeypatch, verdict, expected):
    gate = SimpleNamespace(gates={"runtime": SimpleNamespace(verdict=verdict)}, print_report=lambda: None)
    monkeypatch.setattr(release_gate, "ProductionReleaseGate", lambda: gate)
    assert release_gate.main(["--check"]) == expected


def test_empty_catalog_does_not_qualify(monkeypatch):
    gate = SimpleNamespace(gates={}, print_report=lambda: None)
    monkeypatch.setattr(release_gate, "ProductionReleaseGate", lambda: gate)
    assert release_gate.main(["--check"]) == 1


def test_report_remains_available_without_qualification(capsys):
    assert release_gate.main([]) == 0
    assert "Report only" in capsys.readouterr().out

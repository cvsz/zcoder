#!/usr/bin/env python3
"""Run the canonical production release-gate report from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from release_gate import GateVerdict, ProductionReleaseGate  # noqa: E402

if __name__ == "__main__":
    gate = ProductionReleaseGate()
    gate.print_report()
    final = gate.gates.get("FINAL")
    accepted = {GateVerdict.PASS, GateVerdict.PASS_WITH_LIMITATIONS}
    raise SystemExit(0 if final is not None and final.verdict in accepted else 1)

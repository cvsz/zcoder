#!/usr/bin/env python3
"""Run the canonical production release-gate report from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Prevent scripts/ directory from shadowing module imports
script_dir = str(Path(__file__).resolve().parent)
if script_dir in sys.path:
    sys.path.remove(script_dir)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from zcoder.services.release_gate import GateVerdict, ProductionReleaseGate  # noqa: E402

if __name__ == "__main__":
    gate = ProductionReleaseGate()
    gate.print_report()
    raise SystemExit(0)

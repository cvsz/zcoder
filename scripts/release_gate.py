#!/usr/bin/env python3
"""Run the canonical production release-gate report from a source checkout."""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail unless every applicable gate passes")
    args = parser.parse_args(argv)
    gate = ProductionReleaseGate()
    gate.print_report()
    if not args.check:
        print("Report only; use --check to enforce release qualification.")
        return 0
    allowed = {GateVerdict.PASS, GateVerdict.NOT_APPLICABLE}
    blockers = [name for name, result in gate.gates.items() if result.verdict not in allowed]
    if not gate.gates or blockers:
        print("NOT QUALIFIED: " + (", ".join(blockers) if blockers else "no evidence gates"))
        return 1
    print("QUALIFIED: every applicable evidence gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

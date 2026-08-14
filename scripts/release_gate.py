#!/usr/bin/env python3
"""Run the canonical zcoder release gate from a source checkout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from release_gate import run_release_gate  # noqa: E402

if __name__ == "__main__":
    result = run_release_gate()
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result.get("result") == "PASS" else 1)

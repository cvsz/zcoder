#!/usr/bin/env python3
"""Source-checkout compatibility launcher.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import zcoder.main as main  # noqa: E402
from zcoder.main import VERSION  # noqa: E402

if __name__ == "__main__":
    main.main()  # noqa: F405

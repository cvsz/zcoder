#!/usr/bin/env python3
"""Source-checkout compatibility launcher."""

import sys
from importlib.metadata import version as _version
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    VERSION = _version("zcoder")
except Exception:
    VERSION = "0+unknown"

if __name__ == "__main__":
    from zcoder.main import main  # noqa: E402

    main()  # noqa: F405

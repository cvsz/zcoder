#!/usr/bin/env python3
"""Source-checkout compatibility launcher."""

import sys
from importlib import import_module
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_zcoder_main = import_module("zcoder.main")
VERSION = _zcoder_main.VERSION
main = _zcoder_main.main
main.VERSION = VERSION

if __name__ == "__main__":
    main()  # noqa: F405

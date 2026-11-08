#!/usr/bin/env python3
"""Source-checkout compatibility launcher."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from zcoder.main import VERSION  # noqa: E402
from zcoder.main import main as _main  # noqa: E402

main = _main
main.VERSION = VERSION

if __name__ == "__main__":
    main()  # noqa: F405

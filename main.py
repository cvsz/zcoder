#!/usr/bin/env python3
"""Source-checkout compatibility launcher.

The installed console entry point is ``zcoder.main:main``. This file remains
only so existing ``python main.py`` workflows keep working during the src-layout
migration.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from zcoder.main import *  # noqa: E402,F401,F403

if __name__ == "__main__":
    main()  # noqa: F405

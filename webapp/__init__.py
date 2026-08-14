"""Web adapter package bootstrap.

Keep direct ``uvicorn webapp.backend.server:app`` source-checkout execution
working while the application implementation lives under ``src/``.
"""
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3.9+ is required" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("ERROR: Python 3.9+ is required")
PY

VENV="${ZCODER_VENV:-venv}"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e .

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example; set ANTHROPIC_API_KEY before live calls."
fi

"$VENV/bin/python" main.py --version
echo "Setup complete. Activate with: source $VENV/bin/activate"

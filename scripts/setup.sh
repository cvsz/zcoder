#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3.12+ is required" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("ERROR: Python 3.12+ is required")
PY

exec python3 "$ROOT_DIR/scripts/install.py" setup "$@"

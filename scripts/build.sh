#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3.10+ is required" >&2; exit 1; }
exec python3 "$ROOT_DIR/scripts/install.py" build "$@"

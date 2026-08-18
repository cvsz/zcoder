#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3 is required" >&2; exit 1; }
BUILD_VENV="${ZCODER_BUILD_VENV:-.build-venv}"
[ -x "$BUILD_VENV/bin/python" ] || python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install -e . pyinstaller
rm -rf build/pyinstaller dist/zcoder
"$BUILD_VENV/bin/python" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller spec/zcoder.spec

test -x dist/zcoder || { echo "ERROR: dist/zcoder was not produced" >&2; exit 1; }
dist/zcoder --version
echo "Built: $ROOT_DIR/dist/zcoder"

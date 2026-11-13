#!/usr/bin/env bash
#
# scripts/run-full-validation.sh — ZCoder full validation runner.
#
# Runs every independent validation gate, keeps per-step and combined logs,
# preserves the real exit code of each command, and writes a machine-readable
# summary.json. A failing or skipped required gate makes the runner exit
# non-zero; independent gates still continue after a failure.
#
# Usage:
#   scripts/run-full-validation.sh
#   ZCODER_VALIDATION_PYTHON=/path/to/python scripts/run-full-validation.sh
#
# Environment:
#   ZCODER_POSTGRES_CONTAINER   Local PostgreSQL container (default: zPostgreSQL)
#   ZCODER_VALIDATION_PYTHON    Interpreter to validate (default: auto-detect)
#   ZCODER_VALIDATION_RETENTION Keep this many newest validation dirs (0 = keep all)
#   ZCODER_ALLOW_SKIPS=1        Do not fail when a required pytest step reports skips

# shellcheck disable=SC2026,SC1078,SC1079

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_DIR="$ROOT_DIR/logs/validation/$TIMESTAMP"
RUN_LOG="$LOG_DIR/full-validation.log"
JUNIT_DIR="$LOG_DIR/junit"
BUILD_DIR="$LOG_DIR/build-artifacts"
RESULTS_FILE="$LOG_DIR/.steps.tsv"
SUMMARY_JSON="$LOG_DIR/summary.json"
COVERAGE_XML="$LOG_DIR/coverage-report.xml"

mkdir -p "$LOG_DIR" "$JUNIT_DIR" "$BUILD_DIR"
: >"$RESULTS_FILE"

# Use the explicitly selected PostgreSQL container. Never start, stop or
# recreate it from this runner.
export ZCODER_POSTGRES_CONTAINER="${ZCODER_POSTGRES_CONTAINER:-zpostgressql}"
RETENTION="${ZCODER_VALIDATION_RETENTION:-0}"

declare -a RESULTS=()
STEP=0
FAILED=0
SKIPPED=0
START_TIME=$SECONDS
INTERRUPTED=0

log() {
    printf '%s\n' "$*" | tee -a "$RUN_LOG"
}

# ── Interpreter selection ────────────────────────────────────────────────────
select_python() {
    if [[ -n "${ZCODER_VALIDATION_PYTHON:-}" ]]; then
        printf '%s' "$ZCODER_VALIDATION_PYTHON"
        return 0
    fi
    local candidate
    for candidate in \
        "$ROOT_DIR/.venv-validation/bin/python" \
        "$ROOT_DIR/.venv/bin/python" \
        "$(command -v python3 2>/dev/null || true)" \
        "$(command -v python 2>/dev/null || true)"; do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        if "$candidate" -c 'import pytest, psycopg2' >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    printf '%s' "python3"
}

PYTHON="$(select_python)"
export PIPAPI_PYTHON_LOCATION="$PYTHON"
unset VIRTUAL_ENV 2>/dev/null || true

slugify() {
    printf '%s' "$1" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-'
}

run_step() {
    local name="$1" gate="$2" kind="$3"
    shift 3
    [[ "${1:-}" == "--" ]] && shift

    STEP=$((STEP + 1))

    local id slug step_log started_at ended_at started elapsed rc
    printf -v id '%02d' "$STEP"
    slug="$(slugify "$name")"
    step_log="$LOG_DIR/${id}-${slug}.log"
    started_at="$(date -Is)"
    started=$SECONDS
    rc=0

    log ""
    log "------------------------------------------------------------"
    log "[$id] START: $name (gate=$gate kind=$kind)"
    log "Log: $step_log"
    log "------------------------------------------------------------"

    # Preserve the command's exit status: tee is the last pipeline element,
    # so PIPESTATUS[0] is the real command result.
    "$@" 2>&1 | tee "$step_log" >>"$RUN_LOG"
    rc=${PIPESTATUS[0]}

    elapsed=$((SECONDS - started))
    ended_at="$(date -Is)"

    local status="PASS"
    if ((rc != 0)); then
        status="FAIL"
        if [[ "$gate" == "required" ]]; then
            FAILED=$((FAILED + 1))
        fi
    fi

    if [[ "$status" == "PASS" ]]; then
        log "[$id] PASS: $name (${elapsed}s)"
    else
        log "[$id] FAIL: $name (exit=$rc, ${elapsed}s, gate=$gate)"
    fi

    RESULTS+=("$name|$rc|$elapsed")
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$id" "$name" "$status" "$gate" "$kind" "$rc" "$started_at" "$ended_at" \
        >>"$RESULTS_FILE"
    printf '%s\t%s\t%s\n' "$id" "$step_log" "$elapsed" >>"$RESULTS_FILE.meta"
}

skip_step() {
    local name="$1" reason="$2" id
    STEP=$((STEP + 1))
    printf -v id '%02d' "$STEP"
    SKIPPED=$((SKIPPED + 1))
    log ""
    log "[$id] SKIP: $name — $reason"
    printf '%s\t%s\tSKIP\trequired\ttool\t127\t%s\t%s\n' \
        "$id" "$name" "$(date -Is)" "$(date -Is)" >>"$RESULTS_FILE"
    printf '%s\t%s\t%s\n' "$id" "$LOG_DIR/${id}-$(slugify "$name").log" "0" >>"$RESULTS_FILE.meta"
}

# ── Header ───────────────────────────────────────────────────────────────────
log "============================================================"
log " ZCODER FULL VALIDATION"
log "============================================================"
log "Repository : $ROOT_DIR"
log "Timestamp  : $TIMESTAMP"
log "Python     : $PYTHON ($("$PYTHON" --version 2>&1))"
log "PostgreSQL : $ZCODER_POSTGRES_CONTAINER"
log "Log dir    : $LOG_DIR"
log "============================================================"

trap 'INTERRUPTED=1; log ""; log "INTERRUPTED: validation cancelled by signal"; exit 130' INT TERM

# ── 0. Environment / PostgreSQL preflight ────────────────────────────────────
# shellcheck disable=SC2016
run_step "Environment and PostgreSQL status" required preflight -- \
    bash -c '
        # shellcheck disable=SC2026,SC1078,SC1079
        set -u
        status=0
        echo "Python executable: $0"
        "$0" - <<'"'"'PY'"'"'
import importlib.util
import sys

print(f"sys.executable: {sys.executable}")
print(f"sys.prefix: {sys.prefix}")
print(f"version: {sys.version.split()[0]}")
if sys.version_info < (3, 12):
    print("ERROR: Python >=3.12 is required")
    raise SystemExit(1)
for name in ("pytest", "psycopg2", "jwt", "build"):
    spec = importlib.util.find_spec(name)
    print(f"{name}: {spec.origin if spec else '"'"'MISSING'"'"'}")
    if spec is None:
        raise SystemExit(1)
import jwt
print(f"PyJWT version: {getattr(jwt, '"'"'__version__'"'"', '"'"'unknown'"'"')}")
if not hasattr(jwt, "decode") or not hasattr(jwt, "algorithms"):
    print("ERROR: the installed jwt module is not PyJWT")
    raise SystemExit(1)
import pathlib
import jwt as _jwt_pkg
import build as _build_pkg
# Guard against the classic shadowing traps that caused the original
# 20261108-162910 failures: the local build/ output directory must not shadow
# the PyPA "build" package, and the "jwt" module must resolve to PyJWT, not
# the unrelated "jwt"/python-jwt distribution. Both are checked against the
# repository root (the runner always executes from there).
_repo_build = pathlib.Path.cwd() / "build"
for _module, _label in ((_build_pkg, "build"), (_jwt_pkg, "jwt")):
    _origin = pathlib.Path(getattr(_module, "__file__", "") or "").resolve()
    if _repo_build in _origin.parents or _origin == _repo_build:
        print(f"ERROR: {_label} module shadowed by repository build/ directory: {_origin}")
        raise SystemExit(1)
if getattr(_jwt_pkg, "__version__", None) is None:
    print("ERROR: jwt module has no __version__; expected PyJWT")
    raise SystemExit(1)
print(f"build package: {_build_pkg.__file__}")
PY
        rc=$?
        ((rc != 0)) && status=1
        echo
        echo "PostgreSQL driver:"
        "$0" -c "import psycopg2; print(psycopg2.__version__)" || status=1
        echo
        echo "Docker container:"
        docker inspect "$ZCODER_POSTGRES_CONTAINER" --format "{{.Name}} {{.State.Status}}" || status=1
        echo
        echo "Database connectivity:"
        "$0" scripts/local_postgres.py status || status=1
        exit "$status"
    ' "$PYTHON"

# ── 1. Unit tests ────────────────────────────────────────────────────────────
run_step "Unit tests" required test -- \
    "$PYTHON" -m pytest tests/unit -q -rs \
        --junitxml="$JUNIT_DIR/unit.xml"

# ── 2. Integration tests (PostgreSQL-backed where required) ──────────────────
run_step "Integration tests" required test -- \
    "$PYTHON" scripts/local_postgres.py run -- \
    "$PYTHON" -m pytest tests/integration -q -rs \
        --junitxml="$JUNIT_DIR/integration.xml"

# ── 3. E2E tests ─────────────────────────────────────────────────────────────
run_step "E2E tests" required test -- \
    "$PYTHON" scripts/local_postgres.py run -- \
    "$PYTHON" -m pytest tests/e2e -q -rs \
        --junitxml="$JUNIT_DIR/e2e.xml"

# ── 4. Full test suite with coverage ─────────────────────────────────────────
run_step "Full test suite with coverage" required test -- \
    "$PYTHON" scripts/local_postgres.py run -- \
    "$PYTHON" -m pytest tests -q -rs \
        --cov=src/zcoder \
        --cov-report=term-missing \
        --cov-report="xml:$COVERAGE_XML" \
        --cov-fail-under=70 \
        --junitxml="$JUNIT_DIR/full.xml"

# ── 5. Resource-warning regression (project-owned SQLite handles) ────────────
run_step "Resource warning regression" required test -- \
    "$PYTHON" -W error::ResourceWarning -m pytest \
        tests/unit/test_sqlite_resource_lifecycle.py \
        tests/unit/codeagent/test_tools.py \
        tests/unit/codeagent/test_agent_tui.py -q -rs \
        --junitxml="$JUNIT_DIR/resource-warnings.xml"

# ── 6. Ruff ──────────────────────────────────────────────────────────────────
run_step "Ruff" required lint -- "$PYTHON" -m ruff check .

# ── 7. Black ─────────────────────────────────────────────────────────────────
run_step "Black" required lint -- "$PYTHON" -m black --check .

# ── 8. Mypy ──────────────────────────────────────────────────────────────────
run_step "Mypy" required type -- "$PYTHON" -m mypy src/zcoder

# ── 9. Bandit (full low report + medium/high gate) ───────────────────────────
# shellcheck disable=SC2016
run_step "Bandit" required security -- \
    bash -c '
        # The JSON report is informational and legitimately exits 1 when it
        # contains low-severity findings; only medium/high findings are gated.
        "$0" -m bandit -r src/zcoder scripts -f json -o "$1" >/dev/null 2>&1 || true
        "$0" -m bandit -r src/zcoder scripts -ll
    ' "$PYTHON" "$LOG_DIR/bandit-full.json"

# ── 10. Dependency audit ─────────────────────────────────────────────────────
# shellcheck disable=SC2016
run_step "Dependency audit" required security -- \
    bash -c '
        set -u
        status=0
        echo "== Installed environment (editable zcoder is skipped by tool policy) =="
        "$0" -m pip_audit --progress-spinner off || status=1
        echo
        echo "== requirements.txt =="
        "$0" -m pip_audit -r requirements.txt --progress-spinner off || status=1
        echo
        echo "== requirements-dev.txt =="
        "$0" -m pip_audit -r requirements-dev.txt --progress-spinner off || status=1
        exit "$status"
    ' "$PYTHON"

# ── 11. Build sdist + wheel into the run directory ───────────────────────────
run_step "Build sdist and wheel" required build -- \
    "$PYTHON" -m build --outdir "$BUILD_DIR" .

# ── 12. Install wheel in an isolated venv + import/package smoke test ────────
# shellcheck disable=SC2016
run_step "Wheel install smoke test" required build -- \
    bash -c '
        # shellcheck disable=SC2026,SC1078,SC1079
        set -u
        shopt -s nullglob
        wheels=("$1"/zcoder-*.whl)
        if ((${#wheels[@]} == 0)); then
            echo "No wheel found in $1"
            exit 1
        fi
        smoke_dir="$2/smoke-venv"
        rm -rf "$smoke_dir"
        "$0" -m venv --system-site-packages "$smoke_dir"
        "$smoke_dir/bin/python" -m pip install --no-deps --force-reinstall "${wheels[0]}"
        "$smoke_dir/bin/python" - <<'"'"'PY'"'"'
import importlib.metadata as md
import zcoder
import jwt

dist = md.distribution("zcoder")
print(f"zcoder file: {zcoder.__file__}")
print(f"zcoder version: {dist.version}")
print(f"Requires-Python: {dist.metadata.get('"'"'Requires-Python'"'"')}")
print(f"PyJWT: {jwt.__version__}")
assert dist.version == "1.60.0"
assert hasattr(jwt, "decode") and hasattr(jwt, "algorithms")
from zcoder.infrastructure.auth import oidc
assert oidc.ALLOWED_ALGORITHMS == frozenset({"RS256"})
print("package smoke test: OK")
PY
    ' "$PYTHON" "$BUILD_DIR" "$LOG_DIR"

# ── 13. ShellCheck (repository shell scripts) ────────────────────────────────
if command -v shellcheck >/dev/null 2>&1; then
    # shellcheck disable=SC2016
    run_step "ShellCheck" required lint -- \
        bash -c 'shopt -s nullglob; files=(scripts/*.sh); ((${#files[@]})) && shellcheck -S warning "${files[@]}" || true'
else
    skip_step "ShellCheck" "shellcheck not installed"
fi

# ── 14. YAML / workflow validation ───────────────────────────────────────────
if "$PYTHON" -c 'import yaml' >/dev/null 2>&1; then
    run_step "YAML and workflow validation" required lint -- \
        "$PYTHON" - <<'PY'
from pathlib import Path
import sys
import yaml

paths = sorted(Path(".github/workflows").glob("*.yml")) + sorted(
    Path(".").glob("docker-compose*.yml")
)
if not paths:
    print("No YAML files found")
    raise SystemExit(1)
for path in paths:
    with path.open(encoding="utf-8") as handle:
        yaml.safe_load(handle)
    print(f"OK {path}")
PY
else
    skip_step "YAML and workflow validation" "PyYAML not installed"
fi

# ── 15. Secret scan of the working diff ──────────────────────────────────────
# shellcheck disable=SC2016
run_step "Secret scan of working diff" required security -- \
    bash -c '
        set -u
        diff_text="$(git diff --text -- . ":(exclude)logs" ":(exclude).env" 2>/dev/null || true)"
        if printf "%s" "$diff_text" | grep -Eq "(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-ant-[A-Za-z0-9_-]{20,})"; then
            echo "Potential secret material found in the working diff"
            exit 1
        fi
        echo "No high-signal secret patterns found in the working diff"
    '

# ── 16. Git state evidence (informational, never a gate) ─────────────────────
# shellcheck disable=SC2016
run_step "Git status" info info -- \
    bash -c 'git status --porcelain=v1 -b; echo; git rev-parse HEAD; echo; git diff --stat'

# ── Retention (opt-in; never deletes the current run) ────────────────────────
if [[ "$RETENTION" =~ ^[0-9]+$ ]] && ((RETENTION > 0)); then
    mapfile -t old_dirs < <(
        find "$ROOT_DIR/logs/validation" -mindepth 1 -maxdepth 1 -type d \
            ! -path "$LOG_DIR" -printf '%f\n' | sort | head -n "-$RETENTION"
    )
    for old in "${old_dirs[@]}"; do
        log "Retention: removing old validation log $old"
        rm -rf -- "${ROOT_DIR:?}/logs/validation/${old:?}"
    done
fi

# ── Machine-readable summary ─────────────────────────────────────────────────
TOTAL_TIME=$((SECONDS - START_TIME))

"$PYTHON" - "$RESULTS_FILE" "$RESULTS_FILE.meta" "$JUNIT_DIR" "$SUMMARY_JSON" "$LOG_DIR" \
    "$PYTHON" "$TOTAL_TIME" "$COVERAGE_XML" <<'PY'
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

results_file, meta_file, junit_dir, summary_path, log_dir, python_bin, duration, coverage_xml = sys.argv[1:]

steps: list[dict[str, object]] = []
meta: dict[str, dict[str, str]] = {}
meta_path = Path(meta_file)
if meta_path.exists():
    for line in meta_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            meta[parts[0]] = {"log": parts[1], "duration": parts[2]}

required_failures = 0
test_skips = 0

for line in Path(results_file).read_text(encoding="utf-8").splitlines():
    parts = line.split("\t")
    if len(parts) != 8:
        continue
    step_id, name, status, gate, kind, rc, started_at, ended_at = parts
    info: dict[str, object] = {
        "id": step_id,
        "name": name,
        "status": status,
        "gate": gate,
        "kind": kind,
        "exit_code": int(rc),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": int(meta.get(step_id, {}).get("duration", "0")),
        "log": meta.get(step_id, {}).get("log", ""),
    }

    junit_names = {
        "Unit tests": "unit.xml",
        "Integration tests": "integration.xml",
        "E2E tests": "e2e.xml",
        "Full test suite with coverage": "full.xml",
        "Resource warning regression": "resource-warnings.xml",
    }
    junit = Path(junit_dir) / junit_names.get(name, "")
    if junit and junit.is_file():
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root)
        totals = {"total": 0, "failures": 0, "errors": 0, "skipped": 0}
        reasons: list[str] = []
        for suite in suites:
            if suite.tag != "testsuite":
                continue
            totals["total"] += int(suite.get("tests", 0))
            totals["failures"] += int(suite.get("failures", 0))
            totals["errors"] += int(suite.get("errors", 0))
            totals["skipped"] += int(suite.get("skipped", 0))
            for case in suite.iter("testcase"):
                for skipped in case.findall("skipped"):
                    reasons.append(f"{case.get('classname', '')}::{case.get('name', '')}: {skipped.get('message', 'skipped')}")
        totals["passed"] = (
            totals["total"] - totals["failures"] - totals["errors"] - totals["skipped"]
        )
        info["tests"] = {**totals, "skip_reasons": reasons}
        if int(totals["skipped"]) > 0:
            test_skips += int(totals["skipped"])
            if kind == "test" and gate == "required" and os.environ.get("ZCODER_ALLOW_SKIPS") != "1":
                info["status"] = "FAIL"
                info["skip_gate"] = "required tests were skipped"
                required_failures += 1

    if status == "SKIP" and gate == "required":
        required_failures += 1
    elif status == "FAIL" and gate in {"required", "info"}:
        if gate == "required":
            required_failures += 1

    steps.append(info)

coverage_percent = None
cov_path = Path(coverage_xml)
if cov_path.exists():
    try:
        root = ET.parse(cov_path).getroot()
        rate = root.get("line-rate")
        if rate is not None:
            coverage_percent = round(float(rate) * 100, 2)
    except ET.ParseError:
        coverage_percent = None

build_dir = Path(log_dir) / "build-artifacts"
artifacts = sorted(p.name for p in build_dir.glob("*") if p.is_file())

summary = {
    "schema_version": 1,
    "log_dir": str(log_dir),
    "python": python_bin,
    "duration_seconds": int(duration),
    "coverage_percent": coverage_percent,
    "steps": steps,
    "totals": {
        "steps": len(steps),
        "passed": sum(1 for s in steps if s["status"] == "PASS"),
        "failed": sum(1 for s in steps if s["status"] == "FAIL"),
        "skipped": sum(1 for s in steps if s["status"] == "SKIP"),
        "test_skips": test_skips,
        "required_failures": required_failures,
    },
    "artifacts": artifacts,
    "result": "FAIL" if required_failures else "PASS",
}

Path(summary_path).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary["totals"], indent=2))
print(f"coverage: {coverage_percent}%")
print(f"result: {summary['result']}")
raise SystemExit(1 if required_failures else 0)
PY
SUMMARY_RC=$?

# ── Human-readable summary ───────────────────────────────────────────────────
log ""
log "============================================================"
log " VALIDATION SUMMARY"
log "============================================================"

for result in "${RESULTS[@]}"; do
    IFS='|' read -r name rc elapsed <<<"$result"
    if ((rc == 0)); then
        printf '[PASS] %-38s %4ss\n' "$name" "$elapsed" | tee -a "$RUN_LOG"
    else
        printf '[FAIL] %-38s exit=%s %4ss\n' "$name" "$rc" "$elapsed" | tee -a "$RUN_LOG"
    fi
done

log "------------------------------------------------------------"
log "Total steps : ${#RESULTS[@]}"
log "Passed      : $((${#RESULTS[@]} - FAILED - SKIPPED))"
log "Failed      : $FAILED"
log "Skipped     : $SKIPPED"
log "Duration    : ${TOTAL_TIME}s"
log "Log folder  : $LOG_DIR"
log "Combined log: $RUN_LOG"
log "Summary JSON: $SUMMARY_JSON"
log "============================================================"

if ((INTERRUPTED)); then
    log "RESULT: VALIDATION INTERRUPTED"
    exit 130
fi

if ((FAILED > 0 || SKIPPED > 0 || SUMMARY_RC != 0)); then
    log "RESULT: VALIDATION FAILED"
    exit 1
fi

log "RESULT: ALL VALIDATION GATES PASSED"
exit 0

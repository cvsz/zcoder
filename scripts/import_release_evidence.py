#!/usr/bin/env python3
"""Import hosted CI evidence for the current release-candidate commit.

The production release gate refuses to report a fully qualified release
until hosted validation evidence is bound to the exact candidate commit.
This importer collects that evidence:

1. Verifies version integrity across pyproject.toml, src/zcoder/main.py,
   and src/zcoder/__init__.py.
2. Fetches GitHub check runs for the exact HEAD SHA and requires every
   release-relevant check to be completed with a successful conclusion.
3. Writes a JSON evidence record under ``docs/evidence/`` bound to the
   candidate SHA.

Usage:
    python scripts/import_release_evidence.py            # current HEAD
    python scripts/import_release_evidence.py --sha <sha>
    python scripts/import_release_evidence.py --await    # tag builds: wait for
        the concurrent hosted suite on this SHA to finish green, then import

Exit codes: 0 = evidence imported, 1 = evidence missing or not qualified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence"
EVIDENCE_SCHEMA_VERSION = 1

# Hosted checks that must pass before a release candidate is qualified.
# Keep in sync with .github/workflows/*. "Production Release Gate Audit" is
# intentionally not listed: it is the gate-keeper itself on tag builds and
# cannot be required inside the evidence it produces.
REQUIRED_CHECKS: tuple[str, ...] = (
    "lint",
    "security",
    "test (3.10)",
    "test (3.11)",
    "test (3.12)",
    "docker-build",
    "Analyze Python Code Security",
    "Bandit and pip-audit",
    "Dependency Review & Vulnerability Check",
    "Gitleaks secret scan",
    "actionlint workflows",
    "Helm v3.21.3 Lint & Template Check",
    "Helm v4.2.3 Lint & Template Check",
    "Package Helm Chart & Checksums",
    "Validate TypeScript SDK & Types",
    "lock-check",
    "sync-locked",
)


class EvidenceImportError(Exception):
    """Raised when release evidence cannot be imported (fail-closed)."""


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidenceImportError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def resolve_candidate_sha(requested: str | None) -> str:
    """Resolve the release-candidate commit and require a clean checkout."""
    if requested:
        sha = _run_git("rev-parse", "--verify", f"{requested}^{{commit}}")
    else:
        sha = _run_git("rev-parse", "--verify", "HEAD")
    head = _run_git("rev-parse", "HEAD")
    if requested is None and sha != head:
        raise EvidenceImportError("candidate SHA does not match HEAD")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if dirty.stdout.strip():
        raise EvidenceImportError("working tree is dirty — commit or stash before importing evidence")
    return sha


def verify_version_integrity() -> dict[str, str]:
    """Version must be identical across the three canonical sources."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    main = (REPO_ROOT / "src" / "zcoder" / "main.py").read_text(encoding="utf-8")
    init = (REPO_ROOT / "src" / "zcoder" / "__init__.py").read_text(encoding="utf-8")

    py_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    main_match = re.search(r'^VERSION\s*=\s*"([^"]+)"', main, re.MULTILINE)
    init_match = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.MULTILINE)
    if not (py_match and main_match and init_match):
        raise EvidenceImportError("version constants missing from canonical sources")
    versions = {
        "pyproject": py_match.group(1),
        "main": main_match.group(1),
        "init": init_match.group(1),
    }
    if len(set(versions.values())) != 1:
        raise EvidenceImportError(f"version mismatch across sources: {versions}")
    return {**versions, "version": versions["pyproject"]}


def verify_release_tag(tag: str) -> str:
    """Require a valid SemVer tag whose version matches the checked-out source."""
    semver = (
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
        r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
        r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    )
    if not re.fullmatch(semver, tag):
        raise EvidenceImportError(f"invalid release tag: {tag}")
    version = verify_version_integrity()["version"]
    if tag != f"v{version}":
        raise EvidenceImportError(f"release tag {tag} does not match source version v{version}")
    return version


def fetch_check_runs(sha: str) -> list[dict[str, Any]]:
    """Fetch completed GitHub check runs bound to the candidate SHA."""
    repo = os.environ.get("GITHUB_REPOSITORY") or _repo_slug()
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/commits/{sha}/check-runs?filter=latest&per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidenceImportError(
            f"GitHub check-run evidence unavailable: {(result.stderr or result.stdout).strip()[:300]}"
        )
    try:
        pages = json.loads(result.stdout)
        if not isinstance(pages, list):
            raise ValueError("evidence is not a list of pages")
        runs = [run for page in pages for run in page.get("check_runs", [])]
    except (json.JSONDecodeError, AttributeError) as exc:
        raise EvidenceImportError(f"invalid check-run evidence payload: {exc}") from exc
    for run in runs:
        if not run.get("name") or run.get("head_sha") != sha:
            raise EvidenceImportError("check-run evidence not bound to candidate SHA")
    return runs


def _repo_slug() -> str:
    url = _run_git("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/](?P<slug>.+?)(?:\.git)?$", url)
    if not match:
        raise EvidenceImportError("cannot derive repository slug from origin URL")
    return match.group("slug")


def required_check_names(excluded: frozenset[str] | set[str]) -> tuple[str, ...]:
    """Effective required set after caller-requested exclusions."""
    return tuple(name for name in REQUIRED_CHECKS if name not in excluded)


def evaluate_check_runs(
    runs: list[dict[str, Any]],
    excluded: frozenset[str] | set[str] = frozenset(),
) -> dict[str, dict[str, str]]:
    """Pick the most authoritative completed run per required check name."""
    required = required_check_names(excluded)
    latest = _latest_by_name(runs, required)

    missing = [name for name in required if name not in latest]
    failing: list[tuple[str, str]] = []
    for name in required:
        run = latest.get(name)
        if run is None:
            continue
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status != "completed":
            failing.append((name, f"status={status}"))
        elif conclusion != "success":
            failing.append((name, f"conclusion={conclusion}"))

    if missing:
        raise EvidenceImportError(f"missing hosted checks: {', '.join(missing)}")
    if failing:
        detail = ", ".join(f"{name} ({reason})" for name, reason in failing)
        raise EvidenceImportError(f"failing hosted checks: {detail}")

    return {
        name: {
            "id": str(latest[name].get("id")),
            "conclusion": latest[name].get("conclusion") or "",
            "html_url": latest[name].get("html_url") or "",
        }
        for name in required
    }


def await_required_checks(
    sha: str,
    excluded: frozenset[str] | set[str] = frozenset(),
    timeout_seconds: float = 1800.0,
    poll_seconds: float = 20.0,
) -> None:
    """Block until every required hosted check on the candidate SHA is green.

    Used inside a tag build where this very qualification starts concurrent
    check runs bound to the same SHA. Any check that completes with a
    non-success conclusion aborts immediately; the loop fails closed when the
    deadline expires. Transient evidence-fetch failures are tolerated up to a
    short consecutive-error budget before giving up.
    """
    required = required_check_names(excluded)
    deadline = time.monotonic() + timeout_seconds
    consecutive_errors = 0
    while True:
        try:
            latest = _latest_by_name(fetch_check_runs(sha), required)
            consecutive_errors = 0
        except EvidenceImportError as exc:
            consecutive_errors += 1
            if consecutive_errors > 5:
                raise EvidenceImportError(
                    f"evidence unavailable from GitHub after repeated attempts: {exc}"
                ) from exc
            latest = {}

        missing = [name for name in required if name not in latest]
        pending = [name for name in required if name in latest and latest[name].get("status") != "completed"]
        failed = [
            (name, latest[name].get("conclusion"))
            for name in required
            if name in latest
            and latest[name].get("status") == "completed"
            and latest[name].get("conclusion") != "success"
        ]
        if failed:
            detail = ", ".join(f"{name} (conclusion={conclusion})" for name, conclusion in failed)
            raise EvidenceImportError(f"failing hosted checks: {detail}")
        if not missing and not pending:
            return
        if time.monotonic() > deadline:
            waiting = ", ".join([*missing, *pending])
            raise EvidenceImportError(
                f"timed out after {timeout_seconds / 60:.0f} min waiting for hosted checks: {waiting}"
            )
        time.sleep(poll_seconds)


def _latest_by_name(runs: list[dict[str, Any]], required: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Fold the check-run list down to the newest run per required name."""
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("name") or ""
        if name not in required:
            continue
        current = latest.get(name)
        if current is None or int(run.get("id", 0)) > int(current.get("id", 0)):
            latest[name] = run
    return latest


def build_evidence(sha: str, checks: dict[str, dict[str, str]]) -> dict[str, Any]:
    versions = verify_version_integrity()
    return {
        "schema": EVIDENCE_SCHEMA_VERSION,
        "imported_at": time.time(),
        "sha": sha,
        "version": versions["version"],
        "version_sources": versions,
        "checks": checks,
    }


def write_evidence(evidence: dict[str, Any], out_path: Path | None) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = out_path or (EVIDENCE_DIR / f"release-evidence-{evidence['sha'][:8]}.json")
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", help="candidate commit SHA (defaults to HEAD)")
    parser.add_argument("--release-tag", help="validate a SemVer tag against the source version")
    parser.add_argument("--out", type=Path, help="write evidence to an explicit path")
    parser.add_argument(
        "--print", action="store_true", help="print the evidence record instead of writing it"
    )
    parser.add_argument(
        "--await",
        dest="await_checks",
        action="store_true",
        help="wait until hosted checks on the candidate SHA are green before importing "
        "(for tag builds that trigger the suite concurrently)",
    )
    parser.add_argument(
        "--exclude-check",
        action="append",
        default=[],
        metavar="NAME",
        help="skip a hosted check name from the required set (repeatable)",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=30.0,
        help="deadline for --await (default: 30)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=20.0,
        help="interval between evidence polls with --await (default: 20)",
    )
    args = parser.parse_args(argv)

    excluded = frozenset(args.exclude_check)
    unknown_exclusions = sorted(set(excluded) - set(REQUIRED_CHECKS))
    if unknown_exclusions:
        print(
            f"NOT QUALIFIED: --exclude-check names not in the required set: "
            f"{', '.join(unknown_exclusions)}",
            file=sys.stderr,
        )
        return 1

    try:
        if args.release_tag:
            verify_release_tag(args.release_tag)
        sha = resolve_candidate_sha(args.sha)
        if args.await_checks:
            await_required_checks(
                sha,
                excluded=excluded,
                timeout_seconds=args.timeout_minutes * 60.0,
                poll_seconds=args.poll_seconds,
            )
        runs = fetch_check_runs(sha)
        checks = evaluate_check_runs(runs, excluded=excluded)
        evidence = build_evidence(sha, checks)
    except EvidenceImportError as exc:
        print(f"NOT QUALIFIED: {exc}", file=sys.stderr)
        return 1

    if args.print:
        print(json.dumps(evidence, indent=2))
        return 0

    target = write_evidence(evidence, args.out)
    print(f"EVIDENCE IMPORTED: {target}")
    print(f"candidate {evidence['sha']} version {evidence['version']}: {len(checks)} hosted checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

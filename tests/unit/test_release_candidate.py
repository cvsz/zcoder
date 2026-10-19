"""Exercise release preflight against controlled local and hosted evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/release-candidate.mjs").resolve()
_NODE = shutil.which("node")
_REQUIRED_CHECKS = [
    "lint",
    "security",
    "test (3.10)",
    "test (3.11)",
    "test (3.12)",
    "docker-build",
    "Analyze Python Code Security",
    "Bandit and pip-audit",
    "Gitleaks secret scan",
    "actionlint workflows",
    "Helm v3.21.3 Lint & Template Check",
    "Helm v4.2.3 Lint & Template Check",
    "Package Helm Chart & Checksums",
    "Production Release Gate Audit",
    "Validate TypeScript SDK & Types",
    "lock-check",
    "sync-locked",
]


@pytest.fixture
def candidate(tmp_path):
    if not _NODE:
        pytest.skip("Node.js is required to exercise the release preflight")
    for relative in ("pyproject.toml", "src/zcoder/main.py", "src/zcoder/__init__.py"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(relative, target)
    for args in (
        ["init", "--quiet"],
        ["add", "."],
        [
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    for name in ("uv", "gh"):
        executable = bin_path / name
        executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "if sys.argv[0].endswith('/uv'): sys.exit(0)\n"
            "if sys.argv[1] == 'auth': sys.exit(int(os.environ.get('AUTH_STATUS', '0')))\n"
            "print(os.environ['CHECKS_JSON'])\n"
            "sys.exit(int(os.environ.get('API_STATUS', '0')))\n"
        )
        executable.chmod(0o755)
    checks = [
        {"name": name, "status": "completed", "conclusion": "success", "head_sha": sha, "id": index}
        for index, name in enumerate(_REQUIRED_CHECKS, 1)
    ]
    env = {
        **os.environ,
        "PATH": str(bin_path) + os.pathsep + os.environ["PATH"],
        "CHECKS_JSON": json.dumps([{"check_runs": checks}]),
    }

    def run(*args, updates=None, runs=None):
        command_env = {**env, **(updates or {})}
        if runs is not None:
            command_env["CHECKS_JSON"] = json.dumps([{"check_runs": runs}])
        return subprocess.run(
            [_NODE, str(_SCRIPT), "--json", *args],
            cwd=tmp_path,
            env=command_env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    return run, sha, checks, tmp_path


def test_default_sha_uses_head_when_json_is_selected(candidate):
    run, sha, _, _ = candidate
    result = run()
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sha"] == sha


@pytest.mark.parametrize("updates", [{"AUTH_STATUS": "1"}, {"API_STATUS": "1"}])
def test_hosted_evidence_unavailable_fails_closed(candidate, updates):
    run, sha, _, _ = candidate
    result = run("--sha", sha, updates=updates)
    assert result.returncode == 1
    assert not next(r for r in json.loads(result.stdout)["results"] if r["name"] == "hosted-checks")["ok"]


@pytest.mark.parametrize("mode", ["empty", "missing", "failed", "pending", "wrong-sha"])
def test_incomplete_hosted_evidence_cannot_pass(candidate, mode):
    run, sha, checks, _ = candidate
    if mode == "empty":
        checks = []
    elif mode == "missing":
        checks = checks[:-1]
    elif mode == "failed":
        checks[0]["conclusion"] = "failure"
    elif mode == "pending":
        checks[0]["status"] = "in_progress"
    else:
        checks[0]["head_sha"] = "0" * 40
    assert run("--sha", sha, runs=checks).returncode == 1


def test_all_required_successful_checks_pass(candidate):
    run, sha, _, _ = candidate
    assert run("--check", "--sha", sha).returncode == 0


def test_dirty_checkout_cannot_qualify_committed_sha(candidate):
    run, sha, _, root = candidate
    with (root / "pyproject.toml").open("a") as stream:
        stream.write("\n# uncommitted change\n")
    assert run("--sha", sha).returncode == 1


@pytest.mark.parametrize("args", [("--sha",), ("--sha", "bad;value"), ("--unknown",)])
def test_invalid_arguments_are_rejected(candidate, args):
    run, _, _, _ = candidate
    assert run(*args).returncode != 0

"""Release gate must stay fail-closed unless evidence is bound to the exact
candidate commit that the working tree is checked out at."""

import json
import subprocess

import pytest

from zcoder.services import release_gate as release_gate_module
from zcoder.services.release_gate import GateVerdict, ProductionReleaseGate


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def evidence_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate_module, "EVIDENCE_DIR", tmp_path)
    return tmp_path


def _valid_evidence(sha: str, checks: dict) -> dict:
    return {
        "schema": 1,
        "imported_at": 0.0,
        "sha": sha,
        "version": "1.41.0",
        "version_sources": {"pyproject": "1.41.0", "main": "1.41.0", "init": "1.41.0"},
        "checks": checks,
    }


def _required_check(name: str, conclusion: str = "success") -> dict:
    return {"id": "1", "conclusion": conclusion, "html_url": f"https://example.test/{name}"}


def _write_evidence(path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _gate(verdicts: set[GateVerdict] | None = None) -> ProductionReleaseGate:
    gate = ProductionReleaseGate()
    verdicts = verdicts or set()
    if GateVerdict.PASS in verdicts:
        assert gate.gates["FINAL"].verdict == GateVerdict.PASS
    if GateVerdict.UNKNOWN in verdicts:
        assert gate.gates["FINAL"].verdict == GateVerdict.UNKNOWN
    return gate


def test_gate_stays_unknown_without_evidence(evidence_dir):
    gate = ProductionReleaseGate()
    for name in ("VERSION_INTEGRITY", "TEST_ACCOUNTING", "PITR", "SECURITY", "FINAL"):
        assert gate.gates[name].verdict == GateVerdict.UNKNOWN


def test_gate_promotes_from_evidence_bound_to_head(evidence_dir):
    sha = _head_sha()
    checks = {
        name: _required_check(name)
        for name in (
            "lint",
            "test (3.10)",
            "test (3.11)",
            "test (3.12)",
            "security",
            "Analyze Python Code Security",
            "Bandit and pip-audit",
            "Dependency Review & Vulnerability Check",
            "Gitleaks secret scan",
            "docker-build",
            "Production Release Gate Audit",
            "Validate TypeScript SDK & Types",
            "lock-check",
            "sync-locked",
        )
    }
    record = _valid_evidence(sha, checks)
    _write_evidence(evidence_dir / f"release-evidence-{sha[:8]}.json", record)

    gate = ProductionReleaseGate()
    for name in (
        "VERSION_INTEGRITY",
        "TEST_ACCOUNTING",
        "PITR",
        "SECURITY",
        "FINAL",
    ):
        assert gate.gates[name].verdict == GateVerdict.PASS, name
        assert f"bound to release-candidate {sha[:12]}" in gate.gates[name].notes
    # The documented WAL-target limitation stays on the record after promotion.
    assert "external object storage target" in " ".join(gate.gates["PITR"].limitations)


def test_gate_ignores_stale_evidence_bound_to_another_sha(evidence_dir):
    stale = _valid_evidence(
        "0" * 40,
        {"lint": _required_check("lint")},
    )
    _write_evidence(evidence_dir / "release-evidence-00000000.json", stale)

    gate = ProductionReleaseGate()
    assert gate.gates["FINAL"].verdict == GateVerdict.UNKNOWN


def test_gate_rejects_evidence_with_failed_check(evidence_dir):
    sha = _head_sha()
    checks = {
        "lint": _required_check("lint", conclusion="failure"),
        "test (3.10)": _required_check("test (3.10)"),
        "test (3.11)": _required_check("test (3.11)"),
        "test (3.12)": _required_check("test (3.12)"),
        "security": _required_check("security"),
        "Analyze Python Code Security": _required_check("Analyze Python Code Security"),
        "Bandit and pip-audit": _required_check("Bandit and pip-audit"),
        "Dependency Review & Vulnerability Check": _required_check("Dependency Review & Vulnerability Check"),
        "Gitleaks secret scan": _required_check("Gitleaks secret scan"),
        "docker-build": _required_check("docker-build"),
        "Production Release Gate Audit": _required_check("Production Release Gate Audit"),
        "Validate TypeScript SDK & Types": _required_check("Validate TypeScript SDK & Types"),
        "lock-check": _required_check("lock-check"),
        "sync-locked": _required_check("sync-locked"),
    }
    record = _valid_evidence(sha, checks)
    _write_evidence(evidence_dir / f"release-evidence-{sha[:8]}.json", record)

    gate = ProductionReleaseGate()
    assert gate.gates["SECURITY"].verdict == GateVerdict.UNKNOWN


def test_gate_rejects_malformed_evidence(evidence_dir):
    sha = _head_sha()
    path = evidence_dir / f"release-evidence-{sha[:8]}.json"
    path.write_text("{not valid json", encoding="utf-8")
    gate = ProductionReleaseGate()
    assert gate.gates["FINAL"].verdict == GateVerdict.UNKNOWN

    # Wrong schema version or SHA binding is ignored as well.
    _write_evidence(path, _valid_evidence(sha, {"lint": _required_check("lint")}) | {"schema": 99})
    gate = ProductionReleaseGate()
    assert gate.gates["FINAL"].verdict == GateVerdict.UNKNOWN


def test_partial_evidence_leaves_dependent_gate_unknown(evidence_dir):
    sha = _head_sha()
    # Only the SECURITY-required checks are present; TEST_ACCOUNTING/FINAL
    # must stay UNKNOWN because their required checks are missing.
    checks = {
        "security": _required_check("security"),
        "Analyze Python Code Security": _required_check("Analyze Python Code Security"),
        "Bandit and pip-audit": _required_check("Bandit and pip-audit"),
        "Dependency Review & Vulnerability Check": _required_check("Dependency Review & Vulnerability Check"),
        "Gitleaks secret scan": _required_check("Gitleaks secret scan"),
    }
    record = _valid_evidence(sha, checks)
    _write_evidence(evidence_dir / f"release-evidence-{sha[:8]}.json", record)

    gate = ProductionReleaseGate()
    assert gate.gates["SECURITY"].verdict == GateVerdict.PASS
    assert gate.gates["TEST_ACCOUNTING"].verdict == GateVerdict.UNKNOWN
    assert gate.gates["FINAL"].verdict == GateVerdict.UNKNOWN


def test_importer_version_integrity_detects_mismatch(tmp_path, monkeypatch):
    from scripts import import_release_evidence as importer

    fake_root = tmp_path
    (fake_root / "pyproject.toml").write_text('version = "1.41.1"\n', encoding="utf-8")
    src = fake_root / "src" / "zcoder"
    src.mkdir(parents=True)
    (src / "main.py").write_text('VERSION = "1.41.0"\n', encoding="utf-8")
    (src / "__init__.py").write_text('__version__ = "1.41.0"\n', encoding="utf-8")

    monkeypatch.setattr(importer, "REPO_ROOT", fake_root)
    with pytest.raises(importer.EvidenceImportError, match="version mismatch"):
        importer.verify_version_integrity()


def test_importer_verify_version_integrity_passes(tmp_path, monkeypatch):
    from scripts import import_release_evidence as importer

    fake_root = tmp_path
    (fake_root / "pyproject.toml").write_text('version = "1.41.0"\n', encoding="utf-8")
    src = fake_root / "src" / "zcoder"
    src.mkdir(parents=True)
    (src / "main.py").write_text('VERSION = "1.41.0"\n', encoding="utf-8")
    (src / "__init__.py").write_text('__version__ = "1.41.0"\n', encoding="utf-8")

    monkeypatch.setattr(importer, "REPO_ROOT", fake_root)
    values = importer.verify_version_integrity()
    assert values["version"] == "1.41.0"
    assert len(set(values.values())) == 1


def test_default_evidence_dir_matches_importer_output():
    """The gate loader must read exactly where the importer writes.

    This binding is load-bearing: the anchor constant must resolve to the
    repository root at runtime (src/zcoder/services/release_gate.py ->
    <root>/docs/evidence), not to a nested src/docs directory that silently
    misses every imported record and keeps the gate fail-closed UNKNOWN.
    """
    importer = _gate_aware_importer()
    from pathlib import Path

    assert release_gate_module.EVIDENCE_DIR == importer.REPO_ROOT / "docs" / "evidence"
    # Class and module must observe the same directory (no stale copies).
    assert release_gate_module.ProductionReleaseGate._load_bound_evidence is not None
    assert Path(release_gate_module.__file__).resolve().parents[3] == importer.REPO_ROOT


# ---------------------------------------------------------------------------
# Await / exclusion semantics for tag-build qualification
# ---------------------------------------------------------------------------


def _gate_aware_importer():
    from scripts import import_release_evidence as importer

    return importer


def test_required_checks_exclude_the_gate_itself():
    """The gate-keeper job name must never be required inside its own evidence."""
    importer = _gate_aware_importer()
    assert "Production Release Gate Audit" not in importer.REQUIRED_CHECKS
    assert "Dependency Review & Vulnerability Check" in importer.REQUIRED_CHECKS

    from zcoder.services.release_gate import _PROMOTION_REQUIREMENTS

    for required in _PROMOTION_REQUIREMENTS.values():
        assert "Production Release Gate Audit" not in required
    assert "Dependency Review & Vulnerability Check" in _PROMOTION_REQUIREMENTS["SECURITY"]


def test_release_tag_must_be_semver_and_match_source(monkeypatch):
    importer = _gate_aware_importer()
    monkeypatch.setattr(
        importer,
        "verify_version_integrity",
        lambda: {"version": "1.2.3", "pyproject": "1.2.3", "main": "1.2.3", "init": "1.2.3"},
    )

    assert importer.verify_release_tag("v1.2.3") == "1.2.3"
    for invalid in ("vgarbage", "v1", "v1.2.4", "1.2.3", "v1.2.3-rc.1", "v01.2.3"):
        with pytest.raises(importer.EvidenceImportError):
            importer.verify_release_tag(invalid)

    monkeypatch.setattr(
        importer,
        "verify_version_integrity",
        lambda: {
            "version": "1.2.3-rc.1+build.5",
            "pyproject": "1.2.3-rc.1+build.5",
            "main": "1.2.3-rc.1+build.5",
            "init": "1.2.3-rc.1+build.5",
        },
    )
    assert importer.verify_release_tag("v1.2.3-rc.1+build.5") == "1.2.3-rc.1+build.5"


def test_evaluate_check_runs_excludes_requested_checks():
    importer = _gate_aware_importer()
    excluded = {"docker-build"}
    runs = [
        {"name": name, "id": 1, "status": "completed", "conclusion": "success"}
        for name in importer.required_check_names(excluded)
    ]
    checks = importer.evaluate_check_runs(runs, excluded=excluded)
    assert "docker-build" not in checks
    assert set(checks) == set(importer.required_check_names(excluded))


def test_await_required_checks_polls_until_green(monkeypatch):
    importer = _gate_aware_importer()
    required = importer.REQUIRED_CHECKS

    def make_runs(state: str, conclusion: str | None):
        return [
            {
                "name": name,
                "id": 1,
                "status": state,
                "conclusion": conclusion,
            }
            for name in required
        ]

    # First poll: everything still running. Second poll: all green.
    polls = [make_runs("in_progress", None), make_runs("completed", "success")]
    monkeypatch.setattr(importer, "fetch_check_runs", lambda sha: polls.pop(0))

    importer.await_required_checks(
        "a" * 40, timeout_seconds=30.0, poll_seconds=0.001
    )  # must return without raising


def test_await_required_checks_fails_fast_on_failure(monkeypatch):
    importer = _gate_aware_importer()
    required = importer.REQUIRED_CHECKS

    failing = [
        {"name": name, "id": 1, "status": "completed", "conclusion": "success"} for name in required[1:]
    ]
    failing.append({"name": required[0], "id": 2, "status": "completed", "conclusion": "failure"})
    monkeypatch.setattr(importer, "fetch_check_runs", lambda sha: failing)

    with pytest.raises(importer.EvidenceImportError, match="failing hosted checks"):
        importer.await_required_checks("b" * 40, timeout_seconds=30.0, poll_seconds=0.001)


def test_await_required_checks_times_out_fail_closed(monkeypatch):
    importer = _gate_aware_importer()
    monkeypatch.setattr(importer, "fetch_check_runs", lambda sha: [])

    with pytest.raises(importer.EvidenceImportError, match="timed out"):
        importer.await_required_checks("c" * 40, timeout_seconds=0.0, poll_seconds=0.001)

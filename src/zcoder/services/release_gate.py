"""Current production release-gate facade.

The v1.40 gate catalog is preserved in ``_release_gate_legacy`` so historical
control/evidence definitions remain reviewable.  This facade normalizes paths
after the src-layout migration and refuses to report a fully validated release
until hosted validation evidence bound to the exact candidate commit has been
imported (see ``scripts/import_release_evidence.py``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ._release_gate_legacy import (  # re-export stable public types
    EvidenceLevel,
    GateResult,
    GateVerdict,
)
from ._release_gate_legacy import (
    ProductionReleaseGate as _LegacyProductionReleaseGate,
)

_PATH_REWRITES = {
    "pytest tests/test_source_of_truth_conformance.py": "pytest tests/integration/test_source_of_truth_conformance.py",
    "pytest tests/test_upgrade11_evidence_suite.py": "pytest tests/e2e/upgrade_suites/test_upgrade11_evidence_suite.py",
    "pytest tests/test_upgrade12_product_suite.py": "pytest tests/e2e/upgrade_suites/test_upgrade12_product_suite.py",
    "pytest tests/test_upgrade13_nocost_suite.py": "pytest tests/e2e/upgrade_suites/test_upgrade13_nocost_suite.py",
    "pytest tests/test_security.py tests/test_auth_oidc.py": "pytest tests/unit/test_security.py tests/integration/test_auth_oidc.py",
    "docs/ENCRYPTION.md + SecretRef pattern": "docs/security/ENCRYPTION.md + SecretRef pattern",
    "docs/RETENTION.md + tenant-scoped deletion": "docs/compliance/RETENTION.md + tenant-scoped deletion",
    "docs/UPGRADE-13.md, NO-COST-MATRIX.md, LOCAL-FREE.md, etc.": "docs/README.md (documentation taxonomy index)",
    "residency_models.py (6 distinct regional dimensions)": "src/zcoder/domain/models/residency.py (6 distinct regional dimensions)",
    "no_cost_platform.py offline local mode": "src/zcoder/enterprise/no_cost_platform.py offline local mode",
    "compliance_evidence.py ComplianceCatalog": "src/zcoder/services/compliance_evidence.py ComplianceCatalog",
    "sdk_client.ZCoderClient": "zcoder.interfaces.sdk.client.ZCoderClient",
}

# Evidence produced by scripts/import_release_evidence.py; one record per
# candidate SHA, committed under docs/evidence/. Anchor arithmetic: from
# src/zcoder/services/release_gate.py the repository root is parents[3].
EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "evidence"
PITR_EVIDENCE_SCHEMA_VERSION = 1

# Hosted checks each promoted gate depends on. PITR relies on the hosted
# test matrix, which executes the backup/restore drill coverage; the
# documented WAL-target limitation stays on the record after promotion.
# "Production Release Gate Audit" is not referenced here: it is the
# gate-keeper itself on tag builds, not evidence the gate can consume.
_PROMOTION_REQUIREMENTS = {
    "VERSION_INTEGRITY": ["lint"],
    "TEST_ACCOUNTING": ["test (3.12)", "test (3.13)"],
    "SECURITY": [
        "security",
        "Analyze Python Code Security",
        "Bandit and pip-audit",
        "Dependency Review & Vulnerability Check",
        "Gitleaks secret scan",
    ],
    "PITR": ["test (3.12)", "test (3.13)"],
    "FINAL": [
        "docker-build",
        "Validate TypeScript SDK & Types",
        "lock-check",
        "sync-locked",
    ],
}

_POST_MIGRATION_VALIDATION_GATES = (
    "VERSION_INTEGRITY",
    "TEST_ACCOUNTING",
    "PITR",
    "SECURITY",
    "FINAL",
)


class ProductionReleaseGate(_LegacyProductionReleaseGate):
    """Release gate with post-migration paths and evidence truthfulness."""

    def __init__(self):
        super().__init__()
        self._normalize_paths()
        self._apply_candidate_evidence()

    def _normalize_paths(self) -> None:
        for gate in self.gates.values():
            for old, new in _PATH_REWRITES.items():
                gate.command = gate.command.replace(old, new)

    @staticmethod
    def _candidate_sha() -> str:
        """The exact commit this catalog instance is bound to."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def _apply_candidate_evidence(self) -> None:
        """Promote pending gates only from evidence bound to this exact SHA.

        Any other state (missing evidence, stale SHA binding, failed or
        incomplete hosted checks) leaves the gates UNKNOWN so ``--check``
        stays fail-closed.
        """
        sha = self._candidate_sha()
        if not sha or self._working_tree_dirty():
            self._mark_validation_pending()
            return

        record = self._load_bound_evidence(sha)
        if record is None:
            self._mark_validation_pending()
            return

        self._promote_from_evidence(record, sha)

    @staticmethod
    def _working_tree_dirty() -> bool:
        """Do not qualify a commit while uncommitted source can change its meaning."""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode != 0 or bool(result.stdout.strip())

    @staticmethod
    def _load_pitr_evidence(sha: str) -> dict | None:
        """Load production WAL/restore evidence bound to the exact candidate."""
        configured = os.environ.get("ZCODER_PITR_EVIDENCE_JSON")
        try:
            if configured:
                data = json.loads(configured)
            else:
                path = EVIDENCE_DIR / f"pitr-qualification-{sha[:8]}.json"
                data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        required = (
            data.get("schema") == PITR_EVIDENCE_SCHEMA_VERSION,
            data.get("sha") == sha,
            data.get("wal_archive_verified") is True,
            data.get("restore_drill_passed") is True,
            _pitr_evidence_is_fresh(data),
            isinstance(data.get("evidence_ref"), str)
            and bool(re.fullmatch(r"[A-Za-z0-9._:/#-]{1,240}", data["evidence_ref"])),
            isinstance(data.get("evidence_sha256"), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", data["evidence_sha256"])),
        )
        return data if all(required) else None

    @staticmethod
    def _load_bound_evidence(sha: str) -> dict | None:
        """Load and validate evidence for the candidate SHA, else None.

        Validation is strict: well-formed schema, matching SHA binding, and
        at least one recorded check. Anything else is treated as absent.
        """
        path = EVIDENCE_DIR / f"release-evidence-{sha[:8]}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        if data.get("schema") != 1:
            return None
        if data.get("sha") != sha:
            return None
        checks = data.get("checks")
        if not isinstance(checks, dict) or not checks:
            return None
        if any(
            not isinstance(value, dict) or value.get("conclusion") != "success" for value in checks.values()
        ):
            return None
        return data

    def _promote_from_evidence(self, record: dict, sha: str) -> None:
        evidence_level = EvidenceLevel.E4_REAL_EXTERNAL_TESTED
        bound = record.get("checks") or {}
        for name, required_checks in _PROMOTION_REQUIREMENTS.items():
            gate = self.gates.get(name)
            if gate is None:
                continue
            missing = [check for check in required_checks if check not in bound]
            if missing:
                self._mark_gate_pending(gate, name)
                continue
            gate.verdict = GateVerdict.PASS
            gate.evidence_level = evidence_level
            gate.notes = (
                f"Hosted CI validation bound to release-candidate {sha[:12]}: "
                f"{', '.join(required_checks)} all green."
            )
            gate.limitations = [
                lim for lim in gate.limitations if "no imported validation evidence" not in lim
            ]

        pitr = self.gates.get("PITR")
        if pitr is not None:
            operational = self._load_pitr_evidence(sha)
            if operational is None:
                self._mark_gate_pending(pitr, "PITR")
                pitr.limitations.append(
                    "Requires exact-candidate production WAL archive verification and a successful restore drill."
                )
            else:
                pitr.verdict = GateVerdict.PASS
                pitr.evidence_level = evidence_level
                pitr.notes = (
                    f"Hosted test matrix and production WAL/restore evidence bound to "
                    f"release-candidate {sha[:12]} ({operational['evidence_ref']})."
                )
                pitr.limitations = [
                    lim
                    for lim in pitr.limitations
                    if "no imported validation evidence" not in lim
                    and "Requires exact-candidate production" not in lim
                ]

    @staticmethod
    def _mark_gate_pending(gate: GateResult, name: str) -> None:
        gate.verdict = GateVerdict.UNKNOWN
        gate.evidence_level = EvidenceLevel.E0_CODE_EXISTS
        note = (
            "This catalog has no imported validation evidence bound to the current "
            "release-candidate commit. Hosted checks and operational qualification "
            "must be verified for that exact candidate before release approval."
        )
        gate.notes = note
        if note not in gate.limitations:
            gate.limitations.append(note)

    def _mark_validation_pending(self) -> None:
        for name in _POST_MIGRATION_VALIDATION_GATES:
            gate = self.gates.get(name)
            if gate is None:
                continue
            self._mark_gate_pending(gate, name)


__all__ = [
    "EVIDENCE_DIR",
    "EvidenceLevel",
    "GateResult",
    "GateVerdict",
    "ProductionReleaseGate",
]


def _pitr_evidence_is_fresh(data: dict) -> bool:
    tested_at = data.get("tested_at")
    if not isinstance(tested_at, str) or not tested_at.endswith("Z"):
        return False
    try:
        timestamp = datetime.fromisoformat(tested_at[:-1] + "+00:00")
    except ValueError:
        return False
    now = datetime.now(UTC)
    return now - timedelta(days=30) <= timestamp <= now


if __name__ == "__main__":
    ProductionReleaseGate().print_report()

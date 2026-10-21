"""Current production release-gate facade.

The v1.40 gate catalog is preserved in ``_release_gate_legacy`` so historical
control/evidence definitions remain reviewable.  This facade normalizes paths
after the src-layout migration and refuses to report a fully validated release
until hosted validation evidence bound to the exact candidate commit has been
imported (see ``scripts/import_release_evidence.py``).
"""

from __future__ import annotations

import json
import subprocess
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

# Hosted checks each promoted gate depends on. PITR relies on the hosted
# test matrix, which executes the backup/restore drill coverage; the
# documented WAL-target limitation stays on the record after promotion.
# "Production Release Gate Audit" is not referenced here: it is the
# gate-keeper itself on tag builds, not evidence the gate can consume.
_PROMOTION_REQUIREMENTS = {
    "VERSION_INTEGRITY": ["lint"],
    "TEST_ACCOUNTING": ["test (3.10)", "test (3.11)", "test (3.12)"],
    "SECURITY": [
        "security",
        "Analyze Python Code Security",
        "Bandit and pip-audit",
        "Dependency Review & Vulnerability Check",
        "Gitleaks secret scan",
    ],
    "PITR": ["test (3.10)", "test (3.11)", "test (3.12)"],
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
        if not sha:
            self._mark_validation_pending()
            return

        record = self._load_bound_evidence(sha)
        if record is None:
            self._mark_validation_pending()
            return

        self._promote_from_evidence(record, sha)

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


if __name__ == "__main__":
    ProductionReleaseGate().print_report()

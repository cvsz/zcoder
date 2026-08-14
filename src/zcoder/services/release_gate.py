"""Current production release-gate facade.

The v1.40 gate catalog is preserved in ``_release_gate_legacy`` so historical
control/evidence definitions remain reviewable.  This facade normalizes paths
after the src-layout migration and refuses to report a fully validated release
until the post-migration validation suite has actually run.
"""

from __future__ import annotations

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

_POST_MIGRATION_VALIDATION_GATES = (
    "VERSION_INTEGRITY",
    "TEST_ACCOUNTING",
    "SECURITY",
    "FINAL",
)


class ProductionReleaseGate(_LegacyProductionReleaseGate):
    """Release gate with post-migration paths and evidence truthfulness."""

    def __init__(self):
        super().__init__()
        self._normalize_paths()
        self._mark_validation_pending()

    def _normalize_paths(self) -> None:
        for gate in self.gates.values():
            for old, new in _PATH_REWRITES.items():
                gate.command = gate.command.replace(old, new)

    def _mark_validation_pending(self) -> None:
        note = (
            "Post-src-layout hosted validation has not executed because GitHub "
            "Actions is rejecting jobs before runner startup due to the account "
            "billing/Actions spending state. Previous evidence predates the migration."
        )
        for name in _POST_MIGRATION_VALIDATION_GATES:
            gate = self.gates.get(name)
            if gate is None:
                continue
            gate.verdict = GateVerdict.UNKNOWN
            gate.evidence_level = EvidenceLevel.E0_CODE_EXISTS
            gate.notes = note
            if note not in gate.limitations:
                gate.limitations.append(note)


__all__ = [
    "EvidenceLevel",
    "GateResult",
    "GateVerdict",
    "ProductionReleaseGate",
]


if __name__ == "__main__":
    ProductionReleaseGate().print_report()

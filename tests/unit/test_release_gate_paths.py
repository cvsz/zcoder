"""Post-migration release-gate path and evidence-state checks."""
from release_gate import GateVerdict, ProductionReleaseGate


def test_release_gate_uses_current_test_taxonomy():
    gate = ProductionReleaseGate()
    assert "tests/integration/test_source_of_truth_conformance.py" in gate.gates["SOURCE_TRUTH"].command
    assert "tests/e2e/upgrade_suites/test_upgrade11_evidence_suite.py" in gate.gates["POSTGRES_REQUIRED"].command
    assert "tests/unit/test_security.py" in gate.gates["SECURITY"].command


def test_release_gate_uses_current_docs_taxonomy():
    gate = ProductionReleaseGate()
    assert "docs/security/ENCRYPTION.md" in gate.gates["ENCRYPTION_BOUNDARY"].command
    assert "docs/compliance/RETENTION.md" in gate.gates["RETENTION"].command


def test_release_gate_does_not_claim_unexecuted_post_migration_validation():
    gate = ProductionReleaseGate()
    assert gate.gates["TEST_ACCOUNTING"].verdict is GateVerdict.UNKNOWN
    assert gate.gates["SECURITY"].verdict is GateVerdict.UNKNOWN
    assert gate.gates["FINAL"].verdict is GateVerdict.UNKNOWN

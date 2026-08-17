from pathlib import Path


_REMOVED_MIGRATION_PATHS = (
    ".github/workflows/apply-repository-hardening.yml",
    "scripts/apply_repository_hardening.py",
    "scripts/run_repository_hardening.py",
)


def test_temporary_repository_hardening_scaffold_stays_removed():
    root = Path(__file__).resolve().parents[2]

    for relative_path in _REMOVED_MIGRATION_PATHS:
        assert not (root / relative_path).exists(), relative_path

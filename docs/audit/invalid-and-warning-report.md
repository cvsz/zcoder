# ZCoder — Invalid and Warning Report

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

## Invalid Configurations Found and Fixed

| ID | File | Issue | Fix |
|----|------|-------|-----|
| ZC-003 | `build.sh:3` | ShellCheck SC1007: `CDPATH= cd` (space after `=`) | Changed to `CDPATH='' cd` |
| ZC-003 | `setup.sh:3` | ShellCheck SC1007: `CDPATH= cd` (space after `=`) | Changed to `CDPATH='' cd` |

## Warnings

| ID | Tool | File | Warning | Disposition |
|----|------|------|---------|-------------|
| ZC-003 | ShellCheck | `build.sh` | SC1007: Remove space after `=` | Fixed |
| ZC-003 | ShellCheck | `setup.sh` | SC1007: Remove space after `=` | Fixed |
| — | Ruff format | 19 files | Files would be reformatted | Not a CI gate; P3 maintainability. No source file fails `ruff check` or `black --check` |
| — | MyPy | 195 source files | `annotation-unchecked` notes for untyped function bodies | Not errors; mypy passes with `--ignore-missing-imports` |

## Items Reviewed and Determined Not Invalid

The following were reviewed and determined to be intentional, not defects:

- `pass` statements in Protocol/interface classes (engineering_store, portfolio_store, TenantJobStore)
- `raise NotImplementedError` in `BillingProvider` abstract base class
- `NotImplementedError` in `product.py` (billing interface stubs)
- Duplicate `__all__` removal in `model_registry.py` (first block preserved, identical to main)
- 28 skipped tests without PostgreSQL (expected; integration tests require PostgreSQL)

## No Warnings Hidden

No warnings were globally suppressed. All warnings are either fixed or documented with justification.

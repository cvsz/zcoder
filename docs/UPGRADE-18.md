# UPGRADE-18: Local AI Quality Engineering & Continuous Optimization

## 1. Overview
Upgrade-18 establishes project-specific quality benchmarking, objective correctness scoring, model promotion/quarantine lifecycles, and adaptive quality-first routing.

## 2. Quality Engineering Subsystems
- **Quality Engineering Service (`QualityEngineeringService`)**: Manages project-specific benchmarks, objective test evaluations, and baseline comparison.
- **Model Promotion & Quarantine (`ModelQualityState`)**: Transitions models between `PREFERRED`, `CANDIDATE`, `DEGRADED`, and `QUARANTINED`. Security test failures enforce an immediate hard-gate quarantine.
- **Adaptive Quality-First Router**: Selects models meeting project quality criteria and test passing floors over raw token generation speed.

## 3. Verification
- `pytest tests/test_upgrade18_quality_engineering_suite.py`: 3 passed
- Complete regression suite: 735 passed, 2 optional skipped, 0 failed.

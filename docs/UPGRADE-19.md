# UPGRADE-19: Autonomous Project Bootstrap & Developer Experience

## 1. Overview
Upgrade-19 provides one-command repository onboarding (`zcoder init`), automated stack detection, validation discovery, AGENTS.md generation, readiness scoring, and dry-run execution plans.

## 2. Core Subsystems
- **Stack Detector (`ProjectBootstrapService.detect_stack`)**: Discovers languages (Python, TypeScript, Go, etc.), package managers (pip, npm), and testing frameworks (pytest, vitest).
- **AGENTS.md Generator**: Produces project-tailored autonomous coding guidelines and validation commands.
- **Bootstrap Planner & Execution**: Dry-run safe planning with automatic RAG index ingestion and project readiness reports.

## 3. Verification
- `pytest tests/test_upgrade19_project_bootstrap_suite.py`: 3 passed
- Complete regression suite: 738 passed, 2 optional skipped, 0 failed.

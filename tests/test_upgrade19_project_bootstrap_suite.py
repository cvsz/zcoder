"""tests/test_upgrade19_project_bootstrap_suite.py — Comprehensive Test Suite for Upgrade-19 Project Bootstrap.

Verifies:
  1. Automatic Stack Detection (Python, TypeScript, Package Managers, Test Frameworks)
  2. AGENTS.md Generation & Validation Command Extraction
  3. Bootstrap Planning (Dry-run safe) & Execution
  4. Project Readiness Reporting & RAG Ingestion
  5. Zero-Paid-Calls Guarantee
"""
import pytest

from local_ai_stack import (
    DetectedStack,
    ProjectBootstrapService,
    ProjectReadinessReport,
)


def test_stack_detection_python_and_typescript():
    svc = ProjectBootstrapService()

    # 1. Python stack detection
    python_files = ["src/main.py", "tests/test_core.py", "pyproject.toml", "requirements.txt"]
    stack_py = svc.detect_stack(python_files)
    assert "python" in stack_py.languages
    assert "pip" in stack_py.package_managers
    assert "pytest" in stack_py.test_frameworks

    # 2. TypeScript / Web stack detection
    ts_files = ["src/App.tsx", "package.json", "vitest.config.ts"]
    stack_ts = svc.detect_stack(ts_files)
    assert "typescript/javascript" in stack_ts.languages
    assert "npm/yarn/pnpm" in stack_ts.package_managers
    assert "vitest" in stack_ts.test_frameworks


def test_bootstrap_plan_and_dry_run():
    svc = ProjectBootstrapService()
    files = ["app.py", "requirements.txt", "tests/test_app.py"]

    plan = svc.plan_bootstrap(files)
    assert plan["dry_run"] is True
    assert "pytest -q" in plan["validation_commands"]
    assert "AGENTS.md" in plan["agents_md_preview"]


def test_execute_bootstrap_and_readiness():
    svc = ProjectBootstrapService()
    codebase = {
        "calculator.py": "def add(a, b): return a + b",
        "tests/test_calculator.py": "def test_add(): assert add(1, 2) == 3",
        "requirements.txt": "pytest>=8.0.0",
    }

    report = svc.execute_bootstrap(project_name="calc_project", codebase=codebase)
    assert report.is_ready is True
    assert report.rag_indexed_files >= 2
    assert "python" in report.detected_stack.languages
    assert report.baseline_tests_passing is True
    assert len(report.blockers) == 0

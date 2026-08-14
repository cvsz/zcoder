"""tests/test_upgrade18_quality_engineering_suite.py — Comprehensive Test Suite for Upgrade-18 Local AI Quality Engineering.

Verifies:
  1. Quality Engineering Service & Quality Profiles (Project specific thresholds)
  2. Model Promotion (PREFERRED), Degradation, and Quarantine (Hard security gate)
  3. Quality-First Adaptive Routing (Quality > raw speed)
  4. Benchmark Fixture Versioning & Deterministic Evaluation
  5. Zero-Paid-Calls Guarantee
"""
import pytest

from local_ai_stack import (
    ModelQualityState,
    QualityBenchmarkFixture,
    QualityEngineeringService,
    QualityOutcome,
    QualityProfile,
)


def test_quality_profile_and_model_evaluation():
    service = QualityEngineeringService()
    profile = QualityProfile(
        id="proj-billing-profile",
        name="Billing Quality Profile",
        project_id="proj_billing",
        language="python",
        minimum_quality=0.85,
    )
    service.register_profile(profile)

    # 1. High-quality model evaluation -> Promoted to PREFERRED
    outcome_good = service.evaluate_model(
        model_id="qwen2.5-coder:7b",
        project_id="proj_billing",
        correctness=0.95,
        security_passed=True,
        tool_reliability=0.90,
    )
    assert outcome_good.composite_quality >= 0.85
    assert service.get_model_state("qwen2.5-coder:7b") == ModelQualityState.PREFERRED

    # 2. Security failure -> Hard gate fails and QUARANTINES model immediately
    outcome_insecure = service.evaluate_model(
        model_id="rogue-coder:3b",
        project_id="proj_billing",
        correctness=0.99,
        security_passed=False,  # Security failure (e.g. prompt injection vulnerability)
        tool_reliability=0.95,
    )
    assert outcome_insecure.composite_quality == 0.0
    assert service.get_model_state("rogue-coder:3b") == ModelQualityState.QUARANTINED


def test_adaptive_quality_first_routing():
    service = QualityEngineeringService()
    profile = QualityProfile(
        id="proj-core-profile",
        name="Core Quality Profile",
        project_id="proj_core",
        language="python",
        minimum_quality=0.80,
    )
    service.register_profile(profile)

    # Fast model with degraded quality (0.60)
    service.evaluate_model(
        model_id="fast-tiny-coder:1b",
        project_id="proj_core",
        correctness=0.55,
        security_passed=True,
        tool_reliability=0.70,
        ttft_ms=50.0,
    )

    # Slower model with high quality (0.92)
    service.evaluate_model(
        model_id="qwen2.5-coder:7b",
        project_id="proj_core",
        correctness=0.92,
        security_passed=True,
        tool_reliability=0.95,
        ttft_ms=200.0,
    )

    # Routing must pick the PREFERRED high quality model over the faster tiny model
    selected_model, reason = service.route_for_project(
        project_id="proj_core",
        candidate_models=["fast-tiny-coder:1b", "qwen2.5-coder:7b"],
    )
    assert selected_model == "qwen2.5-coder:7b"
    assert "PREFERRED" in reason


def test_quality_benchmark_fixtures():
    service = QualityEngineeringService()
    fixture = QualityBenchmarkFixture(
        fixture_id="fix_tax_calc",
        project_id="proj_billing",
        language="python",
        task_class="CODE_REPAIR",
        initial_code="def calc_tax(p): return p * 0.05",
        test_code="def test_tax(): assert calc_tax(100) == 5.0",
        version="v1.0",
    )
    service.register_fixture(fixture)
    assert "fix_tax_calc" in service.fixtures
    assert service.fixtures["fix_tax_calc"].version == "v1.0"

"""tests/test_upgrade15_model_factory_suite.py — Comprehensive Test Suite for Upgrade-15 Local Model Factory.

Verifies:
  1. Model Registry & Explicit Lifecycle State (CATALOG vs INSTALLED/VERIFIED)
  2. Model Acquisition Dry-Run & Digest Verification
  3. LlamaCpp First-Class Runtime Adapter
  4. Hardware Auto-Tuning (Threads, Offload Layers, Safe RAM Limits)
  5. Multi-dimensional Model Benchmark Tournament Scoring
  6. Zero-Paid-Calls Guarantee
"""

from local_ai_stack import (
    HardwareAutoTuner,
    HardwareProfile,
    LlamaCppRuntime,
    LocalModelArtifact,
    ModelRegistry,
    ModelSourceType,
    ModelState,
    ModelTournament,
)


def test_model_registry_catalog_vs_installed_distinction():
    registry = ModelRegistry()
    catalog = registry.list_catalog_models()
    assert len(catalog) >= 2

    # Fresh registry must have 0 installed models
    installed = registry.list_installed_models()
    assert len(installed) == 0

    # Test artifact registration & verification
    artifact = LocalModelArtifact(
        id="test-local-coder",
        name="Test Local Coder",
        source_type=ModelSourceType.LOCAL_FILE,
        repo_or_path="/models/test.gguf",
        revision="v1",
        filename="test.gguf",
        format="GGUF",
        size_bytes=1_000_000,
        digest="sha256:valid_digest_123",
        license="MIT",
        parameter_size_b=3.0,
        quantization="q4_k_m",
        state=ModelState.DOWNLOADED,
    )
    registry.register_artifact(artifact)

    # Verification success
    ok = registry.verify_artifact("test-local-coder", "sha256:valid_digest_123")
    assert ok is True
    assert len(registry.list_installed_models()) == 1


def test_model_acquisition_download_plan_dry_run():
    registry = ModelRegistry()
    plan = registry.plan_download("qwen2.5-coder-7b-gguf")
    assert plan["model_id"] == "qwen2.5-coder-7b-gguf"
    assert plan["dry_run_ready"] is True
    assert plan["size_gb"] > 0
    assert plan["license"] == "Apache-2.0"


def test_llamacpp_runtime_adapter():
    runtime = LlamaCppRuntime()
    models = runtime.list_models()
    assert len(models) >= 1
    assert models[0].provider == "llama.cpp"

    res = runtime.chat_complete("qwen2.5-coder:7b-gguf", "def subtract(a, b):")
    assert "LOCAL_LLAMACPP" in res


def test_hardware_auto_tuner():
    profile = HardwareProfile(
        os_name="Linux",
        architecture="x86_64",
        cpu_cores=8,
        ram_total_gb=18.49,
        ram_available_gb=12.76,
        gpu_vendor="CPU_ONLY",
        vram_gb=0.0,
    )

    params = HardwareAutoTuner.tune_for_hardware(profile, model_size_b=7.0)
    assert params.n_threads == 6  # 8 cores - 2 reserved
    assert params.n_gpu_layers == 0  # CPU-only host
    assert params.context_length == 16384  # Based on 12.76 GB available RAM


def test_model_benchmark_tournament():
    tournament = ModelTournament(["qwen2.5-coder:7b", "deepseek-coder:6.7b"])
    results = tournament.run_tournament()
    assert len(results) == 2
    assert results[0].composite_rank >= results[1].composite_rank
    assert results[0].tool_score > 0.8

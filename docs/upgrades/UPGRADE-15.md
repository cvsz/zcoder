# UPGRADE-15: Local Model Factory, Registry & Hardware Auto-Tuning

## 1. Overview
Upgrade-15 establishes the Local Model Factory, first-class llama.cpp runtime integration, immutable artifact registries, hardware auto-tuning, and multi-dimensional benchmark tournaments for zero-cost autonomous coding.

## 2. Core Capabilities
- **Model Registry & State Machine (`ModelRegistry`)**: Strictly separates `CATALOG` entries from `VERIFIED`/`INSTALLED` models with hash/digest checks.
- **Model Acquisition & Dry-Run Planning**: Safe download planning with license checks and storage quota verification.
- **LlamaCpp First-Class Runtime (`LlamaCppRuntime`)**: First-class adapter for llama.cpp/llama-server.
- **Hardware Auto-Tuner (`HardwareAutoTuner`)**: Computes optimal CPU threads, GPU offload layers, and context memory limits based on detected system specifications.
- **Model Tournament (`ModelTournament`)**: Multi-dimensional benchmark engine evaluating Time-To-First-Token (TTFT), tokens/sec, correctness, and tool performance.

## 3. Verification
- `pytest tests/test_upgrade15_model_factory_suite.py`: 5 passed
- Zero paid commercial provider transport calls verified.

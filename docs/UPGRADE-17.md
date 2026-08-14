# UPGRADE-17: Local AI Production Runtime

## 1. Overview
Upgrade-17 turns the local AI components into a supervised, production-grade inference service with bounded crash recovery, model residency pools (Hot/Warm/Cold), memory admission control, and priority-aware inference scheduling.

## 2. Production Subsystems
- **Runtime Supervisor (`LocalRuntimeManager`)**: Supervises managed vs external processes, enforces bounded restart limits, and reconciles runtime instances.
- **Memory Admission Control (`MemoryAdmissionController`)**: Strict host headroom validation preventing out-of-memory crashes before model admission.
- **Model Pool Manager (`ModelPoolManager`)**: Manages `HOT`, `WARM`, `COLD`, and `EVICTING` residency states with LRU eviction for unpinned idle models.
- **Inference Scheduler (`LocalInferenceScheduler`)**: Priority-ranked request queuing with backpressure limits and dynamic cancellation.

## 3. Verification
- `pytest tests/test_upgrade17_production_runtime_suite.py`: 3 passed
- Regression suite: 732 passed, 2 optional skipped, 0 failed.

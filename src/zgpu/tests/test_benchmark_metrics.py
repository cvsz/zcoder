"""Regression tests for truthful benchmark throughput accounting."""

import hashlib
import json

import pytest

from zgpu.benchmarks.metrics import benchmark_environment, generation_metrics, write_benchmark_evidence


def test_counts_actual_tokens_when_context_window_stops_generation():
    metrics = generation_metrics([1, 2, 3], [1, 2, 3, 4], 0.5, 8)
    assert metrics.generated_tokens == 1
    assert metrics.tokens_per_second == 2.0
    assert metrics.ms_per_token == 500.0


def test_zero_generated_tokens_is_not_infinite_speed():
    metrics = generation_metrics([1, 2], [1, 2], 0.0, 4)
    assert metrics.generated_tokens == 0
    assert metrics.tokens_per_second == 0
    assert metrics.ms_per_token == 0


@pytest.mark.parametrize(
    "prompt,output,elapsed,requested",
    [
        ([1], [2], 0.5, 1),
        ([1], [1, 2, 3], 0.5, 1),
        ([1], [1], -0.5, 0),
        ([1], [1], float("nan"), 0),
        ([1], [1], 0.5, -1),
        ([1], [1, 2], 0.0, 1),
    ],
)
def test_rejects_invalid_measurement(prompt, output, elapsed, requested):
    with pytest.raises(ValueError):
        generation_metrics(prompt, output, elapsed, requested)


def test_benchmark_evidence_includes_environment_and_canonical_digest(tmp_path):
    evidence = {
        "schema_version": 1,
        "environment": benchmark_environment(),
        "results": {"tokens_per_second": 2.5},
    }
    output = tmp_path / "nested" / "evidence.json"

    digest = write_benchmark_evidence(evidence, output)

    saved = json.loads(output.read_text(encoding="utf-8"))
    checksum = saved.pop("evidence_sha256")
    canonical = json.dumps(saved, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    assert checksum == digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert saved["environment"]["python"]
    assert isinstance(saved["environment"]["git_worktree_dirty"], (bool, type(None)))
    assert "evidence_sha256" not in evidence


def test_benchmark_evidence_rejects_non_finite_values(tmp_path):
    with pytest.raises(ValueError, match="finite JSON values"):
        write_benchmark_evidence({"throughput": float("nan")}, tmp_path / "invalid.json")

"""Reproducible benchmark for zGPU's Python-simulated tensor and LLM paths."""

from __future__ import annotations

import argparse
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.metrics import benchmark_environment, generation_metrics, write_benchmark_evidence

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.runtime.runtime import ZRuntime


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def run_llm_benchmarks(
    *, warmups: int = 0, repeats: int = 1, output: str | Path | None = None
) -> dict[str, Any]:
    if isinstance(warmups, bool) or not isinstance(warmups, int) or not 0 <= warmups <= 20:
        raise ValueError("warmups must be between 0 and 20")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 50:
        raise ValueError("repeats must be between 1 and 50")

    print("=" * 60)
    print("zGPU simulated tensor and tiny transformer benchmark (not physical silicon)")
    print("=" * 60)

    rt = ZRuntime()
    kernels = LLMKernels(rt)

    print("\n[Benchmark 1] 4x4 Tensor Core MMA GEMM (16x16 Matrix Multiplications)")
    matrix_a = [[1.0 for _ in range(16)] for _ in range(16)]
    matrix_b = [[2.0 for _ in range(16)] for _ in range(16)]
    gemm_samples = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = kernels.gemm(matrix_a, matrix_b)
        gemm_samples.append((time.perf_counter() - start) * 1000.0)
    assert result is not None
    gemm_correct = all(abs(value - 32.0) < 1e-5 for row in result for value in row)
    if not gemm_correct:
        raise RuntimeError("simulated GEMM produced an incorrect result")
    print(f"  • Average 16x16 Tiled GEMM Latency: {statistics.mean(gemm_samples):.2f} ms")
    print(f"  • Result sample C[0][0]: {result[0][0]:.1f} (expected: 32.0)")

    print("\n[Benchmark 2] End-to-End Transformer Decoder Autoregressive Generation")
    config = LLMConfig(vocab_size=64, d_model=16, num_heads=2, d_ff=32, num_layers=2, max_seq_len=32)
    model = ZGPULLM(config=config, runtime=rt)
    prompt = [1, 5, 12, 20]
    requested_tokens = 8
    for _ in range(warmups):
        model.generate(prompt, max_new_tokens=requested_tokens)

    generation_samples: list[dict[str, Any]] = []
    for _ in range(repeats):
        start = time.perf_counter()
        output_tokens = model.generate(prompt, max_new_tokens=requested_tokens)
        elapsed = time.perf_counter() - start
        measured = generation_metrics(prompt, output_tokens, elapsed, requested_tokens)
        generation_samples.append(
            {
                "output_tokens": output_tokens,
                "generated_tokens": measured.generated_tokens,
                "elapsed_seconds": measured.elapsed_seconds,
                "tokens_per_second": measured.tokens_per_second,
                "ms_per_token": measured.ms_per_token,
            }
        )

    elapsed_samples = [sample["elapsed_seconds"] for sample in generation_samples]
    generated_counts = {sample["generated_tokens"] for sample in generation_samples}
    if len(generated_counts) != 1:
        raise RuntimeError("simulator generated inconsistent token counts across repetitions")
    first_sample = generation_samples[0]
    throughput_samples = [sample["tokens_per_second"] for sample in generation_samples]
    print(f"  • Input Prompt Tokens: {prompt}")
    print(f"  • Output Tokens: {first_sample['output_tokens']}")
    print(f"  • Generated Tokens: {first_sample['generated_tokens']} (requested: {requested_tokens})")
    print(f"  • Total Inference Time: {statistics.mean(elapsed_samples) * 1000.0:.2f} ms average")
    print(
        f"  • Throughput: {statistics.mean(throughput_samples):.2f} tokens/second average "
        f"({statistics.median(elapsed_samples) * 1000.0 / first_sample['generated_tokens']:.2f} ms/token median)"
        if first_sample["generated_tokens"]
        else "  • Throughput: 0.00 tokens/second (no tokens generated)"
    )

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": "zgpu-python-simulator-llm",
        "category": "python_simulator",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "environment": benchmark_environment(),
        "configuration": {
            "runtime": "Python SIMT/tensor simulator",
            "model": "randomly_initialized_tiny_transformer",
            "dtype": "Python float",
            "prompt_tokens": len(prompt),
            "requested_generation_tokens": requested_tokens,
            "warmups": warmups,
            "repeats": repeats,
            "gemm_shape": [16, 16, 16],
        },
        "results": {
            "gemm": {
                "correct": gemm_correct,
                "latency_ms_samples": gemm_samples,
                "latency_ms_mean": statistics.mean(gemm_samples),
                "latency_ms_p50": statistics.median(gemm_samples),
                "latency_ms_p95": _percentile(gemm_samples, 0.95),
            },
            "generation": {
                "correct_token_count": True,
                "generated_tokens": first_sample["generated_tokens"],
                "output_tokens": first_sample["output_tokens"],
                "latency_seconds_samples": elapsed_samples,
                "latency_seconds_mean": statistics.mean(elapsed_samples),
                "latency_seconds_p50": statistics.median(elapsed_samples),
                "latency_seconds_p95": _percentile(elapsed_samples, 0.95),
                "tokens_per_second_samples": throughput_samples,
                "tokens_per_second_mean": statistics.mean(throughput_samples),
            },
        },
        "limitations": [
            "This measures the Python simulator, not physical GPU execution.",
            "The transformer has randomly initialized weights and is not a quality or real-model inference benchmark.",
            "No baseline comparison or acceleration claim is produced.",
        ],
    }
    if output is not None:
        digest = write_benchmark_evidence(evidence, output)
        print(f"\nJSON evidence: {Path(output).expanduser()} (SHA-256: {digest})")

    print("\nzGPU simulator benchmark complete (no hardware speedup claim)")
    print("=" * 60)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmups", type=int, default=0, help="Number of generation warm-up runs (0-20).")
    parser.add_argument("--repeats", type=int, default=1, help="Number of measured repetitions (1-50).")
    parser.add_argument("--output", type=Path, help="Optional path for machine-readable JSON evidence.")
    args = parser.parse_args()
    try:
        run_llm_benchmarks(warmups=args.warmups, repeats=args.repeats, output=args.output)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

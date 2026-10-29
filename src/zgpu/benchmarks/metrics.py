"""Correctness-first measurement of autoregressive token throughput."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GenerationMetrics:
    generated_tokens: int
    elapsed_seconds: float
    tokens_per_second: float
    ms_per_token: float


def generation_metrics(
    prompt: list[int], output: list[int], elapsed_seconds: float, requested_tokens: int
) -> GenerationMetrics:
    """Report actual appended tokens, never requested token count as throughput.

    Requires the model output to preserve the prompt prefix and not exceed
    the requested generation budget. Timing must be finite and nonnegative.
    """
    if requested_tokens < 0:
        raise ValueError("requested_tokens must be nonnegative")
    if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be finite and nonnegative")
    if output[: len(prompt)] != prompt:
        raise ValueError("output must preserve the prompt prefix")
    generated = len(output) - len(prompt)
    if generated > requested_tokens:
        raise ValueError("generated token count exceeds requested limit")
    if generated and elapsed_seconds == 0:
        raise ValueError("elapsed_seconds must be positive when tokens were generated")
    throughput = generated / elapsed_seconds if generated else 0.0
    latency = elapsed_seconds * 1000.0 / generated if generated else 0.0
    return GenerationMetrics(generated, elapsed_seconds, throughput, latency)


def benchmark_environment() -> dict[str, Any]:
    """Collect bounded, non-secret local environment metadata for benchmark evidence."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        commit = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        worktree_dirty = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        worktree_dirty = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "git_commit": commit or None,
        "git_worktree_dirty": worktree_dirty,
    }


def write_benchmark_evidence(evidence: dict[str, Any], output_path: str | Path) -> str:
    """Write JSON evidence with a SHA-256 digest over the canonical payload."""
    if not isinstance(evidence, dict):
        raise TypeError("evidence must be a dictionary")
    try:
        canonical = json.dumps(
            evidence, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("benchmark evidence must contain finite JSON values") from exc
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    output = dict(evidence)
    output["evidence_sha256"] = digest
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()
    return digest

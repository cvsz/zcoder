"""zGPU Hardware-Accelerated Vector Embedding & Associative Memory Engine.

Provides massively parallel cosine similarity and top-k nearest-neighbor retrieval
accelerated via zGPU Tensor Core GEMM and SIMT vector reductions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.runtime import ZRuntime


@dataclass
class MemoryRecord:
    id: str
    vector: list[float]
    metadata: dict[str, Any]
    timestamp: float = 0.0


class FastVectorMemory:
    """Associative Vector Memory Bank with zGPU SIMT hardware acceleration."""

    def __init__(self, dim: int = 16, runtime: ZRuntime | None = None):
        self.dim = dim
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)
        self.records: list[MemoryRecord] = []

    def add(self, memory_id: str, vector: list[float], metadata: dict[str, Any] | None = None):
        """Insert or update a memory record with normalized embedding vector."""
        norm = math.sqrt(sum(v * v for v in vector)) or 1e-8
        normalized = [v / norm for v in vector]
        # Pad to multiple of 4 if needed
        if len(normalized) < self.dim:
            normalized.extend([0.0] * (self.dim - len(normalized)))
        elif len(normalized) > self.dim:
            normalized = normalized[: self.dim]

        self.records.append(
            MemoryRecord(
                id=memory_id,
                vector=normalized,
                metadata=metadata or {},
            )
        )

    def search(self, query_vector: list[float], top_k: int = 3) -> list[tuple[MemoryRecord, float]]:
        """Perform hardware-accelerated cosine similarity ranking."""
        if not self.records:
            return []

        norm = math.sqrt(sum(v * v for v in query_vector)) or 1e-8
        q_norm = [v / norm for v in query_vector]
        if len(q_norm) < self.dim:
            q_norm.extend([0.0] * (self.dim - len(q_norm)))
        elif len(q_norm) > self.dim:
            q_norm = q_norm[: self.dim]

        # Pack memory matrix M x dim
        mem_matrix = [rec.vector for rec in self.records]

        # Align to multiple of 4 for Tensor Core GEMM
        pad_rows = (4 - (len(mem_matrix) % 4)) % 4
        padded_mem = [list(r) for r in mem_matrix]
        for _ in range(pad_rows):
            padded_mem.append([0.0] * self.dim)

        # Q (1 x dim) transposed: Q^T (dim x 1) padded to (dim x 4)
        q_t = [[q_norm[r] if c == 0 else 0.0 for c in range(4)] for r in range(self.dim)]

        # Run zGPU Tensor Core GEMM: (M_pad x dim) @ (dim x 4) -> (M_pad x 4)
        sim_scores_2d = self.kernels.gemm(padded_mem, q_t)

        results = []
        for i, rec in enumerate(self.records):
            score = sim_scores_2d[i][0]
            results.append((rec, score))

        # Sort descending by similarity
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def count(self) -> int:
        return len(self.records)

    def clear(self):
        self.records.clear()

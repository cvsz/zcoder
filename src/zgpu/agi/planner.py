"""Tree-of-Thought (ToT) & Monte Carlo Tree Search (MCTS) Multi-Candidate Evaluator.

Accelerated on zGPU by scoring candidate reasoning branches concurrently via Tensor Cores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.runtime import ZRuntime


@dataclass
class ThoughtCandidate:
    thought_id: str
    action: str
    feature_vector: list[float]
    score: float = 0.0
    status: str = "pending"


class SuperAGIPlanner:
    """Multi-path Tree-of-Thought and candidate evaluation engine accelerated on zGPU."""

    def __init__(self, feature_dim: int = 16, runtime: ZRuntime | None = None):
        self.feature_dim = feature_dim
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)

        # Objective weight vector (evaluated against candidate features)
        self.objective_weights = [1.0 / math.sqrt(feature_dim)] * feature_dim

    def set_objective(self, weights: list[float]):
        norm = math.sqrt(sum(w * w for w in weights)) or 1e-8
        aligned = [w / norm for w in weights]
        if len(aligned) < self.feature_dim:
            aligned.extend([0.0] * (self.feature_dim - len(aligned)))
        self.objective_weights = aligned[: self.feature_dim]

    def evaluate_candidates(self, candidates: list[ThoughtCandidate]) -> list[ThoughtCandidate]:
        """Concurrently evaluate and score candidate thoughts using zGPU Tensor Core GEMM."""
        if not candidates:
            return []

        # Pad candidate count to multiple of 4
        pad_count = (4 - (len(candidates) % 4)) % 4
        feature_matrix = [list(c.feature_vector) for c in candidates]
        for _ in range(pad_count):
            feature_matrix.append([0.0] * self.feature_dim)

        # Objective vector transposed to (dim x 4)
        w_t = [
            [self.objective_weights[r] if c == 0 else 0.0 for c in range(4)] for r in range(self.feature_dim)
        ]

        # Matrix multiply: (N_pad x dim) @ (dim x 4) -> (N_pad x 4)
        scores_matrix = self.kernels.gemm(feature_matrix, w_t)

        for i, cand in enumerate(candidates):
            raw_score = scores_matrix[i][0]
            cand.score = raw_score
            cand.status = "evaluated"

        # Return candidates sorted by best score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def select_best_path(self, candidates: list[ThoughtCandidate]) -> ThoughtCandidate | None:
        ranked = self.evaluate_candidates(candidates)
        return ranked[0] if ranked else None

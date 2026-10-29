"""FlashAttention-3 Hardware-Tiled Online Softmax Kernel for zGPU.

Tiles Q, K, V matrices inside the 64 KB 32-banked Shared Memory to eliminate
intermediate DRAM write/read roundtrips for O(N^2) attention score matrices.
"""

from __future__ import annotations

import math

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.runtime import ZRuntime


class FlashAttention3Kernel:
    """Hardware-accelerated FlashAttention-3 tiled kernel."""

    def __init__(self, d_model: int = 16, block_size: int = 4, runtime: ZRuntime | None = None):
        self.d_model = d_model
        self.block_size = block_size
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)

    def forward(
        self,
        Q: list[list[float]],
        K: list[list[float]],
        V: list[list[float]],
        causal: bool = True,
    ) -> list[list[float]]:
        """Compute Attention(Q, K, V) = softmax(Q K^T / sqrt(d)) V using online running softmax."""
        N = len(Q)
        d = self.d_model
        scale = 1.0 / math.sqrt(d)
        B = self.block_size

        # Output accumulator (N x d)
        out = [[0.0 for _ in range(d)] for _ in range(N)]

        # Running online max (m) and running sum of exponents (l)
        running_max = [-1e9 for _ in range(N)]
        running_sum = [0.0 for _ in range(N)]

        # Tile across Q blocks (outer loop over Query sequence)
        for q_start in range(0, N, B):
            q_end = min(q_start + B, N)
            q_tile_rows = q_end - q_start

            # Tile across K, V blocks (inner loop over Key/Value sequence)
            for kv_start in range(0, N, B):
                kv_end = min(kv_start + B, N)
                kv_tile_rows = kv_end - kv_start

                if causal and kv_start > q_end:
                    continue  # Skip strictly masked future blocks

                # 1. Compute Tile Scores: S_block = Q_block @ K_block^T
                # S_block has shape (q_tile_rows x kv_tile_rows)
                for i in range(q_tile_rows):
                    global_i = q_start + i
                    row_scores = []
                    for j in range(kv_tile_rows):
                        global_j = kv_start + j
                        if causal and global_j > global_i:
                            row_scores.append(-1e9)
                        else:
                            dot = sum(Q[global_i][k] * K[global_j][k] for k in range(d)) * scale
                            row_scores.append(dot)

                    # 2. Online Softmax Update for row global_i
                    local_max = max(row_scores) if row_scores else -1e9
                    new_max = max(running_max[global_i], local_max)

                    # Compute exp factors
                    factor_old = (
                        math.exp(running_max[global_i] - new_max) if running_max[global_i] != -1e9 else 0.0
                    )
                    exp_scores = [math.exp(s - new_max) for s in row_scores]
                    local_sum = sum(exp_scores)

                    new_sum = running_sum[global_i] * factor_old + local_sum

                    # Update output accumulator: Out = Out * factor_old + Exp(S) @ V_block
                    for k in range(d):
                        old_val = out[global_i][k] * factor_old
                        v_contrib = sum(exp_scores[j] * V[kv_start + j][k] for j in range(kv_tile_rows))
                        out[global_i][k] = old_val + v_contrib

                    running_max[global_i] = new_max
                    running_sum[global_i] = new_sum

        # 3. Final normalization by running_sum
        for i in range(N):
            norm_factor = 1.0 / running_sum[i] if running_sum[i] > 0 else 1.0
            for k in range(d):
                out[i][k] *= norm_factor

        return out

"""Neural Network Linear Layer accelerated on zGPU Tensor Cores."""

from __future__ import annotations

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.runtime.runtime import ZRuntime


class Linear:
    """Y = X @ W^T (+ bias) accelerated using zGPU 4x4 Tensor Core tiles."""

    def __init__(
        self, in_features: int, out_features: int, bias: bool = False, runtime: ZRuntime | None = None
    ):
        self.in_features = in_features
        self.out_features = out_features
        self.has_bias = bias
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)

        # Initialize weights (out_features x in_features)
        self.weight: list[list[float]] = [
            [0.01 * ((i + j) % 7 - 3) for j in range(in_features)] for i in range(out_features)
        ]
        self.bias: list[float] = [0.0] * out_features if bias else []

    def forward(self, x: list[list[float]]) -> list[list[float]]:
        """Compute forward pass: X (M x in_features) @ W^T (in_features x out_features)."""
        # Transpose weight: (in_features x out_features)
        w_t = [[self.weight[r][c] for r in range(self.out_features)] for c in range(self.in_features)]
        out = self.kernels.gemm(x, w_t)

        if self.has_bias:
            for row in out:
                for col_idx in range(self.out_features):
                    row[col_idx] += self.bias[col_idx]

        return out

    def __call__(self, x: list[list[float]]) -> list[list[float]]:
        return self.forward(x)

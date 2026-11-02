"""Transformer Decoder Architecture Accelerated by zGPU Hardware Execution.

Implements Multi-Head Self Attention, SwiGLU Feed-Forward Networks, and RMSNorm
layers utilizing zGPU Tensor Cores and SIMT vector execution.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from zgpu.kernels.llm_kernels import LLMKernels
from zgpu.nn.linear import Linear
from zgpu.runtime.runtime import ZRuntime


@dataclass
class LLMConfig:
    vocab_size: int = 64
    d_model: int = 16  # Multiple of 4 for zGPU Tensor Core tiling
    num_heads: int = 2
    d_ff: int = 32  # Multiple of 4
    num_layers: int = 2
    max_seq_len: int = 32
    eps: float = 1e-5


class Attention:
    """Multi-Head Self-Attention layer accelerated on zGPU."""

    def __init__(self, config: LLMConfig, runtime: ZRuntime):
        self.config = config
        self.d_k = config.d_model // config.num_heads
        self.runtime = runtime
        self.kernels = LLMKernels(runtime)

        self.q_proj = Linear(config.d_model, config.d_model, bias=False, runtime=runtime)
        self.k_proj = Linear(config.d_model, config.d_model, bias=False, runtime=runtime)
        self.v_proj = Linear(config.d_model, config.d_model, bias=False, runtime=runtime)
        self.out_proj = Linear(config.d_model, config.d_model, bias=False, runtime=runtime)

    def forward(self, x: list[list[float]], mask: list[list[float]] | None = None) -> list[list[float]]:
        # Q, K, V projections via zGPU GEMM
        q = self.q_proj(x)
        k = self.k_proj(x)
        v = self.v_proj(x)

        seq_len = len(x)
        scale = 1.0 / math.sqrt(self.d_k)

        # Transpose K: (d_model x seq_len)
        k_t = [[k[r][c] for r in range(seq_len)] for c in range(self.config.d_model)]

        # Attention scores: Q @ K^T
        scores = self.kernels.gemm(q, k_t)

        # Scale and mask + Softmax
        attn_out = []
        for i in range(seq_len):
            row = [scores[i][j] * scale for j in range(seq_len)]
            if mask is not None:
                for j in range(seq_len):
                    if mask[i][j] < 0:
                        row[j] = -1e9
            attn_weights = self.kernels.softmax(row)

            # Context = Attn @ V
            ctx_row = [0.0] * self.config.d_model
            for j in range(seq_len):
                w = attn_weights[j]
                for d in range(self.config.d_model):
                    ctx_row[d] += w * v[j][d]
            attn_out.append(ctx_row)

        return self.out_proj(attn_out)


class FeedForward:
    """SwiGLU Feed-Forward Network accelerated on zGPU."""

    def __init__(self, config: LLMConfig, runtime: ZRuntime):
        self.config = config
        self.runtime = runtime
        self.kernels = LLMKernels(runtime)

        self.w1 = Linear(config.d_model, config.d_ff, bias=False, runtime=runtime)
        self.w2 = Linear(config.d_ff, config.d_model, bias=False, runtime=runtime)
        self.w3 = Linear(config.d_model, config.d_ff, bias=False, runtime=runtime)

    def forward(self, x: list[list[float]]) -> list[list[float]]:
        gate = self.w1(x)
        val = self.w3(x)

        # SwiGLU: SiLU(gate) * val
        act = []
        for g_row, v_row in zip(gate, val, strict=False):
            silu_g = self.kernels.silu(g_row)
            act.append([sg * vr for sg, vr in zip(silu_g, v_row, strict=False)])

        return self.w2(act)


class TransformerBlock:
    """Standard Transformer Decoder Block."""

    def __init__(self, config: LLMConfig, runtime: ZRuntime):
        self.config = config
        self.attn = Attention(config, runtime)
        self.ffn = FeedForward(config, runtime)
        self.norm1_w = [1.0] * config.d_model
        self.norm2_w = [1.0] * config.d_model

    def forward(self, x: list[list[float]], mask: list[list[float]] | None = None) -> list[list[float]]:
        # Pre-LN RMSNorm + Attention + Residual
        normed_1 = [LLMKernels.rms_norm(row, self.norm1_w, self.config.eps) for row in x]
        attn_out = self.attn.forward(normed_1, mask)
        x1 = [
            [a + b for a, b in zip(r_orig, r_attn, strict=False)]
            for r_orig, r_attn in zip(x, attn_out, strict=False)
        ]

        # Pre-LN RMSNorm + FFN + Residual
        normed_2 = [LLMKernels.rms_norm(row, self.norm2_w, self.config.eps) for row in x1]
        ffn_out = self.ffn.forward(normed_2)
        x2 = [
            [a + b for a, b in zip(r_x1, r_ffn, strict=False)]
            for r_x1, r_ffn in zip(x1, ffn_out, strict=False)
        ]

        return x2


class ZGPULLM:
    """Full LLM Model Engine running on zGPU."""

    def __init__(self, config: LLMConfig | None = None, runtime: ZRuntime | None = None):
        self.config = config or LLMConfig()
        self.runtime = runtime or ZRuntime()
        self.kernels = LLMKernels(self.runtime)

        # Embedding weights
        self.token_embeddings = [
            [0.05 * ((i * 3 + j) % 11 - 5) for j in range(self.config.d_model)]
            for i in range(self.config.vocab_size)
        ]

        self.blocks = [TransformerBlock(self.config, self.runtime) for _ in range(self.config.num_layers)]
        self.final_norm_w = [1.0] * self.config.d_model
        self.head = Linear(self.config.d_model, self.config.vocab_size, bias=False, runtime=self.runtime)

    def forward(self, token_ids: list[int]) -> list[list[float]]:
        """Forward pass for token IDs returning next-token logits."""
        seq_len = len(token_ids)
        # Embed tokens
        x = [list(self.token_embeddings[tok % self.config.vocab_size]) for tok in token_ids]

        # Causal triangular attention mask
        mask = [[0.0 if j <= i else -1.0 for j in range(seq_len)] for i in range(seq_len)]

        # Decoder blocks
        for block in self.blocks:
            x = block.forward(x, mask)

        # Final RMSNorm
        normed = [LLMKernels.rms_norm(row, self.final_norm_w, self.config.eps) for row in x]

        # Language Model Head -> Logits (seq_len x vocab_size)
        logits = self.head(normed)
        return logits

    def generate(
        self,
        token_ids: list[int],
        max_new_tokens: int = 5,
        token_callback: Callable[[int], None] | None = None,
    ) -> list[int]:
        """Autoregressive generation on zGPU."""
        curr_tokens = list(token_ids)
        for _ in range(max_new_tokens):
            if len(curr_tokens) >= self.config.max_seq_len:
                break
            logits = self.forward(curr_tokens)
            last_logits = logits[-1]
            probs = self.kernels.softmax(last_logits)
            # Greedy argmax
            next_token = max(range(len(probs)), key=lambda idx: probs[idx])
            curr_tokens.append(next_token)
            if token_callback is not None:
                token_callback(next_token)
        return curr_tokens

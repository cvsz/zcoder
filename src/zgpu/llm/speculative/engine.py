"""zGPU Speculative Decoding Engine.

Accelerates autoregressive inference by using a small draft model to generate K
candidate tokens per iteration, followed by concurrent verification via the target model
in a single parallel zGPU Tensor Core pass.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from zgpu.llm.transformer import ZGPULLM


@dataclass
class SpeculativeResult:
    tokens: list[int]
    accepted_tokens: int
    draft_tokens: int
    speedup_ratio: float
    latency_ms: float


class SpeculativeDecoder:
    """Draft-and-Verify Speculative Decoding pipeline for zGPU."""

    def __init__(
        self,
        target_model: ZGPULLM,
        draft_model: ZGPULLM,
        lookahead_k: int = 4,
    ):
        self.target_model = target_model
        self.draft_model = draft_model
        self.lookahead_k = lookahead_k

    def generate(self, prompt_tokens: list[int], max_new_tokens: int = 12) -> SpeculativeResult:
        t0 = time.perf_counter()
        curr_tokens = list(prompt_tokens)
        total_accepted = 0
        total_drafted = 0

        while len(curr_tokens) - len(prompt_tokens) < max_new_tokens:
            # 1. Draft Phase: small model generates lookahead_k candidates quickly
            draft_candidates = []
            draft_ctx = list(curr_tokens)
            for _ in range(self.lookahead_k):
                logits = self.draft_model.forward(draft_ctx)
                probs = self.draft_model.kernels.softmax(logits[-1])
                next_tok = max(range(len(probs)), key=lambda idx: probs[idx])
                draft_candidates.append(next_tok)
                draft_ctx.append(next_tok)
                total_drafted += 1

            # 2. Verification Phase: target model runs forward pass on candidate sequence concurrently
            target_logits = self.target_model.forward(draft_ctx[:-1])
            accepted_in_step = 0

            # 3. Acceptance evaluation
            for i, draft_tok in enumerate(draft_candidates):
                pos = len(curr_tokens) - 1 + i
                if pos < len(target_logits):
                    t_probs = self.target_model.kernels.softmax(target_logits[pos])
                    t_tok = max(range(len(t_probs)), key=lambda idx: t_probs[idx])
                    if t_tok == draft_tok:
                        curr_tokens.append(draft_tok)
                        accepted_in_step += 1
                        total_accepted += 1
                        if len(curr_tokens) - len(prompt_tokens) >= max_new_tokens:
                            break
                    else:
                        # Reject and correct with target model's choice
                        curr_tokens.append(t_tok)
                        total_accepted += 1
                        break
                else:
                    break

            if accepted_in_step == 0:
                # Guarantee forward progress by appending target model's pick
                pos = len(curr_tokens) - 1
                t_probs = self.target_model.kernels.softmax(target_logits[pos])
                t_tok = max(range(len(t_probs)), key=lambda idx: t_probs[idx])
                curr_tokens.append(t_tok)
                total_accepted += 1

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        speedup = total_accepted / max(1, total_drafted / self.lookahead_k)

        return SpeculativeResult(
            tokens=curr_tokens,
            accepted_tokens=total_accepted,
            draft_tokens=total_drafted,
            speedup_ratio=round(speedup, 2),
            latency_ms=round(elapsed_ms, 2),
        )

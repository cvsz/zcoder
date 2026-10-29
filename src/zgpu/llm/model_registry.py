"""zGPU Model Registry & Multi-Model Service Engine.

Supports multiple named LLM model architectures, parameter scaling,
Thai language Unicode tokenization, and dynamic weight loading on top of the zGPU SIMT Tensor Core execution stack.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zgpu.llm.thai_tokenizer import ThaiMultilingualTokenizer
from zgpu.llm.transformer import ZGPULLM, LLMConfig
from zgpu.runtime.runtime import ZRuntime

log = logging.getLogger("zGPU-ModelRegistry")


@dataclass
class ModelProfile:
    name: str
    description: str
    config: LLMConfig
    tags: list[str]


# Predefined zGPU simulator model profiles
DEFAULT_PROFILES: dict[str, ModelProfile] = {
    "zgpu-thai": ModelProfile(
        name="zgpu-thai",
        description="Thai & Multilingual Transformer Decoder (ภาษาไทย 256-vocab, 16-dim, 2 layers)",
        config=LLMConfig(vocab_size=256, d_model=16, num_heads=2, d_ff=32, num_layers=2, max_seq_len=64),
        tags=["thai", "multilingual", "ภาษาไทย"],
    ),
    "zgpu-nano": ModelProfile(
        name="zgpu-nano",
        description="Ultra-lightweight edge inference model (8-dim, 1 layer)",
        config=LLMConfig(vocab_size=64, d_model=8, num_heads=2, d_ff=16, num_layers=1, max_seq_len=32),
        tags=["edge", "ultra-fast", "nano"],
    ),
    "zgpu-small": ModelProfile(
        name="zgpu-small",
        description="Default balanced model for general SIMT inference (16-dim, 2 layers)",
        config=LLMConfig(vocab_size=128, d_model=16, num_heads=2, d_ff=32, num_layers=2, max_seq_len=64),
        tags=["general", "balanced", "small"],
    ),
    "zgpu-medium": ModelProfile(
        name="zgpu-medium",
        description="Higher-capacity transformer decoder (32-dim, 4 layers, 4 heads)",
        config=LLMConfig(vocab_size=256, d_model=32, num_heads=4, d_ff=64, num_layers=4, max_seq_len=128),
        tags=["medium", "extended-context"],
    ),
    "zgpu-code": ModelProfile(
        name="zgpu-code",
        description="Optimized for autonomous code generation & ISA synthesis",
        config=LLMConfig(vocab_size=128, d_model=16, num_heads=4, d_ff=32, num_layers=3, max_seq_len=64),
        tags=["code", "self-coding", "isa"],
    ),
}


class ModelRegistry:
    """Manages loaded zGPU models and allows dynamic model instantiation."""

    def __init__(self, runtime: ZRuntime | None = None):
        self.runtime = runtime or ZRuntime()
        self.profiles: dict[str, ModelProfile] = dict(DEFAULT_PROFILES)
        self.loaded_models: dict[str, ZGPULLM] = {}
        self.tokenizers: dict[str, ThaiMultilingualTokenizer] = {}
        self.default_model_name: str = "zgpu-thai"

        # Pre-initialize the default Thai model
        self.get_or_load(self.default_model_name)

    def _get_tokenizer(self, model_name: str) -> ThaiMultilingualTokenizer:
        profile = self.profiles.get(model_name, self.profiles[self.default_model_name])
        vocab_size = profile.config.vocab_size
        if model_name not in self.tokenizers or self.tokenizers[model_name].vocab_size != vocab_size:
            self.tokenizers[model_name] = ThaiMultilingualTokenizer(vocab_size=vocab_size)
        return self.tokenizers[model_name]

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered model profiles and their loaded status."""
        result = []
        for name, profile in self.profiles.items():
            result.append(
                {
                    "name": name,
                    "description": profile.description,
                    "loaded": name in self.loaded_models,
                    "d_model": profile.config.d_model,
                    "num_layers": profile.config.num_layers,
                    "num_heads": profile.config.num_heads,
                    "vocab_size": profile.config.vocab_size,
                    "max_seq_len": profile.config.max_seq_len,
                    "tags": profile.tags,
                }
            )
        return result

    def register_model(
        self, name: str, config: LLMConfig, description: str = "", tags: list[str] | None = None
    ) -> None:
        """Register a new custom model specification."""
        self.profiles[name] = ModelProfile(
            name=name,
            description=description or f"Custom model {name}",
            config=config,
            tags=tags or ["custom"],
        )
        log.info("Registered model profile: %s", name)

    def get_or_load(self, name: str) -> ZGPULLM:
        """Fetch an already loaded model, or instantiate it on zGPU device memory."""
        if name not in self.profiles:
            raise ValueError(f"Unknown model '{name}'. Available: {list(self.profiles.keys())}")

        if name not in self.loaded_models:
            profile = self.profiles[name]
            log.info(
                "Loading model '%s' (d_model=%d, layers=%d) onto zGPU...",
                name,
                profile.config.d_model,
                profile.config.num_layers,
            )
            self.loaded_models[name] = ZGPULLM(config=profile.config, runtime=self.runtime)

        return self.loaded_models[name]

    def tokenize(self, model_name: str, text: str) -> list[int]:
        tok = self._get_tokenizer(model_name)
        return tok.encode(text)

    def detokenize(self, model_name: str, tokens: list[int]) -> str:
        tok = self._get_tokenizer(model_name)
        return tok.decode(tokens)

    def generate(
        self,
        prompt: str,
        model_name: str | None = None,
        max_tokens: int = 16,
        token_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        target_model = model_name or self.default_model_name
        model = self.get_or_load(target_model)

        t0 = time.perf_counter()
        token_ids = self.tokenize(target_model, prompt)
        if not token_ids:
            token_ids = [1]

        def emit_token(token_id: int) -> None:
            if token_callback is not None:
                token_callback(self.detokenize(target_model, [token_id]))

        out_tokens = model.generate(token_ids, max_new_tokens=max_tokens, token_callback=emit_token)
        new_tokens = out_tokens[len(token_ids) :]
        text_out = self.detokenize(target_model, new_tokens)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "text": text_out,
            "tokens_used": len(out_tokens),
            "tokens_generated": len(new_tokens),
            "latency_ms": round(latency_ms, 2),
            "model": target_model,
            "finish_reason": "length" if len(new_tokens) >= max_tokens else "stop",
        }

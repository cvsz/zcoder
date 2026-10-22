"""
coder.py — Claude API integration core
ZCoder CLI v1.7.0
"""

import json
import os
import urllib.request

from zcoder.config.logging import get_logger
from zcoder.config.settings import Config
from zcoder.core.resilience import safe_local_urlopen

logger = get_logger("coder")


class Coder:
    def __init__(
        self,
        api_key=None,
        model=None,
        temperature=0.3,
        max_tokens=4096,
        provider=None,
        base_url=None,
        personality_style=None,
        service_tier=None,
        inference_geo=None,
        fast_mode=False,
    ):
        self.config = Config()
        self.api_key = ""
        configured_model = self.config.get("model")
        self.model = model or (
            configured_model if configured_model and configured_model.startswith("zcoder-") else None
        )
        self.model = self.model or "zcoder-qwen2.5-coder-7b"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = provider or os.getenv("ZCODER_PROVIDER", "llama_cpp")
        self.base_url = base_url or os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080")
        self.personality_style = personality_style
        # service_tier: "auto" (use Priority Tier if committed, else fall
        # back to standard) or "standard_only". Not sent unless set — most
        # accounts have no Priority Tier commitment (they're no longer
        # purchasable, only existing commitments still work) and it's
        # rejected outright on Sonnet 5 / Mythos-tier models.
        self.service_tier = service_tier
        # inference_geo: "us" (US-only inference, 1.1x pricing) or "global"
        # (default). Only Opus 4.6+/Sonnet 4.6+ and later accept this param
        # at all — earlier models 400 if it's set.
        self.inference_geo = inference_geo
        # fast_mode: sends speed:"fast" — reduced-latency mode, currently a
        # research-preview feature restricted to certain Opus models and
        # billed at a premium rate. See claude_models.py FAST_MODE_SUPPORTED.
        self.fast_mode = fast_mode

    def _generate_local(self, prompt, system=None, file_content=None, history=None):
        """Call a locally hosted llama.cpp OpenAI-compatible chat endpoint."""
        from urllib.parse import urlsplit

        from zcoder.agent.orchestration.providers import resolve_model

        url = self.base_url.rstrip("/")
        parts = urlsplit(url)
        if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
            return "[ERROR] llama_cpp endpoint must use HTTP loopback; no external gateway is allowed."
        if parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
            return "[ERROR] Invalid llama_cpp base URL."
        messages = list(history or [])
        if system:
            messages.insert(0, {"role": "system", "content": system})
        user_content = prompt
        if file_content:
            user_content = f"File content:\n```\n{file_content}\n```\n\n{prompt}"
        messages.append({"role": "user", "content": user_content})
        try:
            local_model = resolve_model(self.model)
        except ValueError as exc:
            return f"[ERROR] {exc}"
        payload = {
            "model": local_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": False,
            "temperature": self.temperature,
        }
        req = urllib.request.Request(
            url + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with safe_local_urlopen(req, timeout=120) as response:
                data = json.loads(response.read(8 * 1024 * 1024 + 1))
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("invalid model response")
            return content
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("local_inference_failed", extra={"error_type": type(exc).__name__})
            return f"[ERROR] Local llama.cpp inference failed: {type(exc).__name__}. Check loopback server and model."

    def generate(self, prompt, system=None, file_content=None, history=None):
        """Generate a response from the configured local model."""
        if self.personality_style:
            try:
                from zcoder.agent.personalities import PersonalityManager

                addition = PersonalityManager().build_prompt_addition(self.personality_style)
                if addition:
                    system = f"{system}\n\n{addition}" if system else addition
            except Exception:
                logger.exception("personality_prompt_failed")
        if self.provider in {"llama_cpp", "local"}:
            return self._generate_local(prompt, system=system, file_content=file_content, history=history)
        return "[ERROR] Remote model providers are disabled; use --provider llama_cpp."

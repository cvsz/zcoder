"""Provider-neutral local model client used by the command-line interface."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from zcoder.config.logging import get_logger
from zcoder.core.exceptions import APIError, AuthenticationError, RateLimitError, TransientAPIError
from zcoder.core.resilience import CircuitBreaker, retry

logger = get_logger("coder")

# Shared across Coder instances within a process so repeated failures
# (e.g. an outage during a long --agent-orchestrate run) trip the breaker
# once rather than per-instance, instead of each Coder() call starting
# with a fresh "closed" breaker that never actually protects anything.
_default_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _open_local(request, timeout):
    opener = urllib.request.build_opener(_RejectRedirects())
    return opener.open(request, timeout=timeout)


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
        self.model = model or os.getenv("ZCODER_MODEL", "zqwen2.5-coder-7b-instruct-q4_k_m")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = (provider or "llama_cpp").strip().lower()
        self.base_url = (base_url or os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1")).rstrip("/")
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

    def generate(self, prompt, system=None, file_content=None, history=None):
        """Generate a response from the AI model."""
        if self.provider not in {"local", "llama_cpp", "openai_compatible"}:
            return "[ERROR] The command-line coding client only supports the local model server."
        parsed_url = urllib.parse.urlsplit(self.base_url)
        if (
            parsed_url.scheme != "http"
            or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            return "[ERROR] ZCODER_BASE_URL must point to a local llama-server endpoint."
        endpoint_base = (
            self.base_url if parsed_url.path.rstrip("/").endswith("/v1") else f"{self.base_url}/v1"
        )

        logger.info("generate_start", extra={"model": self.model, "prompt_chars": len(prompt or "")})
        messages = list(history or [])

        user_content = prompt
        if file_content:
            user_content = f"File content:\n```\n{file_content}\n```\n\n{prompt}"

        if self.personality_style:
            try:
                from zcoder.agent.personalities import PersonalityManager

                pm = PersonalityManager()
                addition = pm.build_prompt_addition(self.personality_style)
                if addition and system:
                    system = system + "\n\n" + addition
                elif addition:
                    system = addition
            except Exception:
                pass

        messages.append({"role": "user", "content": user_content})

        if self.service_tier or self.inference_geo or self.fast_mode:
            return "[ERROR] Cloud-only inference options are unavailable with the local model."

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "temperature": self.temperature,
        }
        headers = {"Content-Type": "application/json"}

        @retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_default_breaker)
        def _call():
            req = urllib.request.Request(
                f"{endpoint_base}/chat/completions",
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            try:
                with _open_local(req, timeout=120) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                if e.code == 401:
                    raise AuthenticationError("API key rejected (401)", details={"body": body[:300]}) from e
                if e.code == 429:
                    retry_after = None
                    try:
                        retry_after = float(e.headers.get("Retry-After", "")) if e.headers else None
                    except (TypeError, ValueError):
                        pass
                    raise RateLimitError(
                        "Rate limited (429)", retry_after=retry_after, details={"body": body[:300]}
                    ) from e
                if e.code >= 500:
                    raise TransientAPIError(f"Server error ({e.code})", details={"body": body[:300]}) from e
                raise APIError(
                    f"Request rejected ({e.code})", status_code=e.code, details={"body": body[:300]}
                ) from e
            except (TimeoutError, ConnectionError, OSError) as e:
                # Covers socket timeouts and connection resets from urllib,
                # which surface as plain OSError/ConnectionError subclasses,
                # not HTTPError. These are transient/retryable by nature.
                raise TransientAPIError(f"Network error: {e}") from e

        try:
            data = _call()
        except AuthenticationError as e:
            logger.error("auth_failed", extra={"model": self.model})
            return f"[API ERROR 401] {e.message}"
        except RateLimitError as e:
            logger.error("rate_limited_after_retries", extra={"model": self.model})
            return f"[API ERROR 429] {e.message}"
        except APIError as e:
            logger.error("api_error", extra={"model": self.model, "status_code": e.status_code})
            return f"[API ERROR {e.status_code}] {e.message}"
        except TransientAPIError as e:
            logger.error("transient_error_exhausted_retries", extra={"model": self.model})
            return f"[ERROR] {e.message}"
        except Exception as e:
            logger.exception("unexpected_error", extra={"model": self.model})
            return f"[ERROR] {e}"

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            logger.error("invalid_local_model_response", extra={"model": self.model})
            return "[ERROR] Local model returned an invalid chat completion response."
        logger.info("generate_ok", extra={"model": self.model, "response_chars": len(text)})
        return text

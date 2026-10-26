"""Local llama.cpp streaming and legacy provider tool-streaming helpers.

The text streaming command uses the loopback OpenAI-compatible SSE endpoint.
The legacy ``stream_with_tools`` protocol remains provider-specific and is
available only when an explicit remote provider is configured.

New in v1.11.0 — Fine-grained tool streaming (was a documented feature with
no code anywhere in this project): tool_use input streams to the client as
Claude generates it, without server-side JSON buffering/validation, cutting
latency to the first fragment of a large parameter (a file, a long string).
Per platform.claude.com/docs (checked 2026-07-02) this is now GA on all
models/platforms — no beta header required — and controlled per-tool with
the eager_input_streaming field rather than a blanket header. The legacy
fine-grained-tool-streaming-2025-05-14 beta header still works for tools
that leave the field unset, kept here for backward compatibility with older
integrations. Because fragments aren't validated as they stream, the
accumulated string isn't guaranteed to be valid JSON until the block closes
(and may never be, if stop_reason ends up "max_tokens" mid-parameter) —
callers of stream_with_tools() get the raw accumulated string per tool call
and should json.loads() it themselves with that in mind.

Also new: refusal stop_details handling. Refusal responses carry a
documented category ("cyber", "bio", or null) and explanation, letting you
route different refusal classes differently — see handle_refusal().

CLI flags:
  --stream                Stream output in real time
  --stream-thinking       Stream with thinking blocks visible
  --stream-tools          Stream with fine-grained tool input streaming
                           enabled on every tool passed
  --no-stream             Force non-streaming (default for most commands)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from zcoder.core.provider_policy import create_anthropic_client
from zcoder.infrastructure.observability.otel import trace_model_call

# Legacy header — GA now, per-tool eager_input_streaming is the current way
# to opt in, but this still works for requests that send it and leave the
# field unset on individual tools.
FINE_GRAINED_TOOL_STREAMING_BETA = "fine-grained-tool-streaming-2025-05-14"


def with_eager_input_streaming(tools: list[dict], enabled: bool = True) -> list[dict]:
    """Return a copy of tools with eager_input_streaming set on each —
    turns on fine-grained streaming for those tools. Pass enabled=False to
    explicitly force buffered streaming for a tool even under the legacy
    beta header (an explicit false overrides the header, per the docs)."""
    out = []
    for t in tools:
        t2 = dict(t)
        t2["eager_input_streaming"] = enabled
        out.append(t2)
    return out


def handle_refusal(response_or_stop_details) -> dict | None:
    """Read stop_details off a (non-streaming) response dict or a
    message_delta event's stop_details field. Returns {"category": ...,
    "explanation": ...} when the response was a refusal with no output
    generated, or None otherwise. category is "cyber", "bio", or null per
    the current docs — use it to route to a different fallback/support flow
    instead of just showing the raw refusal text. Refusal-only responses
    (stop_reason:"refusal" with no generated output) are documented as not
    billed, so this is also useful as a signal to skip cost bookkeeping for
    that call — see claude_cost_optimizer.py / claude_metrics.py."""
    if isinstance(response_or_stop_details, dict) and "stop_reason" in response_or_stop_details:
        if response_or_stop_details.get("stop_reason") != "refusal":
            return None
        details = response_or_stop_details.get("stop_details") or {}
    else:
        details = response_or_stop_details or {}
    return {
        "category": details.get("category"),
        "explanation": details.get("explanation", ""),
    }


class _RejectStreamRedirects(urllib.request.HTTPRedirectHandler):
    """Keep local model requests on the validated loopback origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StreamCoder:
    """Stream text from local llama-server; retain legacy remote tool streams."""

    def __init__(
        self, api_key: str = "", model: str = "zqwen2.5-coder-7b-instruct-q4_k_m", max_tokens: int = 4096
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.client = None
        self.base_url = os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1").strip().rstrip("/")

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        show_thinking: bool = False,
    ) -> str:
        """Stream a response, printing tokens live. Returns full text."""
        parsed = urllib.parse.urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ZCODER_BASE_URL must point to a local llama-server on loopback")
        endpoint_base = self.base_url if parsed.path.rstrip("/").endswith("/v1") else f"{self.base_url}/v1"
        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            f"{endpoint_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )

        full_text = ""
        thinking_text = ""
        usage_data = {}
        opener = urllib.request.build_opener(_RejectStreamRedirects())
        with trace_model_call(provider="local", model=self.model, operation="stream"):
            with opener.open(request, timeout=300) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        raise ValueError("Local model returned a malformed streaming event") from None
                    choices = event.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content") or ""
                        if isinstance(text, list):
                            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
                        if isinstance(text, str) and text:
                            full_text += text
                            print(text, end="", flush=True)
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        if isinstance(reasoning, str) and reasoning:
                            thinking_text += reasoning
                            if show_thinking:
                                print(reasoning, end="", file=sys.stderr, flush=True)
                    usage = event.get("usage")
                    if isinstance(usage, dict):
                        usage_data["input_tokens"] = usage.get("prompt_tokens", 0)
                        usage_data["output_tokens"] = usage.get("completion_tokens", 0)

        print()  # final newline
        if "input_tokens" in usage_data or "output_tokens" in usage_data:
            print(
                f"\033[90m[tokens] in={usage_data.get('input_tokens', 0)}  "
                f"out={usage_data.get('output_tokens', 0)}\033[0m"
            )

        return full_text

    def stream_file_analysis(self, file_content: str, prompt: str, system: str | None = None) -> str:
        """Stream analysis of a file."""
        full_prompt = f"```\n{file_content}\n```\n\n{prompt}"
        return self.stream(full_prompt, system=system)

    def stream_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        system: str | None = None,
        eager_input_streaming: bool = True,
        use_legacy_beta: bool = False,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Stream a single turn with tool_use fine-grained input streaming.
        Prints each partial_json fragment as it arrives (so a large
        parameter — a generated file, a long string — appears incrementally
        instead of all at once when the block closes), then returns
        {"text": ..., "tool_calls": [{"name","id","input_raw","input"}],
        "stop_reason": ...}. input is the parsed dict when the accumulated
        JSON was valid, input_raw always has the raw accumulated string —
        check both, since fine-grained streaming doesn't guarantee valid
        JSON on truncation (stop_reason == "max_tokens" mid-parameter)."""
        if eager_input_streaming:
            tools = with_eager_input_streaming(tools)

        messages = [{"role": "user", "content": prompt}]
        kwargs = dict(model=self.model, max_tokens=self.max_tokens, messages=messages, tools=tools)
        if system:
            kwargs["system"] = system
        extra_headers = {}
        if use_legacy_beta:
            extra_headers["anthropic-beta"] = FINE_GRAINED_TOOL_STREAMING_BETA
        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        full_text = ""
        tool_calls = []
        current = None  # in-progress tool_use block accumulator
        stop_reason = None
        stop_details = None

        client = self.client or create_anthropic_client(self.api_key)
        with client.messages.stream(**kwargs) as stream:
            for event in stream:
                etype = getattr(event, "type", "")

                if etype == "content_block_start":
                    block = event.content_block
                    if getattr(block, "type", "") == "tool_use":
                        current = {
                            "name": getattr(block, "name", ""),
                            "id": getattr(block, "id", ""),
                            "json": "",
                        }
                        if verbose:
                            print(
                                f"\n\033[90m[tool_use:{current['name']}] ",
                                end="",
                                file=sys.stderr,
                                flush=True,
                            )

                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", "")
                    if dtype == "text_delta":
                        text = getattr(delta, "text", "")
                        full_text += text
                        if verbose:
                            print(text, end="", flush=True)
                    elif dtype == "input_json_delta" and current is not None:
                        frag = getattr(delta, "partial_json", "")
                        current["json"] += frag
                        if verbose:
                            print(frag, end="", file=sys.stderr, flush=True)

                elif etype == "content_block_stop" and current is not None:
                    if verbose:
                        print("\033[0m", file=sys.stderr)
                    parsed = None
                    try:
                        parsed = json.loads(current["json"]) if current["json"] else {}
                    except json.JSONDecodeError:
                        pass  # expected possibility with eager_input_streaming
                    tool_calls.append(
                        {
                            "name": current["name"],
                            "id": current["id"],
                            "input_raw": current["json"],
                            "input": parsed,
                        }
                    )
                    current = None

                elif etype == "message_delta":
                    stop_reason = getattr(event, "delta", None) and getattr(event.delta, "stop_reason", None)
                    sd = getattr(event, "delta", None) and getattr(event.delta, "stop_details", None)
                    if sd:
                        stop_details = sd

        if verbose:
            print()
        if stop_reason == "refusal":
            refusal = handle_refusal({"stop_reason": stop_reason, "stop_details": stop_details or {}})
            if verbose and refusal:
                print(
                    f"\033[91m[refusal] category={refusal['category']} {refusal['explanation']}\033[0m",
                    file=sys.stderr,
                )

        return {
            "text": full_text,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
            "stop_details": stop_details,
        }


# ── CLI entry point ────────────────────────────────────────────────────────


def cmd_stream(
    prompt: str,
    api_key: str,
    model: str,
    system: str | None = None,
    file_content: str | None = None,
    show_thinking: bool = False,
):
    print("\033[94mℹ Streaming response…\033[0m\n")
    sc = StreamCoder(api_key=api_key, model=model)
    if file_content:
        return sc.stream_file_analysis(file_content, prompt, system=system)
    return sc.stream(prompt, system=system, show_thinking=show_thinking)


def cmd_stream_tools(
    prompt: str,
    tools: list[dict[str, Any]],
    api_key: str,
    model: str,
    system: str | None = None,
):
    """Stream one CLI tool turn through the bounded messaging service."""
    from zcoder.services.messaging_service import run_messaging_turn_once

    print("\033[94mℹ Streaming with fine-grained tool input…\033[0m\n")
    capability = StreamCoder(api_key=api_key, model=model)
    result = run_messaging_turn_once(
        capability,
        prompt,
        tools=tools,
        system=system,
        verbose=True,
    )
    if result.tool_calls:
        print(f"\n\033[90m── {len(result.tool_calls)} tool call(s) ─────\033[0m")
        for tc in result.tool_calls:
            print(f"  {tc['name']}: {tc['input'] if tc['input'] is not None else tc['input_raw'][:120]}")
    return {
        "text": result.text,
        "tool_calls": list(result.tool_calls),
        "stop_reason": result.stop_reason,
        "stop_details": result.stop_details,
    }

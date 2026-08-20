"""
claude_router.py — Multi-Agent Conversation Router (provider-neutral)
ZCoder CLI v1.40.x

Routes every incoming prompt to the most appropriate specialist agent
by asking a lightweight classifier call first, then forwarding to the
winner. Supports fallback chains and parallel fan-out.

Provider neutrality (Slice E):
  --provider / ZCODER_PROVIDER selects the gateway (anthropic|gemini|xai|ollama|local)
  --base-url / ZCODER_BASE_URL / OLLAMA_BASE_URL overrides the default gateway
  --api-key  / provider-specific env vars supply the credential
  local provider requires no network and returns a stub response.

CLI flags:
  --route PROMPT          Auto-route PROMPT to the best specialist agent
  --route-explain         With --route: print which agent was chosen and why
  --route-parallel        Fan-out to ALL agents and return the best answer
  --route-add-agent NAME  Register a custom agent description in the routing table
  --route-list            List all agents in the routing table
  --provider NAME         Gateway provider (anthropic|gemini|xai|ollama|local)
  --base-url URL          Override the provider gateway base URL
"""

from __future__ import annotations

import json
import urllib.request

from zcoder.claude.orchestration import providers
from zcoder.core.exceptions import ZCoderError
from zcoder.core.resilience import CircuitBreaker, retry, urlopen_json
from zcoder.core.utils import sampling_kwargs

_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30)

# Kept for backward compatibility; new code should resolve via providers module.
ENDPOINT = "https://api.anthropic.com/v1/messages"

# ── Built-in routing table ──────────────────────────────────────────────────
DEFAULT_ROUTING_TABLE = {
    "code": "Write, review, refactor, debug, or explain code in any language",
    "research": "Deep factual research, literature review, or evidence synthesis",
    "write": "Long-form writing, editing, summarisation, translation, or copywriting",
    "analyse": "Data analysis, statistical interpretation, or business insight extraction",
    "plan": "Project planning, task breakdown, roadmaps, or strategy",
    "brainstorm": "Idea generation, creative thinking, or blue-sky exploration",
    "security": "Security review, threat modelling, CVE analysis, or hardening advice",
    "architect": "System design, architecture decisions, or technology selection",
    "debug": "Root-cause analysis and bug fixing for code or systems",
    "automate": "Workflow automation, scripting, CI/CD, or DevOps pipeline design",
}


def _resolve_provider_kwargs(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[str, str, str]:
    prov = providers.resolve_provider(provider)
    key = providers.resolve_api_key(prov, api_key)
    url = providers.resolve_base_url(prov, base_url)
    return prov, url, key


@retry(max_attempts=4, base_delay=1.0, max_delay=15.0, breaker=_breaker)
def _call(
    api_key: str,
    payload: dict,
    *,
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    prov, url, key = _resolve_provider_kwargs(provider, base_url, api_key, model)
    if prov == "local":
        return {"text": "[local mode] No upstream call — local stub response."}
    mdl = model or "claude-sonnet-5"
    # Build provider-specific request
    # payload is the Anthropic-shaped dict produced by callers; decompose it
    # into normalized fields so the provider adapter can translate.
    messages: list[dict] = list(payload.get("messages") or [])
    system: str | None = payload.get("system")
    max_tokens: int = int(payload.get("max_tokens", 4096))
    sampling = {k: payload[k] for k in ("temperature", "top_p", "top_k") if k in payload}
    prov_payload = providers.build_payload(prov, mdl, messages, system, max_tokens, sampling)
    endpoint = providers.endpoint_for(prov, url, mdl)
    headers = providers.headers_for(prov, key)
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(prov_payload).encode(),
        headers=headers,
        method="POST",
    )
    raw = urlopen_json(req, timeout=60)
    # Normalize provider responses to an Anthropic-shaped dict so downstream
    # _text/parse logic keeps working; also stash the raw provider payload.
    if prov == "anthropic":
        return raw
    text = providers.parse_response(prov, raw)
    return {"content": [{"type": "text", "text": text}], "_provider": prov, "_raw": raw}


def _post(
    api_key: str,
    payload: dict,
    *,
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    # Preserves the pre-existing {"error": ...} contract callers below
    # already check for, while retrying transient failures in _call().
    try:
        return _call(api_key, payload, provider=provider, base_url=base_url, model=model)
    except ZCoderError as e:
        return {"error": e.message}
    except Exception as e:
        return {"error": str(e)}


def _text(data: dict) -> str:
    # Local stub already returns {"text": ...}; keep that fast path.
    if "text" in data and "content" not in data:
        return data.get("text", "") or ""
    # Provider-normalized shape from _call, or native Anthropic shape
    if "content" in data:
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    # Fallback to provider parse (e.g. when _call was bypassed in tests)
    prov = data.get("_provider")
    if prov:
        return providers.parse_response(prov, data.get("_raw", data))
    return ""


def classify(
    prompt: str,
    table: dict,
    api_key: str,
    model: str,
    *,
    provider: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Return (agent_name, reason) for the best-fit agent."""
    options = "\n".join(f"  {k}: {v}" for k, v in table.items())
    classifier_prompt = (
        f"You are a routing classifier. Given a user request, choose the single best "
        f"specialist agent from the list below. Reply with ONLY a JSON object: "
        f'{{"agent": "<agent_name>", "reason": "<one sentence>"}}\n\n'
        f"Agents:\n{options}\n\nUser request: {prompt}"
    )
    data = _post(
        api_key,
        {
            "model": model,
            "max_tokens": 200,
            **sampling_kwargs(model, temperature=0.0),
            "messages": [{"role": "user", "content": classifier_prompt}],
        },
        provider=provider,
        base_url=base_url,
        model=model,
    )
    raw = _text(data).strip()
    try:
        parsed = json.loads(raw)
        agent = parsed.get("agent", "code")
        reason = parsed.get("reason", "")
        if agent not in table:
            agent = "code"
        return agent, reason
    except (json.JSONDecodeError, KeyError):
        return "code", "classifier output not parseable; defaulting to code agent"


def route_and_call(
    prompt: str,
    api_key: str,
    model: str,
    table: dict | None = None,
    explain: bool = False,
    parallel: bool = False,
    *,
    provider: str | None = None,
    base_url: str | None = None,
) -> str:
    table = table or DEFAULT_ROUTING_TABLE

    if parallel:
        results = {}
        for agent_name, description in table.items():
            system = f"You are a specialist in: {description}. Answer as that expert."
            data = _post(
                api_key,
                {
                    "model": model,
                    "max_tokens": 2048,
                    **sampling_kwargs(model, temperature=0.5),
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                provider=provider,
                base_url=base_url,
                model=model,
            )
            results[agent_name] = _text(data)
        # Synthesise the best answer
        synthesis_prompt = (
            "Multiple specialist agents answered this question. "
            "Synthesise the best, most complete answer, crediting unique insights "
            "from each agent where relevant.\n\n"
            + "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in results.items())
            + f"\n\nOriginal question: {prompt}"
        )
        data = _post(
            api_key,
            {
                "model": model,
                "max_tokens": 4096,
                **sampling_kwargs(model, temperature=0.3),
                "messages": [{"role": "user", "content": synthesis_prompt}],
            },
            provider=provider,
            base_url=base_url,
            model=model,
        )
        return _text(data)

    agent_name, reason = classify(prompt, table, api_key, model, provider=provider, base_url=base_url)
    if explain:
        print(f"\033[90m→ Routing to [{agent_name}]: {reason}\033[0m\n")

    system = f"You are a specialist in: {table[agent_name]}. Answer as that expert."
    data = _post(
        api_key,
        {
            "model": model,
            "max_tokens": 4096,
            **sampling_kwargs(model, temperature=0.6),
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        provider=provider,
        base_url=base_url,
        model=model,
    )
    return _text(data)


def cmd_route(
    prompt: str,
    api_key: str,
    model: str,
    explain: bool = False,
    parallel: bool = False,
    extra_table: dict | None = None,
    *,
    provider: str | None = None,
    base_url: str | None = None,
):
    table = dict(DEFAULT_ROUTING_TABLE)
    if extra_table:
        table.update(extra_table)
    answer = route_and_call(
        prompt, api_key, model, table, explain, parallel, provider=provider, base_url=base_url
    )
    print(answer)


def cmd_route_list(extra_table: dict | None = None):
    table = dict(DEFAULT_ROUTING_TABLE)
    if extra_table:
        table.update(extra_table)
    print("\n\033[94mRouting Table\033[0m")
    for name, desc in sorted(table.items()):
        print(f"  \033[1m{name:<14}\033[0m {desc}")
    print()

"""utils.py — Terminal utilities & formatters"""

import os
import sys
import textwrap
from urllib.parse import parse_qs, urlencode


def sanitize_dsn(dsn: str) -> str:
    """Strip query parameters psycopg2 cannot parse.

    DSNs written for other tooling (Prisma, Supabase, ...) routinely carry
    params like ``?schema=public``; psycopg2 rejects any unknown query
    parameter with ``invalid URI query parameter`` at connect time. Keep
    only the parameters psycopg2 actually understands.
    """
    if "?" not in dsn:
        return dsn
    base, query = dsn.split("?", 1)
    if not query:
        return base
    supported = {
        "sslmode",
        "sslcert",
        "sslkey",
        "sslrootcert",
        "sslcrl",
        "sslcrlf",
        "application_name",
        "fallback_application_name",
        "connect_timeout",
        "options",
        "gssencmode",
        "krbsrvname",
        "target_session_attrs",
        "channel_binding",
        "service",
    }
    kept = {k: v[-1] for k, v in parse_qs(query).items() if k in supported}
    if not kept:
        return base
    return f"{base}?{urlencode(kept)}"


def print_header(title):
    width = min(os.get_terminal_size().columns if sys.stdout.isatty() else 80, 80)
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def print_success(msg):
    print(f"\033[92m✓ {msg}\033[0m")


def print_error(msg):
    print(f"\033[91m✗ {msg}\033[0m", file=sys.stderr)


def print_info(msg):
    print(f"\033[94mℹ {msg}\033[0m")


def print_warn(msg):
    print(f"\033[93m⚠ {msg}\033[0m")


def format_code_block(code, lang=""):
    return f"```{lang}\n{code}\n```"


def wrap_text(text, width=80):
    return textwrap.fill(text, width=width)


def confirm(prompt):
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# Models that reject explicit sampling parameters. Per platform.claude.com/docs
# (checked 2026-07-02, "What's new in Claude Sonnet 5"): Claude Sonnet 5 returns
# a 400 invalid_request_error if temperature/top_p/top_k are set to non-default
# values at all. Any call site that hardcodes temperature=... needs to route
# through sampling_kwargs() instead of building the dict itself, or it will
# 400 the moment someone points it at claude-sonnet-5 (the default model in
# config.py / coder.py).
NO_SAMPLING_PARAMS_MODEL_PREFIXES = ("claude-sonnet-5", "claude-fable-5", "claude-mythos-5")


def sampling_kwargs(model, temperature=None, top_p=None, top_k=None):
    """Build the temperature/top_p/top_k kwargs dict for a request, omitting
    all of them when `model` is one that 400s on explicit sampling params
    (Sonnet 5 and newer). Use this instead of hardcoding temperature=0.3 etc.
    directly into a payload/kwargs dict."""
    if model and str(model).startswith(NO_SAMPLING_PARAMS_MODEL_PREFIXES):
        return {}
    out = {}
    if temperature is not None:
        out["temperature"] = temperature
    if top_p is not None:
        out["top_p"] = top_p
    if top_k is not None:
        out["top_k"] = top_k
    return out

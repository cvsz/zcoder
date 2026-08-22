#!/usr/bin/env python3
"""
main.py — ZCoder CLI
Version 1.30.0 | Gap-audit finding: --thinking always sent manual
thinking.type="enabled"+budget_tokens, which is a 400 error on every
current-generation model (Opus 4.7/4.8, Sonnet 5, Fable 5, Mythos 5,
Mythos Preview) and deprecated on Opus 4.6/Sonnet 4.6. claude_thinking.py
now auto-selects real adaptive thinking (thinking.type="adaptive" +
top-level output_config.effort, GA, no beta header) per model, with a
--effort-legacy-budget escape hatch that fails fast on models where it
can't work. Also removed claude_structured.py's now-unnecessary
structured-outputs-2025-11-13 beta header (structured outputs are GA).
See docs/42_upgrade_v1.30.0.md, CHANGELOG.md, and ROADMAP.md.
"""

import argparse
import os
import sys
from pathlib import Path

# Both are tiny, dependency-free dicts (no urllib/API calls at import time),
# so importing them eagerly to build argparse `choices=` is cheap and keeps
# the CLI's advertised choices in sync with the actual data instead of a
# second hardcoded list drifting from it.
from zcoder.claude.personalities import AGENT_SYSTEM_PROMPTS, PERSONALITIES

VERSION = "1.41.0"
BANNER = f"\033[94mZCoder CLI v{VERSION}\033[0m"


def _api_key(args):
    if os.getenv("ZCODER_LOCAL_MODE", "").strip() in ("1", "true", "yes"):
        return os.getenv("ANTHROPIC_API_KEY", "local-mode-no-key-required")
    k = getattr(args, "api_key", None) or os.getenv("ANTHROPIC_API_KEY", "")
    if not k:
        print("[ERROR] ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    return k


def _model(args):
    return getattr(args, "model", "claude-sonnet-5") or "claude-sonnet-5"


def _read_file(path):
    try:
        return open(path).read()
    except Exception as e:
        print(f"[ERROR] Cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)


def build_parser():
    from zcoder.claude.models.registry import UPGRADE_TARGETS

    p = argparse.ArgumentParser(
        prog="zcoder",
        description=f"ZCoder CLI v{VERSION}",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    g = p.add_argument_group("Global")
    g.add_argument("-p", "--prompt")
    g.add_argument("-f", "--file")
    g.add_argument("-o", "--output")
    g.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Start a persistent multi-turn chat REPL (see claude_interactive.py)",
    )
    g.add_argument(
        "--interactive-system",
        metavar="TEXT",
        dest="interactive_system",
        help="Starting system prompt for --interactive",
    )
    g.add_argument(
        "--tui",
        action="store_true",

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
        help="Launch the full-screen Textual TUI (see tui.py) — model/personality/"
        "agent/skill sidebar plus a streaming chat transcript, in the terminal",
    )
    g.add_argument("--model", default="claude-sonnet-5")
    g.add_argument("--temperature", type=float, default=0.3)
    g.add_argument("--max-tokens", type=int, default=4096, dest="max_tokens")
    g.add_argument("--api-key", default="", dest="api_key")
    g.add_argument(
        "--provider",
        default=None,
        dest="provider",
        choices=["anthropic", "gemini", "xai", "ollama", "local"],
        help="Model gateway provider (default: anthropic; env ZCODER_PROVIDER / ZCODER_LOCAL_MODE)",
    )
    g.add_argument(
        "--base-url",
        default=None,
        dest="base_url",
        help="Override the provider gateway base URL (env ZCODER_BASE_URL / OLLAMA_BASE_URL)",
    )
    g.add_argument("--version", action="store_true")
    g.add_argument(
        "--service-tier",
        choices=["auto", "standard_only"],
        default=None,
        dest="service_tier",
        help="Priority Tier routing (requires an existing capacity "
        "commitment; not supported on Sonnet 5 or Mythos-tier models)",
    )
    g.add_argument(
        "--inference-geo",
        choices=["us", "global"],
        default=None,
        dest="inference_geo",
        help="Data residency: 'us' pins inference to US data centers "
        "at 1.1x pricing (Opus 4.6+/Sonnet 4.6+ only)",
    )
    g.add_argument(
        "--fast-mode",
        action="store_true",
        dest="fast_mode",
        help='Research-preview reduced-latency mode (speed:"fast"); '
        "currently Opus-only and billed at a premium rate",
    )
    g.add_argument(
        "--health-check",
        action="store_true",
        dest="health_check",
        help="Run liveness/readiness checks and exit (config, API key, "
        "disk-writable); prints JSON, exit code 0=healthy 1=unhealthy",
    )
    g.add_argument(
        "--health-check-deep",
        action="store_true",
        dest="health_check_deep",
        help="With --health-check, also make one minimal live API call "
        "(use for a startup probe, not a frequent liveness probe)",
    )

    sa = p.add_argument_group("Skills & Agents")
    # --skill/--agent were accepted by the parser and never read anywhere
    # (no args.skill / args.agent reference existed in this file at all) —
    # picking a skill or agent silently had zero effect on the request.
    # Now: --skill injects that skill's description into the system prompt,
    # --agent injects a role prompt for one of the named roles --list-agents
    # already prints (previously the only place those names existed), and
    # --personality was the same story one module over — personalities.py's
    # PersonalityManager was fully implemented and even wired into
    # coder.py's Coder.generate() via personality_style, but nothing in
    # main.py ever passed personality_style to a Coder(...) call because
    # there was no flag to source it from.
    sa.add_argument("--skill", help="Prepend a named skill's system prompt (see --list-skills)")
    sa.add_argument(
        "--agent",
        choices=sorted(AGENT_SYSTEM_PROMPTS),
        help="Prepend a named agent role's system prompt (see --list-agents)",
    )
    sa.add_argument(
        "--personality",
        choices=sorted(PERSONALITIES),
        help="Apply a response style/personality (see --list-personalities)",
    )
    sa.add_argument("--list-skills", action="store_true")
    sa.add_argument("--list-agents", action="store_true")
    sa.add_argument("--list-personalities", action="store_true", dest="list_personalities")

    pr = p.add_argument_group("Feature Projects")
    pr.add_argument("--project-create", metavar="NAME")
    pr.add_argument("--project-list", action="store_true")
    pr.add_argument("--project-show", metavar="ID")
    pr.add_argument("--project-plan", metavar="ID")
    pr.add_argument("--project-run", metavar="ID")
    pr.add_argument("--project-add-task", metavar="ID")
    pr.add_argument("--project-delete", metavar="ID")
    pr.add_argument("--project-archive", metavar="ID")
    pr.add_argument("--project-templates", action="store_true")
    pr.add_argument("--project-template", default="blank")
    pr.add_argument("--project-desc", default="")
    pr.add_argument("--task", metavar="TASK_ID")
    pr.add_argument("--task-title", default="")
    pr.add_argument("--task-desc", default="")
    pr.add_argument("--task-agent", default="")
    pr.add_argument("--task-priority", default="medium")

    ar = p.add_argument_group("Artifacts")
    ar.add_argument("--artifact-create", metavar="NAME")
    ar.add_argument("--artifact-list", action="store_true")
    ar.add_argument("--artifact-show", metavar="ID")
    ar.add_argument("--artifact-iterate", metavar="ID")
    ar.add_argument("--artifact-export", metavar="ID")
    ar.add_argument("--artifact-export-all", metavar="PROJ_ID")
    ar.add_argument("--artifact-tag", metavar="ID")
    ar.add_argument("--artifact-attach", metavar="ART_ID")
    ar.add_argument("--artifact-diff", metavar="ID")
    ar.add_argument("--artifact-delete", metavar="ID")
    ar.add_argument("--artifact-types", action="store_true")
    ar.add_argument("--artifact-type", default="code")
    ar.add_argument("--artifact-lang", default="")
    ar.add_argument("--artifact-tags", default="")
    ar.add_argument("--artifact-version", type=int)
    ar.add_argument("--artifact-query", default="")
    ar.add_argument("--artifact-project", default="")
    ar.add_argument("--tag", default="")
    ar.add_argument("--to-project", default="")
    ar.add_argument("--v1", type=int)
    ar.add_argument("--v2", type=int)
    ar.add_argument("--artifact-output-dir", default="")

    th = p.add_argument_group("Extended Thinking")
    th.add_argument("--thinking", action="store_true")
    th.add_argument("--thinking-budget", type=int, default=8000, dest="thinking_budget")
    th.add_argument("--effort", default="", choices=["", "low", "medium", "high", "xhigh", "max"])
    th.add_argument(
        "--adaptive",
        action="store_true",
        help="Force adaptive thinking (thinking.type='adaptive' + top-level "
        "output_config.effort, GA, no beta header). Default (neither this "
        "nor --effort-legacy-budget) auto-selects per model: adaptive on "
        "Opus 4.6+/Sonnet 4.6+/Sonnet 5/Opus 4.7/4.8/Fable 5/Mythos 5/Mythos "
        "Preview, legacy manual budget_tokens on Opus 4.5/Haiku 4.5/earlier",
    )
    th.add_argument(
        "--effort-legacy-budget",
        action="store_true",
        dest="effort_legacy_budget",
        help="Force the old manual thinking.type='enabled'+budget_tokens path "
        "(--thinking-budget/--effort still apply) even on a model where "
        "adaptive would otherwise be auto-selected. Errors out immediately, "
        "before any API call, on models where budget_tokens is a 400 "
        "(Opus 4.7/4.8, Sonnet 5, Fable 5, Mythos 5, Mythos Preview)",
    )
    th.add_argument("--interleaved-thinking", action="store_true", dest="interleaved_thinking")
    th.add_argument("--show-thinking", action="store_true", dest="show_thinking")
    th.add_argument(
        "--thinking-display-omitted",
        action="store_true",
        dest="thinking_display_omitted",
        help="v1.25.0: thinking.display='omitted' — faster streaming/smaller "
        "payloads for a caller that doesn't render thinking text "
        "(billing unchanged, GA, no beta header)",
    )

    p.add_argument("--stream", action="store_true")

    ws = p.add_argument_group("Web Search & Fetch")
    ws.add_argument("--web-search", action="store_true")
    ws.add_argument("--web-fetch", action="store_true")
    ws.add_argument("--max-searches", type=int, default=5, dest="max_searches")
    ws.add_argument("--no-citations", action="store_true", dest="no_citations")
    ws.add_argument("--fetch-url", metavar="URL", dest="fetch_url")
    ws.add_argument(
        "--response-inclusion",
        metavar="VALUE",
        dest="response_inclusion",
        default="",
        help="v1.24.0: drop a consumed result's blocks from the "
        'response (currently only "excluded" is documented); requires '
        "web_search_20260318/web_fetch_20260318, both defaults as of v1.24.0",
    )

    vi = p.add_argument_group("Vision")
    vi.add_argument("--vision", metavar="FILE")
    vi.add_argument("--vision-pdf", metavar="FILE", dest="vision_pdf")
    vi.add_argument("--vision-url", metavar="URL", dest="vision_url")
    vi.add_argument("--vision-code", action="store_true", dest="vision_code")
    vi.add_argument("--vision-compare", nargs=2, metavar="FILE", dest="vision_compare")
    vi.add_argument("--vision-ocr", metavar="FILE", dest="vision_ocr")
    vi.add_argument("--vision-lang", default="auto", dest="vision_lang")

    ba = p.add_argument_group("Batch API")
    ba.add_argument("--batch-submit", metavar="FILE", dest="batch_submit")
    ba.add_argument("--batch-status", metavar="ID", dest="batch_status")
    ba.add_argument("--batch-results", metavar="ID", dest="batch_results")
    ba.add_argument("--batch-cancel", metavar="ID", dest="batch_cancel")
    ba.add_argument("--batch-list", action="store_true", dest="batch_list")
    ba.add_argument("--batch-wait", action="store_true", dest="batch_wait")
    ba.add_argument("--batch-generate", type=int, default=0, dest="batch_generate")
    ba.add_argument(
        "--batch-300k-output",
        action="store_true",
        dest="batch_300k_output",
        help="Opt into 300k max output tokens per request (beta "
        "output-300k-2026-03-24), Opus 4.8/4.7/4.6 and Sonnet 5/4.6 only",
    )

    ca = p.add_argument_group("Prompt Caching")
    ca.add_argument("--cache", action="store_true")
    ca.add_argument("--cache-ttl", default="5m", choices=["5m", "1h"], dest="cache_ttl")
    ca.add_argument("--cache-warm", action="store_true", dest="cache_warm")
    ca.add_argument("--cache-system", default="", dest="cache_system")
    ca.add_argument(
        "--cache-stats",
        action="store_true",
        dest="cache_stats",
        help="With --cache: print token/hit-rate stats after the response "
        "(previously accepted by the parser but never read anywhere, "
        "so it had no effect either way — --cache always silently "
        "printed stats and there was no way to turn that off)",
    )
    ca.add_argument("--cache-docs", nargs="+", metavar="FILE", dest="cache_docs")
    ca.add_argument(
        "--cache-diagnose",
        action="store_true",
        dest="cache_diagnose",
        help="With --cache: opt into Cache diagnostics (beta) — report "
        "cache_miss_reason against this process's previous call. "
        "The client-side support for this (diagnose= on "
        "generate_cached()) has existed since v1.10.x, but no CLI "
        "flag ever set it, so it was unreachable from the CLI.",
    )
    ca.add_argument(
        "--cache-multi-turn",
        nargs="+",
        metavar="TEXT",
        dest="cache_multi_turn",
        help="Run a multi-turn cached conversation instead of a single "
        "--cache call; each TEXT is one user turn.",
    )
    ca.add_argument(
        "--cache-mid-system",
        default="",
        dest="cache_mid_system",
        help="With --cache-multi-turn: insert a mid-conversation system "
        "message (Opus 4.8 only) after the turn given by "
        "--cache-mid-system-after, without invalidating the cached "
        "prefix that came before it.",
    )
    ca.add_argument(
        "--cache-mid-system-after",
        type=int,
        default=0,
        dest="cache_mid_system_after",
        metavar="N",
        help="0-based turn index to insert --cache-mid-system after "
        "(default: 0, i.e. right after the first turn).",
    )

    tu = p.add_argument_group("Tool Use")
    tu.add_argument("--tool-agent", action="store_true", dest="tool_agent")
    tu.add_argument("--server-tool", metavar="TOOL", dest="server_tool")
    tu.add_argument("--list-server-tools", action="store_true", dest="list_server_tools")
    tu.add_argument("--max-turns", type=int, default=10, dest="max_turns")
    tu.add_argument(
        "--memory-agent",
        metavar="PROMPT",
        dest="memory_agent",
        help="Run an agent loop backed by the native memory tool (memory_20250818)",
    )
    tu.add_argument(
        "--memory-dir",
        default="~/.zcoder/memory",
        dest="memory_dir",
        help="Local directory backing --memory-agent (default: ~/.zcoder/memory)",
    )
    tu.add_argument(
        "--context-management",
        action="store_true",
        dest="context_management",
        help="With --server-tool: auto-clear stale tool results on long calls "
        "(context-management-2025-06-27 beta)",
    )
    tu.add_argument(
        "--compaction",
        action="store_true",
        dest="compaction",
        help="With --server-tool: enable server-side conversation compaction "
        "(compact_20260112 beta) instead of / alongside clear_tool_uses",
    )
    tu.add_argument(
        "--task-budget",
        type=int,
        default=0,
        dest="task_budget",
        help="With --server-tool: advisory task_budget in tokens for the full "
        "agentic loop (task-budgets-2026-03-13 beta; Opus 4.7/4.8, "
        "Fable 5, Mythos 5 only)",
    )
    tu.add_argument(
        "--ptc",
        action="store_true",
        dest="ptc",
        help="With --server-tool code_execution and --tool-file: mark those "
        "custom tools as callable from code (Programmatic Tool Calling)",
    )
    tu.add_argument(
        "--stream-tools",
        metavar="PROMPT",
        dest="stream_tools",
        help="Stream a turn with fine-grained tool input streaming, using "
        "--tool-file for the tool definitions",
    )
    tu.add_argument(
        "--mid-conv-tool-check",
        metavar="MODEL_ID",
        dest="mid_conv_tool_check",
        help="Check whether MODEL_ID supports mid-conversation tool changes "
        "(mid-conversation-tool-changes-2026-07-01 beta; Fable 5, Mythos 5, "
        "Opus 4.8, Opus 5 only)",
    )

    adv = p.add_argument_group("Advisor Tool")
    adv.add_argument(
        "--advisor",
        metavar="PROMPT",
        dest="advisor",
        help="Run PROMPT with an advisor model consulted mid-generation (advisor_20260301 beta)",
    )
    adv.add_argument(
        "--advisor-model",
        default="claude-opus-4-8",
        dest="advisor_model",
        help="Advisor model (default: claude-opus-4-8)",
    )
    adv.add_argument(
        "--advisor-max-uses",
        type=int,
        default=0,
        dest="advisor_max_uses",
        help="Cap on advisor tool definition's max_uses (unset = no cap)",
    )
    adv.add_argument(
        "--advisor-max-tokens",
        type=int,
        default=0,
        dest="advisor_max_tokens",
        help="Cap the advisor model's output tokens per call",
    )

    em = p.add_argument_group("Embeddings")
    em.add_argument(
        "--embed",
        metavar="TEXT",
        dest="embed",
        help="Embed TEXT via Voyage AI, print vector info (needs VOYAGE_API_KEY; "
        "Anthropic doesn't host its own embedding model)",
    )
    em.add_argument(
        "--embed-file", metavar="FILE", dest="embed_file", help="Embed each line of FILE via Voyage AI"
    )
    em.add_argument(
        "--embed-similarity",
        nargs=2,
        metavar=("A", "B"),
        dest="embed_similarity",
        help="Cosine similarity between two strings' embeddings",
    )
    em.add_argument("--embed-model", default="voyage-3.5", dest="embed_model")
    em.add_argument(
        "--embed-input-type", default="document", choices=["document", "query"], dest="embed_input_type"
    )

    so = p.add_argument_group("Structured Outputs")
    so.add_argument("--structured", action="store_true")
    so.add_argument("--schema", metavar="FILE")
    so.add_argument("--schema-inline", metavar="JSON", dest="schema_inline")
    so.add_argument("--structured-analyse", metavar="FILE", dest="structured_analyse")
    so.add_argument("--structured-extract", metavar="FILE", dest="structured_extract")

    fa = p.add_argument_group("Files API")
    fa.add_argument("--file-upload", metavar="FILE", dest="file_upload")
    fa.add_argument("--file-list", action="store_true", dest="file_list")
    fa.add_argument("--file-delete", metavar="ID", dest="file_delete")
    fa.add_argument("--file-ask", metavar="ID", dest="file_ask")
    fa.add_argument("--file-download", metavar="ID", dest="file_download")
    fa.add_argument("--file-output", default="", dest="file_output")
    fa.add_argument("--file-media-type", default="application/pdf", dest="file_media_type")

    ce = p.add_argument_group("Code Execution")
    ce.add_argument("--code-exec", action="store_true", dest="code_exec")
    ce.add_argument("--code-debug", metavar="FILE", dest="code_debug")
    ce.add_argument("--code-exec-output", default="", dest="code_exec_output")
    ce.add_argument(
        "--code-exec-version",
        metavar="VERSION",
        dest="code_exec_version",
        default="code_execution_20260521",
        help="Pin a code_execution tool version (default: code_execution_20260521 "
        "— GA, no beta header, discloses the 90s per-cell limit). Pass "
        "code_execution_20260120 or code_execution_20250522 to pin an older, "
        "still-supported version.",
    )

    tc = p.add_argument_group("Token Counting")
    tc.add_argument("--count-tokens", action="store_true", dest="count_tokens")
    tc.add_argument("--count-budget", type=int, default=0, dest="count_budget")

    ci = p.add_argument_group("Citations & RAG")
    ci.add_argument("--cite", nargs="+", metavar="FILE")
    ci.add_argument("--rag", metavar="DIR")
    ci.add_argument("--rag-pattern", default="*.md", dest="rag_pattern")

    mo = p.add_argument_group("Models API")
    mo.add_argument("--list-models", action="store_true", dest="list_models")
    mo.add_argument(
        "--list-models-legacy",
        action="store_true",
        dest="list_models_legacy",
        help="Include superseded (still-callable) models in --list-models' offline view",
    )
    mo.add_argument("--model-info", metavar="ID", dest="model_info")
    mo.add_argument(
        "--check-deprecated",
        metavar="PATH",
        dest="check_deprecated",
        help="Scan a file or directory for retired model ID strings and print migration targets",
    )
    mo.add_argument(
        "--upgrade-all",
        metavar="PATH",
        dest="upgrade_all",
        help="Rewrite EVERY known Claude model ID under PATH (retired, legacy, "
        "or just a different current model) to --upgrade-target. Unlike "
        "--check-deprecated this actually edits files. Dry-run by default.",
    )
    mo.add_argument(
        "--upgrade-target",
        choices=sorted(UPGRADE_TARGETS),
        default="fable5",
        dest="upgrade_target",
        help="Target for --upgrade-all: fable5 (claude-fable-5) or opus (claude-opus-4-8). Default: fable5",
    )
    mo.add_argument(
        "--upgrade-yes",
        action="store_true",
        dest="upgrade_yes",
        help="With --upgrade-all: actually write changes (default is a dry-run preview)",
    )
    mo.add_argument(
        "--upgrade-no-backup",
        action="store_true",
        dest="upgrade_no_backup",
        help="With --upgrade-all --upgrade-yes: skip writing .bak backup files",
    )

    f5 = p.add_argument_group("Claude Fable 5 / Mythos 5")
    f5.add_argument(
        "--fable5-info",
        action="store_true",
        dest="fable5_info",
        help="Show what's known about Fable 5 / Mythos 5 (pricing, context, refusal handling)",
    )
    f5.add_argument(
        "--fable5",
        metavar="PROMPT",
        dest="fable5",
        help="Call Claude Fable 5 with refusal detection and automatic fallback",
    )
    f5.add_argument(
        "--fable5-no-fallback",
        action="store_true",
        dest="fable5_no_fallback",
        help="With --fable5: disable automatic fallback on refusal (just report it). "
        "Only affects the manual retry path; no effect if "
        "--fable5-fallback-chain is set.",
    )
    f5.add_argument(
        "--fallback-model",
        default="claude-opus-4-8",
        dest="fallback_model",
        help="Manual-retry fallback model (default: claude-opus-4-8). "
        "No effect if --fable5-fallback-chain is set.",
    )
    f5.add_argument(
        "--fable5-fallback-chain",
        metavar="MODEL1,MODEL2|default",
        dest="fable5_fallback_chain",
        help="Server-side fallback (beta `fallbacks` param): comma-separated "
        "models (up to 3 total including the primary) that the platform "
        "itself retries against, in order, in the same round trip if the "
        "primary refuses. Or pass the literal value 'default' to use "
        "Anthropic's own recommended fallback models by refusal category "
        "(added 2026-07-24, needs its own beta header, sent automatically). "
        "Preferred over --fallback-model when available.",
    )

    m5 = p.add_argument_group("Claude Mythos 5 (limited access)")
    m5.add_argument(
        "--mythos5-info",
        action="store_true",
        dest="mythos5_info",
        help="Show what's known about Mythos 5 access/pricing (approval-gated, see --fable5-info for the public sibling)",
    )
    m5.add_argument(
        "--mythos5",
        metavar="PROMPT",
        dest="mythos5",
        help="Call Claude Mythos 5 directly (requires approved Project Glasswing access)",
    )

    o5 = p.add_argument_group("Claude Opus 5 (deep model-specific support)")
    o5.add_argument(
        "--opus5-info",
        action="store_true",
        dest="opus5_info",
        help="Show Opus 5's capability table (effort ladder, thinking rules, "
        "fast mode, Priority Tier, data residency)",
    )
    o5.add_argument("--opus5", metavar="PROMPT", dest="opus5", help="Call Claude Opus 5")
    o5.add_argument(
        "--opus5-effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        dest="opus5_effort",
        help="Effort level for --opus5 (default: model default)",
    )
    o5.add_argument(
        "--opus5-disable-thinking",
        action="store_true",
        dest="opus5_disable_thinking",
        help="Disable thinking for --opus5. Rejected client-side (not sent to the "
        "API) if combined with --opus5-effort xhigh or max — Opus 5 only allows "
        "disabling thinking at effort high or below.",
    )
    o5.add_argument(
        "--opus5-fast",
        action="store_true",
        dest="opus5_fast",
        help='Send speed:"fast" with --opus5 (supported on this model)',
    )
    o5.add_argument(
        "--opus5-geo",
        action="store_true",
        dest="opus5_geo",
        help='Send inference_geo:"us" with --opus5 (confirmed supported; 1.1x pricing)',
    )

    s5 = p.add_argument_group("Claude Sonnet 5 (deep model-specific support)")
    s5.add_argument(
        "--sonnet5-info",
        action="store_true",
        dest="sonnet5_info",
        help="Show Sonnet 5's capability table and current pricing "
        "($2/$10 per MTok permanently; Sep 1 increase was cancelled 2026-08-10)",
    )
    s5.add_argument("--sonnet5", metavar="PROMPT", dest="sonnet5", help="Call Claude Sonnet 5")
    s5.add_argument(
        "--sonnet5-geo",
        action="store_true",
        dest="sonnet5_geo",
        help='Send inference_geo:"us" with --sonnet5 (supported; 1.1x pricing)',
    )
    s5.add_argument(
        "--sonnet5-cost",
        metavar="IN,OUT",
        dest="sonnet5_cost",
        help="Estimate cost in USD for IN input / OUT output tokens on Sonnet 5 "
        "at the permanent $2/$10 per MTok standard rate",
    )

    h45 = p.add_argument_group("Claude Haiku 4.5 (deep model-specific support)")
    h45.add_argument(
        "--haiku45-info",
        action="store_true",
        dest="haiku45_info",
        help="Show Haiku 4.5's capability table (extended, non-adaptive thinking; "
        "no fast mode; no data residency)",
    )
    h45.add_argument("--haiku45", metavar="PROMPT", dest="haiku45", help="Call Claude Haiku 4.5")
    h45.add_argument(
        "--haiku45-thinking-budget",
        type=int,
        metavar="N",
        dest="haiku45_thinking_budget",
        help="Enable extended thinking with explicit budget_tokens=N (min 1024). "
        "Haiku 4.5 uses extended (manual-budget) thinking only, never adaptive.",
    )

    ad = p.add_argument_group("Admin API (usage/cost reporting + API key management)")
    ad.add_argument(
        "--admin-api-key",
        metavar="KEY",
        dest="admin_api_key",
        help="Admin API key (sk-ant-admin...). Falls back to the "
        "ANTHROPIC_ADMIN_API_KEY env var if not given.",
    )
    ad.add_argument(
        "--usage-report",
        action="store_true",
        dest="usage_report",
        help="Print an org usage/cost report (requires an Admin API key)",
    )
    ad.add_argument(
        "--usage-report-start",
        metavar="DATE",
        dest="usage_report_start",
        help="Report start date, YYYY-MM-DD (default: 30 days ago)",
    )
    ad.add_argument(
        "--usage-report-end",
        metavar="DATE",
        dest="usage_report_end",
        help="Report end date, YYYY-MM-DD (default: today)",
    )
    ad.add_argument(
        "--usage-report-group-by",
        default="model",
        metavar="FIELD",
        dest="usage_report_group_by",
        help="Group usage report by field, e.g. model, api_key_id (default: model)",
    )
    ad.add_argument(
        "--cost-report",
        action="store_true",
        dest="cost_report",
        help="Print an org cost report (billed spend, requires an Admin API key). "
        "Distinct from --usage-report, which reports token counts, not cost.",
    )
    ad.add_argument(
        "--cost-report-start",
        metavar="DATE",
        dest="cost_report_start",
        help="Report start date, YYYY-MM-DD (default: 30 days ago)",
    )
    ad.add_argument(
        "--cost-report-end",
        metavar="DATE",
        dest="cost_report_end",
        help="Report end date, YYYY-MM-DD (default: today)",
    )
    ad.add_argument(
        "--cost-report-group-by",
        default="model",
        metavar="FIELD",
        dest="cost_report_group_by",
        help="Group cost report by field, e.g. model, api_key_id (default: model)",
    )
    ad.add_argument(
        "--admin-list-keys",
        action="store_true",
        dest="admin_list_keys",
        help="List organization API keys (requires an Admin API key)",
    )
    ad.add_argument(
        "--admin-revoke-key",
        metavar="ID",
        dest="admin_revoke_key",
        help="Revoke (deactivate) an organization API key by ID",
    )
    ad.add_argument(
        "--admin-create-key",
        metavar="NAME",
        dest="admin_create_key",
        help="Explains why key creation isn't available via the API "
        "(Console-only by design) instead of silently failing",
    )
    ad.add_argument(
        "--spend-limits-list",
        action="store_true",
        dest="spend_limits_list",
        help="List every member's resolved effective spend limit (v1.23.0, Claude Enterprise only)",
    )
    ad.add_argument(
        "--spend-limit-set",
        metavar=("USER_ID", "AMOUNT"),
        nargs=2,
        dest="spend_limit_set",
        help="Set a per-user spend limit override (amount: decimal string, minor units)",
    )
    ad.add_argument(
        "--spend-limit-get", metavar="ID", dest="spend_limit_get", help="Get one spend limit override by id"
    )
    ad.add_argument(
        "--spend-limit-delete",
        metavar="ID",
        dest="spend_limit_delete",
        help="Delete a per-user spend limit override",
    )
    ad.add_argument(
        "--spend-limit-requests-list",
        action="store_true",
        dest="spend_limit_requests_list",
        help="List spend limit increase requests",
    )
    ad.add_argument(
        "--spend-limit-status",
        metavar="STATUS",
        dest="spend_limit_status",
        default="",
        choices=["", "pending", "approved", "denied"],
        help="Filter --spend-limit-requests-list by status",
    )
    ad.add_argument(
        "--spend-limit-request-approve",
        metavar="ID",
        dest="spend_limit_request_approve",
        help="Approve a pending increase request",
    )
    ad.add_argument(
        "--spend-limit-request-deny",
        metavar="ID",
        dest="spend_limit_request_deny",
        help="Deny a pending increase request",
    )
    ad.add_argument(
        "--rate-limits",
        action="store_true",
        dest="rate_limits",
        help="Print the organization's configured rate limits (v1.23.0)",
    )
    ad.add_argument(
        "--rate-limits-model",
        metavar="MODEL",
        dest="rate_limits_model",
        default="",
        help="Filter --rate-limits to one model's group",
    )
    ad.add_argument(
        "--rate-limits-workspace",
        metavar="WORKSPACE_ID",
        dest="rate_limits_workspace",
        help="Print one workspace's rate limit overrides, with inherited org_limit",
    )
    ad.add_argument(
        "--claude-code-usage-report",
        action="store_true",
        dest="claude_code_usage_report",
        help="Print daily per-user Claude Code productivity metrics (v1.24.0)",
    )
    ad.add_argument(
        "--claude-code-usage-report-start",
        metavar="DATE",
        dest="claude_code_usage_report_start",
        default="",
        help="Date (YYYY-MM-DD) for --claude-code-usage-report, default: yesterday",
    )
    ad.add_argument(
        "--cmek-list",
        action="store_true",
        dest="cmek_list",
        help="List registered CMEK external keys (v1.25.0; unverified endpoint "
        "shape, see docs/37_upgrade_v1.25.0_audit_and_impl.md)",
    )
    ad.add_argument(
        "--cmek-workspace",
        metavar="WORKSPACE_ID",
        dest="cmek_workspace",
        default="",
        help="Filter --cmek-list to one workspace",
    )

    ce = p.add_argument_group("Claude Enterprise User Management (v1.38.0, beta)")
    ce.add_argument(
        "--members-list",
        action="store_true",
        dest="members_list",
        help="List organization members (Members/Invites take no beta header)",
    )
    ce.add_argument(
        "--members-email",
        metavar="EMAIL",
        dest="members_email",
        default="",
        help="Filter --members-list to one email address",
    )
    ce.add_argument("--member-get", metavar="USER_ID", dest="member_get", help="Show one organization member")
    ce.add_argument(
        "--member-role-set",
        metavar=("USER_ID", "ROLE"),
        nargs=2,
        dest="member_role_set",
        help='Set a member\'s role to "user" or "managed" (administrative roles are Console-only)',
    )
    ce.add_argument(
        "--member-remove",
        metavar="USER_ID",
        dest="member_remove",
        help="Remove a member from the organization",
    )
    ce.add_argument(
        "--invite-create",
        metavar=("EMAIL", "ROLE"),
        nargs=2,
        dest="invite_create",
        help='Invite someone by email with role "user" or "managed"',
    )
    ce.add_argument(
        "--invite-rbac-groups",
        metavar="ID,ID",
        dest="invite_rbac_groups",
        default="",
        help="Comma-separated rbac_group_ids to assign on --invite-create acceptance",
    )
    ce.add_argument(
        "--invites-list",
        action="store_true",
        dest="invites_list",
        help="List pending/accepted/expired invites",
    )
    ce.add_argument(
        "--invite-withdraw", metavar="INVITE_ID", dest="invite_withdraw", help="Withdraw a pending invite"
    )
    ce.add_argument(
        "--groups-list",
        action="store_true",
        dest="groups_list",
        help="List Enterprise groups (requires ce-user-management beta)",
    )
    ce.add_argument("--group-create", metavar="NAME", dest="group_create", help="Create an Enterprise group")
    ce.add_argument(
        "--group-delete",
        metavar="GROUP_ID",
        dest="group_delete",
        help="Delete an Enterprise group (not SCIM-provisioned ones)",
    )
    ce.add_argument(
        "--group-members-list", metavar="GROUP_ID", dest="group_members_list", help="List a group's members"
    )
    ce.add_argument(
        "--group-member-add",
        metavar=("GROUP_ID", "USER_ID"),
        nargs=2,
        dest="group_member_add",
        help="Add an existing organization member to a group",
    )
    ce.add_argument(
        "--group-member-remove",
        metavar=("GROUP_ID", "USER_ID"),
        nargs=2,
        dest="group_member_remove",
        help="Remove a member from a group",
    )
    ce.add_argument(
        "--roles-list",
        action="store_true",
        dest="roles_list",
        help="List custom roles (read-only through the API)",
    )
    ce.add_argument(
        "--role-permissions",
        metavar="ROLE_ID",
        dest="role_permissions",
        help="List one custom role's permissions",
    )

    wf = p.add_argument_group("Workload Identity Federation (v1.23.0)")
    wf.add_argument(
        "--wif-exchange-token",
        action="store_true",
        dest="wif_exchange_token",
        help="Exchange the JWT found via env vars for a short-lived Claude API access token",
    )
    wf.add_argument(
        "--wif-status",
        action="store_true",
        dest="wif_status",
        help="Show which of the 5 WIF env vars are set/missing (never their values)",
    )
    wf.add_argument(
        "--org-admin-token",
        metavar="TOKEN",
        dest="org_admin_token",
        default="",
        help="org:admin OAuth bearer token, for --wif-create-*/--wif-list-* "
        "(distinct from --admin-api-key). Falls back to "
        "ANTHROPIC_ORG_ADMIN_TOKEN.",
    )
    wf.add_argument("--wif-create-service-account", metavar="NAME", dest="wif_create_service_account")
    wf.add_argument("--wif-list-service-accounts", action="store_true", dest="wif_list_service_accounts")
    wf.add_argument("--wif-create-issuer", metavar="NAME", dest="wif_create_issuer")
    wf.add_argument("--wif-issuer-url", metavar="URL", dest="wif_issuer_url", default="")
    wf.add_argument("--wif-list-issuers", action="store_true", dest="wif_list_issuers")
    wf.add_argument("--wif-create-rule", metavar="NAME", dest="wif_create_rule")
    wf.add_argument("--wif-rule-issuer", metavar="ID", dest="wif_rule_issuer", default="")
    wf.add_argument("--wif-rule-service-account", metavar="ID", dest="wif_rule_service_account", default="")
    wf.add_argument("--wif-rule-subject-prefix", metavar="PREFIX", dest="wif_rule_subject_prefix", default="")
    wf.add_argument("--wif-list-rules", action="store_true", dest="wif_list_rules")

    cp = p.add_argument_group("Compliance API (Activity Feed + chats/files/projects + directory)")
    cp.add_argument(
        "--compliance-api-key",
        metavar="KEY",
        dest="compliance_api_key",
        help="Compliance Access Key (sk-ant-api01-...) or Admin API key "
        "(sk-ant-admin01-..., Activity Feed only). Falls back to "
        "ANTHROPIC_COMPLIANCE_API_KEY, then --admin-api-key/"
        "ANTHROPIC_ADMIN_API_KEY, if not given.",
    )
    cp.add_argument(
        "--compliance-activities",
        action="store_true",
        dest="compliance_activities",
        help="Print recent Activity Feed entries",
    )
    cp.add_argument(
        "--compliance-activities-since",
        metavar="DATETIME",
        dest="compliance_activities_since",
        help="created_at.gte filter, RFC 3339 (e.g. 2026-06-01T00:00:00Z)",
    )
    cp.add_argument(
        "--compliance-activities-until",
        metavar="DATETIME",
        dest="compliance_activities_until",
        help="created_at.lte filter, RFC 3339",
    )
    cp.add_argument(
        "--compliance-activity-types",
        metavar="T1,T2",
        dest="compliance_activity_types",
        help="Comma-separated activity_types[] filter, e.g. claude_chat_created,claude_file_uploaded",
    )
    cp.add_argument(
        "--compliance-activities-limit",
        type=int,
        default=100,
        metavar="N",
        dest="compliance_activities_limit",
        help="Page size, 1-5000 (default: 100)",
    )
    cp.add_argument(
        "--compliance-activities-all",
        action="store_true",
        dest="compliance_activities_all",
        help="Page through the entire matching feed instead of just one page",
    )
    cp.add_argument(
        "--compliance-chats-list",
        action="store_true",
        dest="compliance_chats_list",
        help="List chats for --compliance-user-ids (Compliance Access Key required)",
    )
    cp.add_argument(
        "--compliance-user-ids",
        metavar="ID1,ID2",
        dest="compliance_user_ids",
        help="Comma-separated user IDs, required with --compliance-chats-list (max 10)",
    )
    cp.add_argument(
        "--compliance-chat-messages",
        metavar="CHAT_ID",
        dest="compliance_chat_messages",
        help="Print one chat's full message content",
    )
    cp.add_argument(
        "--compliance-chat-delete",
        metavar="CHAT_ID",
        dest="compliance_chat_delete",
        help="Hard-delete a chat — permanent, needs --compliance-yes to actually run",
    )
    cp.add_argument(
        "--compliance-file-download",
        metavar="FILE_ID",
        dest="compliance_file_download",
        help="Download a file's original bytes (use --compliance-output to set the path)",
    )
    cp.add_argument(
        "--compliance-file-delete",
        metavar="FILE_ID",
        dest="compliance_file_delete",
        help="Hard-delete a file — permanent, needs --compliance-yes to actually run",
    )
    cp.add_argument(
        "--compliance-projects-list",
        action="store_true",
        dest="compliance_projects_list",
        help="List projects",
    )
    cp.add_argument(
        "--compliance-project-info",
        metavar="PROJECT_ID",
        dest="compliance_project_info",
        help="Show one project's details",
    )
    cp.add_argument(
        "--compliance-project-attachments",
        metavar="PROJECT_ID",
        dest="compliance_project_attachments",
        help="List a project's attachments (files and documents)",
    )
    cp.add_argument(
        "--compliance-project-delete",
        metavar="PROJECT_ID",
        dest="compliance_project_delete",
        help="Hard-delete a project — permanent, needs --compliance-yes; "
        "fails clearly if chats are still attached",
    )
    cp.add_argument(
        "--compliance-orgs-list",
        action="store_true",
        dest="compliance_orgs_list",
        help="List every linked organization",
    )
    cp.add_argument(
        "--compliance-org-users",
        metavar="ORG_UUID",
        dest="compliance_org_users",
        help="List an organization's users",
    )
    cp.add_argument(
        "--compliance-org-roles",
        metavar="ORG_UUID",
        dest="compliance_org_roles",
        help="List an organization's RBAC roles",
    )
    cp.add_argument(
        "--compliance-org-settings",
        metavar="ORG_UUID",
        dest="compliance_org_settings",
        help="Show the effective settings (retention, redaction, IP allowlist, ...) in force for an organization",
    )
    cp.add_argument(
        "--compliance-groups-list",
        action="store_true",
        dest="compliance_groups_list",
        help="List RBAC/SCIM groups",
    )
    cp.add_argument(
        "--compliance-group-members",
        metavar="GROUP_ID",
        dest="compliance_group_members",
        help="List a group's members",
    )
    cp.add_argument(
        "--compliance-local-sessions-list",
        action="store_true",
        dest="compliance_local_sessions_list",
        help="List Cowork/Claude Code local sessions (filter with --compliance-user-ids)",
    )
    cp.add_argument(
        "--compliance-local-session-info",
        metavar="SESSION_ID",
        dest="compliance_local_session_info",
        help="Show metadata for one local Cowork/Claude Code session",
    )
    cp.add_argument(
        "--compliance-local-session-messages",
        metavar="SESSION_ID",
        dest="compliance_local_session_messages",
        help="Print full transcript/messages for one local Cowork/Claude Code session",
    )
    cp.add_argument(
        "--compliance-yes",
        action="store_true",
        dest="compliance_yes",
        help="Actually execute a --compliance-*-delete (default: dry-run preview only)",
    )
    cp.add_argument(
        "--compliance-output",
        metavar="PATH",
        dest="compliance_output",
        help="Output path for --compliance-file-download (default: the original filename)",
    )

    sk = p.add_argument_group("Agent Skills API (platform, skill_id-based)")
    sk.add_argument(
        "--skills-list",
        action="store_true",
        dest="skills_list",
        help="List Anthropic-provided pre-built Skills (pptx/xlsx/docx/pdf)",
    )
    sk.add_argument(
        "--skills-info",
        metavar="ID",
        dest="skills_info",
        help="Show details for one skill_id (info-only, no API call)",
    )

    cu = p.add_argument_group("Computer Use")
    cu.add_argument("--computer-use", metavar="TASK", dest="computer_use")

    ag = p.add_argument_group("Agent SDK")
    ag.add_argument("--agent-session", metavar="ID", dest="agent_session")
    ag.add_argument("--agent-rewind", metavar="ID", dest="agent_rewind")
    ag.add_argument("--agent-branch", metavar="ID", dest="agent_branch")
    ag.add_argument("--agent-orchestrate", action="store_true", dest="agent_orchestrate")
    ag.add_argument(
        "--agent-managed-run",
        metavar="TASK",
        dest="agent_managed_run",
        help="Run TASK on the real hosted Claude Managed Agents API "
        "(creates a throwaway agent/environment/session)",
    )
    ag.add_argument(
        "--agent-memory-store",
        metavar="NAME",
        dest="agent_memory_store",
        default="",
        help="With --agent-managed-run: create/reuse a persistent "
        "Managed Agents memory store NAME and mount it into the "
        "session (agent-memory-2026-07-22 beta, opt-in). Without "
        "--agent-managed-run: use with --agent-memory-store-create "
        "to create a standalone store.",
    )
    ag.add_argument(
        "--agent-memory-store-create",
        action="store_true",
        dest="agent_memory_store_create",
        help="Create a Managed Agents memory store (named via "
        "--agent-memory-store) without also running a task",
    )
    ag.add_argument(
        "--agent-memory-list",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_list",
        help="List the memory entries inside a memory store (v1.24.0)",
    )
    ag.add_argument(
        "--agent-memory-path-prefix",
        metavar="PREFIX",
        dest="agent_memory_path_prefix",
        default="",
        help="With --agent-memory-list: filter to entries under this path prefix (must end with '/')",
    )
    ag.add_argument(
        "--agent-memory-depth",
        metavar="N",
        dest="agent_memory_depth",
        default="",
        help="With --agent-memory-list: 0, 1, or omitted",
    )
    ag.add_argument(
        "--agent-memory-stores-list",
        action="store_true",
        dest="agent_memory_stores_list",
        help="List memory stores in the workspace (v1.27.0)",
    )
    ag.add_argument(
        "--agent-memory-stores-include-archived",
        action="store_true",
        dest="agent_memory_stores_include_archived",
        help="With --agent-memory-stores-list: include archived stores",
    )
    ag.add_argument(
        "--agent-memory-store-archive",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_store_archive",
        help="Archive a memory store (v1.27.0) -- one-way, no unarchive",
    )
    ag.add_argument(
        "--agent-memory-store-delete",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_store_delete",
        help="Permanently delete a memory store and everything in it "
        "(v1.27.0) -- dry-run unless --agent-memory-store-delete-yes",
    )
    ag.add_argument(
        "--agent-memory-store-delete-yes",
        action="store_true",
        dest="agent_memory_store_delete_yes",
        help="Confirm --agent-memory-store-delete instead of dry-running it",
    )
    ag.add_argument(
        "--agent-memory-get",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_get",
        help="Retrieve a memory's full content (v1.27.0); pair with --agent-memory-id",
    )
    ag.add_argument(
        "--agent-memory-create",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_create",
        help="Create a memory (v1.27.0); pair with --agent-memory-path and --agent-memory-content",
    )
    ag.add_argument(
        "--agent-memory-update",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_update",
        help="Update a memory's content/path (v1.27.0); pair with "
        "--agent-memory-id and --agent-memory-content and/or "
        "--agent-memory-path",
    )
    ag.add_argument(
        "--agent-memory-delete",
        metavar="MEMORY_STORE_ID",
        dest="agent_memory_delete",
        help="Delete a memory (v1.27.0); pair with --agent-memory-id -- "
        "dry-run unless --agent-memory-delete-yes",
    )
    ag.add_argument(
        "--agent-memory-delete-yes",
        action="store_true",
        dest="agent_memory_delete_yes",
        help="Confirm --agent-memory-delete instead of dry-running it",
    )
    ag.add_argument(
        "--agent-memory-id",
        metavar="MEMORY_ID",
        dest="agent_memory_id",
        default="",
        help="Memory ID for --agent-memory-get/update/delete",
    )
    ag.add_argument(
        "--agent-memory-path",
        metavar="PATH",
        dest="agent_memory_path",
        default="",
        help="Memory path for --agent-memory-create/update",
    )
    ag.add_argument(
        "--agent-memory-content",
        metavar="TEXT",
        dest="agent_memory_content",
        default="",
        help="Memory content for --agent-memory-create/update",
    )
    ag.add_argument("--agent-list-sessions", action="store_true", dest="agent_list_sessions")
    ag.add_argument("--list-tool-presets", action="store_true", dest="list_tool_presets")

    ag.add_argument(
        "--agent-dream",
        metavar="STORE_ID",
        dest="agent_dream",
        help="Run a Dreaming pass (research preview, dreaming-2026-04-21 "
        "beta) over memory store STORE_ID, producing a new curated "
        "output store. Async — returns a pending dream id.",
    )
    ag.add_argument(
        "--agent-dream-sessions",
        metavar="IDS",
        dest="agent_dream_sessions",
        default="",
        help="Comma-separated session IDs to fold into --agent-dream, alongside the memory store",
    )
    ag.add_argument(
        "--agent-dream-instructions",
        metavar="TEXT",
        dest="agent_dream_instructions",
        default="",
        help="Optional steering text for --agent-dream",
    )
    ag.add_argument(
        "--agent-dream-list",
        action="store_true",
        dest="agent_dream_list",
        help="List dreams in the workspace (newest first)",
    )
    ag.add_argument(
        "--agent-dream-list-include-archived",
        action="store_true",
        dest="agent_dream_list_include_archived",
        help="With --agent-dream-list, also include archived dreams",
    )
    ag.add_argument(
        "--agent-dream-list-limit",
        type=int,
        default=20,
        dest="agent_dream_list_limit",
        help="With --agent-dream-list, max results per page (default 20, max 100)",
    )
    ag.add_argument(
        "--agent-dream-list-page",
        metavar="CURSOR",
        dest="agent_dream_list_page",
        default="",
        help="With --agent-dream-list, page cursor from a previous call",
    )
    ag.add_argument(
        "--agent-dream-get",
        metavar="DREAM_ID",
        dest="agent_dream_get",
        help="Retrieve one dream's status, usage, session_id, and output_store_id",
    )
    ag.add_argument(
        "--agent-dream-cancel",
        metavar="DREAM_ID",
        dest="agent_dream_cancel",
        help="Cancel a pending/running dream immediately",
    )
    ag.add_argument(
        "--agent-dream-archive",
        metavar="DREAM_ID",
        dest="agent_dream_archive",
        help="Archive a completed/failed/canceled dream (excludes it from "
        "--agent-dream-list without deleting it)",
    )

    ag.add_argument(
        "--agent-outcome",
        metavar="DESC",
        dest="agent_outcome",
        default="",
        help="With --agent-managed-run: define an outcome (rubric-graded "
        "self-correction loop, public beta) instead of a plain task. "
        "Requires --agent-outcome-rubric.",
    )
    ag.add_argument(
        "--agent-outcome-rubric",
        metavar="FILE",
        dest="agent_outcome_rubric",
        default="",
        help="Markdown rubric file for --agent-outcome",
    )
    ag.add_argument(
        "--agent-outcome-max-iter",
        type=int,
        default=3,
        dest="agent_outcome_max_iter",
        help="max_iterations for --agent-outcome (default 3, max 20)",
    )

    ag.add_argument(
        "--agent-webhook-register",
        metavar="URL",
        dest="agent_webhook_register",
        help="Register a webhook URL for Managed Agents session/outcome/dream events (public beta)",
    )
    ag.add_argument(
        "--agent-webhook-events",
        metavar="LIST",
        dest="agent_webhook_events",
        default="",
        help="Comma-separated event types for --agent-webhook-register (default: all supported types)",
    )

    ag.add_argument(
        "--agent-vault-create",
        metavar="NAME",
        dest="agent_vault_create",
        help="Create a vault (v1.21.0, public beta) for third-party "
        "credentials (MCP OAuth, static bearer, or env-var secrets)",
    )
    ag.add_argument(
        "--agent-vault-external-user",
        metavar="ID",
        dest="agent_vault_external_user",
        default="",
        help="Optional external_user_id metadata for --agent-vault-create",
    )
    ag.add_argument(
        "--agent-vault-add-credential",
        metavar="VAULT_ID",
        dest="agent_vault_add_credential",
        help="Add a credential to VAULT_ID",
    )
    ag.add_argument(
        "--agent-vault-cred-type",
        metavar="TYPE",
        dest="agent_vault_cred_type",
        default="",
        choices=["mcp_oauth", "static_bearer", "environment_variable"],
        help="Credential type for --agent-vault-add-credential",
    )
    ag.add_argument(
        "--agent-vault-mcp-url",
        metavar="URL",
        dest="agent_vault_mcp_url",
        default="",
        help="MCP server URL (mcp_oauth/static_bearer credentials)",
    )
    ag.add_argument(
        "--agent-vault-secret-name",
        metavar="NAME",
        dest="agent_vault_secret_name",
        default="",
        help="Environment variable name (environment_variable credentials)",
    )
    ag.add_argument(
        "--agent-vault-secret",
        metavar="VALUE",
        dest="agent_vault_secret",
        default="",
        help="The credential's secret value (write-only, never logged)",
    )
    ag.add_argument(
        "--agent-vault-allowed-domains",
        metavar="LIST",
        dest="agent_vault_allowed_domains",
        default="",
        help="Comma-separated allow-listed domains (environment_variable credentials)",
    )
    ag.add_argument(
        "--agent-vault-injection-location",
        metavar="LOCATION",
        dest="agent_vault_injection_location",
        default="",
        choices=["", "headers", "body", "both"],
        help="Where the resolved secret is substituted at egress "
        "(environment_variable credentials only, v1.22.0)",
    )
    ag.add_argument(
        "--agent-vault-list",
        action="store_true",
        dest="agent_vault_list",
        help="List vaults in the workspace",
    )
    ag.add_argument(
        "--agent-vault",
        metavar="VAULT_ID",
        dest="agent_vault",
        default="",
        help="With --agent-managed-run: mount a vault's credentials into the session",
    )

    ag.add_argument(
        "--agent-override-json",
        metavar="FILE",
        dest="agent_override_json",
        default="",
        help="With --agent-managed-run: JSON file containing an "
        "agent_with_overrides dict (any of version, model, system, tools, "
        "mcp_servers, skills) for a session-level override (v1.22.0, public beta)",
    )
    ag.add_argument(
        "--agent-override-model",
        metavar="MODEL",
        dest="agent_override_model",
        default="",
        help="With --agent-managed-run: override just the model "
        "for this session (shortcut for --agent-override-json)",
    )
    ag.add_argument(
        "--agent-override-system",
        metavar="TEXT",
        dest="agent_override_system",
        default="",
        help="With --agent-managed-run: override just the system "
        "prompt for this session (shortcut for --agent-override-json)",
    )
    ag.add_argument(
        "--agent-stream-deltas",
        action="store_true",
        dest="agent_stream_deltas",
        help="With --agent-managed-run: live-print text as it's generated "
        "(v1.22.0, public beta), instead of waiting for each full turn",
    )

    ag.add_argument(
        "--agent-schedule-create",
        metavar="AGENT_ID",
        dest="agent_schedule_create",
        help="Attach a cron schedule (v1.21.0, public beta) to AGENT_ID",
    )
    ag.add_argument(
        "--agent-schedule-env",
        metavar="ENV_ID",
        dest="agent_schedule_env",
        default="",
        help="Environment id (with --agent-schedule-create)",
    )
    ag.add_argument(
        "--agent-schedule-cron",
        metavar="EXPR",
        dest="agent_schedule_cron",
        default="",
        help="Cron expression (with --agent-schedule-create)",
    )
    ag.add_argument(
        "--agent-schedule-tz",
        metavar="TZ",
        dest="agent_schedule_tz",
        default="UTC",
        help="IANA timezone (with --agent-schedule-create, default UTC)",
    )
    ag.add_argument(
        "--agent-schedule-task",
        metavar="TEXT",
        dest="agent_schedule_task",
        default="",
        help="Initial task text for the scheduled session",
    )
    ag.add_argument(
        "--agent-schedule-list",
        action="store_true",
        dest="agent_schedule_list",
        help="List scheduled deployments",
    )
    ag.add_argument(
        "--agent-schedule-cancel",
        metavar="DEPLOYMENT_ID",
        dest="agent_schedule_cancel",
        help="Archive a scheduled deployment",
    )

    ag.add_argument(
        "--agent-review-multiagent",
        metavar="PATH",
        dest="agent_review_multiagent",
        help="Native Multiagent orchestration (v1.21.0): parallel specialist "
        "code review of PATH over one shared sandbox",
    )
    ag.add_argument(
        "--agent-review-specialists",
        metavar="LIST",
        dest="agent_review_specialists",
        default="security,style,test-coverage",
        help="Comma-separated specialists for --agent-review-multiagent (security, style, test-coverage)",
    )

    ag.add_argument(
        "--agent-outcome-rubric-upload",
        metavar="FILE",
        dest="agent_outcome_rubric_upload",
        help="Upload a rubric once via the Files API and print its file_id (v1.21.0)",
    )
    ag.add_argument(
        "--agent-outcome-rubric-file",
        metavar="FILE_ID",
        dest="agent_outcome_rubric_file",
        default="",
        help="Reuse an uploaded rubric's file_id with --agent-outcome, "
        "instead of --agent-outcome-rubric FILE",
    )

    ag.add_argument(
        "--agent-env-self-hosted",
        metavar="NAME",
        dest="agent_env_self_hosted",
        help="Create a self-hosted sandbox environment NAME (public beta, "
        "v1.26.0) — tool execution runs on infrastructure you control "
        "(your own worker, or a managed provider like Cloudflare/Daytona/"
        "Modal/Vercel) instead of Anthropic's cloud sandbox. Prints the "
        "remaining manual steps (environment key generation is Console-"
        "only; running a worker is a separate long-lived process).",
    )
    ag.add_argument(
        "--agent-env-work-stats",
        metavar="ENVIRONMENT_ID",
        dest="agent_env_work_stats",
        help="Read a self-hosted environment's work queue state: how many "
        "sessions are waiting (depth), being processed (pending), and "
        "whether a worker is actually connected (workers_polling)",
    )

    ag.add_argument(
        "--agent-create",
        metavar="NAME",
        dest="agent_create",
        help="Create a persisted, versioned Managed Agent NAME (v1.38.0, "
        "public beta) -- pair with --model and --agent-system",
    )
    ag.add_argument(
        "--agent-system",
        metavar="TEXT",
        dest="agent_system",
        default="You are a helpful coding assistant.",
        help="System prompt for --agent-create/--agent-update",
    )
    ag.add_argument(
        "--agent-effort",
        metavar="LEVEL",
        dest="agent_effort",
        default="",
        help="Effort level for --agent-create/--agent-update (v1.38.0, public beta)",
    )
    ag.add_argument(
        "--agent-get",
        metavar="AGENT_ID",
        dest="agent_get",
        help="Retrieve a Managed Agent's stored config (v1.38.0, public beta)",
    )
    ag.add_argument(
        "--agent-get-version",
        type=int,
        metavar="N",
        dest="agent_get_version",
        help="With --agent-get: read a specific prior version instead of current",
    )
    ag.add_argument(
        "--agent-list",
        action="store_true",
        dest="agent_list",
        help="List Managed Agents in the workspace (v1.38.0, public beta)",
    )
    ag.add_argument(
        "--agent-list-limit",
        type=int,
        default=50,
        dest="agent_list_limit",
        help="With --agent-list: max results (default 50)",
    )
    ag.add_argument(
        "--agent-update",
        metavar="AGENT_ID",
        dest="agent_update",
        help="Update a persisted agent, creating a new version (v1.38.0, "
        "public beta) -- pair with --model/--agent-system/--agent-effort",
    )
    ag.add_argument(
        "--agent-inference-geo",
        metavar="GEO",
        dest="agent_inference_geo",
        default="",
        choices=["", "us", "global"],
        help="With --agent-create/--agent-update: pin the Managed Agent's "
        "model.inference_geo (v1.39.0, public beta). 'us' keeps "
        "inference US-only at a 1.1x price multiplier; 'global' runs "
        "wherever there's capacity at the standard rate. Distinct from "
        "the top-level --inference-geo flag, which is the Messages API "
        "field (different request shape).",
    )

    ag.add_argument(
        "--agent-session-budget-usd",
        type=float,
        metavar="DOLLARS",
        dest="agent_session_budget_usd",
        help="With --agent-managed-run: set a hard USD spend cap on the "
        "throwaway session (v1.39.0, public beta). The session pauses "
        "with stop_reason=budget_reached instead of terminating once "
        "reached -- see --agent-session-budget-set/--agent-session-get "
        "to change or inspect it afterward. Not the same as "
        "--task-budget (an advisory token budget for the Advisor "
        "Tool's agentic loop) or --thinking-budget.",
    )
    ag.add_argument(
        "--agent-session-get",
        metavar="SESSION_ID",
        dest="agent_session_get",
        help="Inspect a Managed Agents session's status, stop_reason, "
        "budget, and consumed spend (v1.39.0, public beta)",
    )
    ag.add_argument(
        "--agent-session-budget-set",
        metavar="SESSION_ID",
        dest="agent_session_budget_set",
        help="Replace SESSION_ID's spend budget -- pair with "
        "--agent-session-budget-usd for the new cap. Resumes the "
        "session automatically if it was paused at budget_reached.",
    )
    ag.add_argument(
        "--agent-session-budget-remove",
        metavar="SESSION_ID",
        dest="agent_session_budget_remove",
        help="Remove SESSION_ID's spend budget entirely (one-way -- the "
        "session can never be given a new budget afterward). Resumes "
        "the session automatically if it was paused at budget_reached.",
    )

    cw = p.add_argument_group("Cowork")
    cw.add_argument("--cowork", metavar="TYPE")
    cw.add_argument("--cowork-prompt", metavar="TEXT", dest="cowork_prompt")
    cw.add_argument("--cowork-files", nargs="+", dest="cowork_files")
    cw.add_argument("--cowork-depth", type=int, default=3, dest="cowork_depth")
    cw.add_argument(
        "--cowork-format",
        default="markdown",
        dest="cowork_format",
        choices=["markdown", "json", "outline", "bullets"],
    )
    cw.add_argument("--cowork-list", action="store_true", dest="cowork_list")

    xl = p.add_argument_group("Excel / Data Chat")
    xl.add_argument(
        "--excel",
        nargs="?",
        const="",
        metavar="FILE",
        dest="excel",
        help="Start a conversational spreadsheet session — build financial "
        "models, clean messy data, and create tables and charts, applied "
        "directly to a live .xlsx workbook. Optionally load an existing "
        ".xlsx/.csv as the starting data.",
    )
    xl.add_argument(
        "--excel-output",
        metavar="FILE",
        dest="excel_output",
        help="Workbook path to write after every turn (default: <input>.xlsx or excel_session.xlsx)",
    )
    xl.add_argument(
        "--excel-sheet",
        metavar="NAME",
        dest="excel_sheet",
        help="Which sheet to load from a multi-sheet --excel input file",
    )
    xl.add_argument(
        "--excel-native",
        action="store_true",
        dest="excel_native",
        help="Route --excel through Anthropic's own xlsx Skill (server-side, "
        "code-execution container) instead of the built-in pandas/openpyxl "
        "path. Requires Skills access on the account; no local pandas/"
        "openpyxl dependency needed for this mode. Falls back to the "
        "regular --excel path's behavior if omitted.",
    )

    pp = p.add_argument_group("PowerPoint / Slide Chat")
    pp.add_argument(
        "--pptx",
        nargs="?",
        const="",
        metavar="FILE",
        dest="pptx",
        help="Start a conversational slide-deck session — add/edit slides, "
        "tables, and charts, applied directly to a live .pptx deck. "
        "Optionally load an existing .pptx as the starting deck.",
    )
    pp.add_argument(
        "--pptx-output",
        metavar="FILE",
        dest="pptx_output",
        help="Deck path to write after every turn (default: <input>.pptx or pptx_session.pptx)",
    )
    pp.add_argument(
        "--pptx-native",
        action="store_true",
        dest="pptx_native",
        help="Route --pptx through Anthropic's own pptx Skill (server-side, "
        "code-execution container) instead of the built-in python-pptx "
        "path. Requires Skills access on the account; no local python-pptx "
        "dependency needed for this mode. Falls back to the regular --pptx "
        "path's behavior if omitted.",
    )

    br = p.add_argument_group("Browse (Claude in Chrome analog)")
    br.add_argument(
        "--browse",
        metavar="URL",
        dest="browse",
        help="Start a headless browsing-agent session at URL. Not the "
        "Claude in Chrome extension — a fetch/decide/navigate loop for "
        "CLI and CI use. Requires --browse-task.",
    )
    br.add_argument(
        "--browse-task", metavar="TEXT", dest="browse_task", help="What to find or do, required with --browse"
    )
    br.add_argument(
        "--browse-max-steps",
        type=int,
        default=6,
        dest="browse_max_steps",
        help="Max fetch/decide iterations (default: 6)",
    )
    br.add_argument(
        "--browse-allow-domain",
        action="append",
        default=None,
        dest="browse_allow_domains",
        metavar="DOMAIN",
        help="Restrict navigation to this domain (repeatable)",
    )

    # Claude Code
    cc = p.add_argument_group("Claude Code")
    cc.add_argument("--code-agent", action="store_true", dest="code_agent")
    cc.add_argument("--code-agent-cwd", default=".", dest="code_agent_cwd")
    cc.add_argument("--code-agent-tools", default="all", dest="code_agent_tools")
    cc.add_argument("--code-agent-permission", default="askPermission", dest="code_agent_permission")
    cc.add_argument("--code-agent-session", metavar="ID", dest="code_agent_session")
    cc.add_argument("--code-agent-resume", metavar="ID", dest="code_agent_resume")
    cc.add_argument("--code-agent-system", metavar="TEXT", dest="code_agent_system")
    cc.add_argument("--code-agent-mcp", nargs="+", metavar="URL", dest="code_agent_mcp")
    cc.add_argument(
        "--code-agent-mcp-tunnel",
        type=int,
        metavar="PORT",
        dest="code_agent_mcp_tunnel",
        help="Open an MCP tunnel to a local MCP server on PORT and print its public URL (research preview)",
    )
    cc.add_argument("--code-agent-list-sessions", action="store_true", dest="code_agent_list_sessions")
    cc.add_argument("--code-agent-list-tools", action="store_true", dest="code_agent_list_tools")
    cc.add_argument("--code-agent-hooks", metavar="FILE", dest="code_agent_hooks")
    cc.add_argument("--code-agent-checkpoint", action="store_true", dest="code_agent_checkpoint")
    cc.add_argument("--code-agent-tenant", metavar="ID", dest="code_agent_tenant")
    cc.add_argument("--code-agent-subagent", metavar="PROMPT", dest="code_agent_subagent")
    cc.add_argument("--code-agent-subagent-turns", metavar="N", type=int, dest="code_agent_subagent_turns")
    cc.add_argument("--code-agent-subagent-cost", metavar="USD", type=float, dest="code_agent_subagent_cost")
    cc.add_argument("--code-agent-subagent-tenant", metavar="ID", dest="code_agent_subagent_tenant")
    cc.add_argument("--code-agent-todo", metavar="PROMPT", dest="code_agent_todo")
    cc.add_argument("--code-agent-slash", metavar="CMD", dest="code_agent_slash")
    cc.add_argument("--code-agent-cost", action="store_true", dest="code_agent_cost")
    cc.add_argument(
        "--code-agent-output", default="stream", dest="code_agent_output", choices=["stream", "json", "text"]
    )
    cc.add_argument(
        "--code-agent-headless",
        action="store_true",
        dest="code_agent_headless",
        help="Non-interactive print mode: run one prompt, print plain text, exit (like `claude -p`)",
    )
    cc.add_argument(
        "--code-agent-output-style",
        metavar="NAME",
        dest="code_agent_output_style",
        help="Apply a named output style (default, explanatory, concise, learning, or custom)",
    )
    cc.add_argument("--list-output-styles", action="store_true", dest="list_output_styles")
    cc.add_argument(
        "--code-agent-sandbox",
        action="store_true",
        dest="code_agent_sandbox",
        help="Run Bash tool calls inside a filesystem+network sandbox",
    )
    cc.add_argument(
        "--code-agent-sandbox-allow-net",
        action="store_true",
        dest="code_agent_sandbox_allow_net",
        help="Allow network access inside the sandbox (default: blocked)",
    )
    cc.add_argument(
        "--code-agent-sandbox-roots",
        nargs="+",
        metavar="PATH",
        dest="code_agent_sandbox_roots",
        help="Extra filesystem roots the sandbox may read/write besides cwd",
    )
    cc.add_argument(
        "--agent-context-editing",
        action="store_true",
        dest="agent_context_editing",
        help="Opt-in context editing (clear_tool_uses) for this agent loop, "
        "complementary to Compaction — clearing drops stale tool results, "
        "Compaction summarizes the whole conversation. Useful for long "
        "--code-agent sessions.",
    )
    cc.add_argument(
        "--no-project-memory",
        action="store_true",
        dest="no_project_memory",
        help="Disable auto-loading of CLAUDE.md project/user memory into the "
        "agent system prompt (load nothing beyond the user memory file)",
    )

    pl = p.add_argument_group("Plugins & Marketplaces")
    pl.add_argument("--plugin-marketplace-add", metavar="PATH_OR_URL", dest="plugin_marketplace_add")
    pl.add_argument("--plugin-marketplace-name", metavar="NAME", dest="plugin_marketplace_name")
    pl.add_argument("--plugin-marketplace-list", action="store_true", dest="plugin_marketplace_list")
    pl.add_argument("--plugin-marketplace-remove", metavar="NAME", dest="plugin_marketplace_remove")
    pl.add_argument("--plugin-install", metavar="NAME[@MARKETPLACE]", dest="plugin_install")
    pl.add_argument(
        "--plugin-dir",
        metavar="PATH",
        dest="plugin_dir",
        help="Install a plugin directly from a local directory or .zip",
    )
    pl.add_argument("--plugin-uninstall", metavar="NAME", dest="plugin_uninstall")
    pl.add_argument("--plugin-list", action="store_true", dest="plugin_list")
    pl.add_argument("--plugin-info", metavar="NAME", dest="plugin_info")
    pl.add_argument("--plugin-enable", metavar="NAME", dest="plugin_enable")
    pl.add_argument("--plugin-disable", metavar="NAME", dest="plugin_disable")

    mem = p.add_argument_group("Memory")
    mem.add_argument("--memory-add", metavar="TEXT", dest="memory_add")
    mem.add_argument(
        "--memory-type", default="fact", choices=["fact", "preference", "event", "task"], dest="memory_type"
    )
    mem.add_argument("--memory-tags", default="", dest="memory_tags")
    mem.add_argument("--memory-importance", type=int, default=5, dest="memory_importance")
    mem.add_argument("--memory-recall", metavar="QUERY", dest="memory_recall")
    mem.add_argument("--memory-forget", metavar="ID", dest="memory_forget")
    mem.add_argument("--memory-stats", action="store_true", dest="memory_stats")
    mem.add_argument("--memory-retention", action="store_true", dest="memory_retention")
    mem.add_argument("--memory-ns", default="default", dest="memory_ns")

    ses = p.add_argument_group("Sessions & Checkpoints")
    ses.add_argument("--sessions-list", action="store_true", dest="sessions_list")
    ses.add_argument("--session-show", metavar="ID", dest="session_show")
    ses.add_argument("--checkpoint-list", metavar="SESSION_ID", dest="checkpoint_list")
    ses.add_argument("--away-summary", metavar="SESSION_ID", dest="away_summary")

    lv = p.add_argument_group("zcoder-live")
    lv.add_argument("--live", action="store_true", dest="live")

    rs = p.add_argument_group("Deep Research")
    rs.add_argument("--research", metavar="TOPIC", dest="research")
    rs.add_argument("--research-depth", type=int, default=4, dest="research_depth")
    rs.add_argument("--research-urls", nargs="*", default=None, dest="research_urls")

    rag = p.add_argument_group("RAG")
    rag.add_argument("--rag-index", metavar="NAME", dest="rag_index")
    rag.add_argument("--rag-folder", metavar="PATH", dest="rag_folder")
    rag.add_argument("--rag-query", metavar="TEXT", dest="rag_query")
    rag.add_argument("--rag-index-name", default="default", dest="rag_index_name")
    rag.add_argument("--rag-list", action="store_true", dest="rag_list")
    rag.add_argument("--rag-k", type=int, default=5, dest="rag_k")
    rag.add_argument(
        "--rag-tenant",
        metavar="ID",
        dest="rag_tenant",
        default="",
        help="Tenant boundary for RAG indexes (SEC-007; required for index/query)",
    )

    ev = p.add_argument_group("Evaluation")
    ev.add_argument("--eval-run", metavar="SUITE_JSON", dest="eval_run")
    ev.add_argument("--eval-compare", nargs=2, metavar=("MODEL_A", "MODEL_B"), dest="eval_compare")
    ev.add_argument("--eval-list", action="store_true", dest="eval_list")
    ev.add_argument("--eval-scaffold", metavar="PATH", dest="eval_scaffold")
    ev.add_argument("--eval-threshold", type=float, default=0.7, dest="eval_threshold")

    gt = p.add_argument_group("Git Integration")
    gt.add_argument("--git-commit", action="store_true", dest="git_commit")
    gt.add_argument(
        "--git-commit-style",
        default="conventional",
        choices=["conventional", "imperative", "detailed"],
        dest="git_commit_style",
    )
    gt.add_argument("--git-commit-write", action="store_true", dest="git_commit_write")
    gt.add_argument("--git-pr", nargs=2, metavar=("BASE", "HEAD"), dest="git_pr")
    gt.add_argument("--git-changelog", metavar="SINCE_TAG", dest="git_changelog")
    gt.add_argument("--git-review", action="store_true", dest="git_review")
    gt.add_argument(
        "--git-blame-explain", nargs=3, metavar=("FILE", "START", "END"), dest="git_blame_explain"
    )

    gh = p.add_argument_group("GitHub Integration")
    gh.add_argument(
        "--gh-review-pr",
        metavar="REPO/NUMBER",
        dest="gh_review_pr",
        help="AI review of a pull request diff, e.g. anthropics/claude-code/42",
    )
    gh.add_argument(
        "--gh-triage-issues",
        metavar="REPO",
        dest="gh_triage_issues",
        help="Triage open issues and suggest labels/owners",
    )
    gh.add_argument(
        "--gh-summarise-commits",
        metavar="REPO",
        dest="gh_summarise_commits",
        help="Summarise recent commit history",
    )
    gh.add_argument(
        "--gh-pr-description",
        metavar="REPO/NUMBER",
        dest="gh_pr_description",
        help="Generate a PR description from a pull request's diff",
    )
    gh.add_argument(
        "--gh-token",
        default="",
        dest="gh_token",
        help="GitHub personal access token (or GITHUB_TOKEN env var)",
    )
    gh.add_argument(
        "--gh-max-items",
        type=int,
        default=20,
        dest="gh_max_items",
        help="Max issues/commits to process for --gh-triage-issues / --gh-summarise-commits (default: 20)",
    )

    ro = p.add_argument_group("Multi-Agent Router")
    ro.add_argument(
        "--route", metavar="PROMPT", dest="route", help="Auto-route PROMPT to the best specialist agent"
    )
    ro.add_argument(
        "--route-explain",
        action="store_true",
        dest="route_explain",
        help="With --route: print which agent was chosen and why",
    )
    ro.add_argument(
        "--route-parallel",
        action="store_true",
        dest="route_parallel",
        help="With --route: fan out to ALL agents and synthesise the best answer",
    )
    ro.add_argument(
        "--route-list", action="store_true", dest="route_list", help="List all agents in the routing table"
    )

    co = p.add_argument_group("Cost Optimizer")
    co.add_argument("--optimized", metavar="PROMPT", dest="optimized")
    co.add_argument("--force-model", default=None, dest="force_model")
    co.add_argument("--cost-summary", action="store_true", dest="cost_summary")
    co.add_argument("--cost-reset", action="store_true", dest="cost_reset")

    po = p.add_argument_group("Prompt Optimizer")
    po.add_argument(
        "--optimize",
        metavar="PROMPT",
        dest="prompt_optimize",
        help="Rewrite a prompt to be clearer and more effective",
    )
    po.add_argument(
        "--score-prompt",
        metavar="PROMPT",
        dest="score_prompt",
        help="Score a prompt 0-100 for clarity, specificity, and completeness",
    )
    po.add_argument(
        "--ab-test",
        action="store_true",
        dest="ab_test",
        help="With --prompt and --ab-prompt-b: A/B test two prompt variants against --ab-task",
    )
    po.add_argument(
        "--ab-prompt-b",
        metavar="PROMPT_B",
        default="",
        dest="ab_prompt_b",
        help="Second prompt variant for --ab-test (first variant is --prompt)",
    )
    po.add_argument(
        "--ab-task",
        metavar="TASK",
        default="",
        dest="ab_task",
        help="Task description to judge both --ab-test variants against",
    )
    po.add_argument(
        "--prompt-lib-add",
        action="store_true",
        dest="prompt_lib_add",
        help="Save --prompt to the library under --tag",
    )
    po.add_argument(
        "--prompt-lib-list", action="store_true", dest="prompt_lib_list", help="List saved prompts"
    )
    po.add_argument(
        "--prompt-lib-get", metavar="TAG", dest="prompt_lib_get", help="Print a saved prompt by tag"
    )

    ob = p.add_argument_group("Observability")
    ob.add_argument("--obs-latency", action="store_true", dest="obs_latency")
    ob.add_argument("--obs-errors", action="store_true", dest="obs_errors")
    ob.add_argument("--obs-tail", type=int, nargs="?", const=20, default=None, dest="obs_tail")
    ob.add_argument("--obs-clear", action="store_true", dest="obs_clear")
    ob.add_argument("--obs-hours", type=int, default=24, dest="obs_hours")

    mt = p.add_argument_group("Metrics (local usage log)")
    mt.add_argument(
        "--metrics-show",
        action="store_true",
        dest="metrics_show",
        help="Show usage summary (calls, cost, tokens) across all logged calls",
    )
    mt.add_argument(
        "--metrics-today",
        action="store_true",
        dest="metrics_today",
        help="With --metrics-show: limit to today's calls",
    )
    mt.add_argument(
        "--metrics-model",
        default="",
        dest="metrics_model",
        help="With --metrics-show: filter summary to one model",
    )
    mt.add_argument(
        "--metrics-clear", action="store_true", dest="metrics_clear", help="Clear the local metrics log"
    )
    mt.add_argument(
        "--metrics-export",
        metavar="FILE",
        dest="metrics_export",
        help="Export the full metrics log to FILE as JSON",
    )

    wf = p.add_argument_group("Workflows")
    wf.add_argument("--workflow-run", metavar="PATH", dest="workflow_run")
    wf.add_argument("--workflow-input", default="", dest="workflow_input")
    wf.add_argument("--workflow-scaffold", metavar="PATH", dest="workflow_scaffold")

    hk = p.add_argument_group("Hooks")
    hk.add_argument("--hooks-add", nargs=2, metavar=("EVENT", "COMMAND"), dest="hooks_add")
    hk.add_argument("--hook-tool-match", default=None, dest="hook_tool_match")
    hk.add_argument("--hooks-list", action="store_true", dest="hooks_list")
    hk.add_argument("--hooks-remove", type=int, metavar="INDEX", dest="hooks_remove")

    pm = p.add_argument_group("Permissions")
    pm.add_argument("--perms-list", action="store_true", dest="perms_list")
    pm.add_argument("--perms-add", nargs=2, metavar=("PATTERN", "DECISION"), dest="perms_add")
    pm.add_argument("--perms-reason", default="", dest="perms_reason")

    pln = p.add_argument_group("Plan Mode")
    pln.add_argument("--plan", metavar="TASK", dest="plan")
    pln.add_argument("--plan-context", default="", dest="plan_context")
    pln.add_argument("--plan-execute", action="store_true", dest="plan_execute")

    se = p.add_argument_group("Settings")
    se.add_argument("--settings-show", action="store_true", dest="settings_show")
    se.add_argument("--status-line", action="store_true", dest="status_line")

    return p


def main():
    from zcoder.config.logging import new_correlation_id, setup_logging

    setup_logging()
    new_correlation_id()

    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        print(BANNER)
        return

    if getattr(args, "health_check", False):
        import json as _json

        from zcoder.core.health import run_health_check

        report = run_health_check(deep=getattr(args, "health_check_deep", False))
        print(_json.dumps(report.to_dict(), indent=2))
        sys.exit(0 if report.healthy else 1)

    # ── No-key listing ──
    if args.list_skills:
        from zcoder.services.skills import SkillManager

        for s in SkillManager().list_skills():
            print(f"  {s['name']:<25} — {s['description']}")
        return
    if args.list_agents:
        # Was a second, independent hardcoded list of the same seven names
        # with no data behind them; now sourced from AGENT_SYSTEM_PROMPTS,
        # the same table --agent actually uses, so the two can't drift.
        for n, sys_prompt in sorted(AGENT_SYSTEM_PROMPTS.items()):
            print(f"  {n:<25} — {sys_prompt}")
        return
    if args.list_personalities:
        from zcoder.claude.personalities import PersonalityManager

        for p_ in PersonalityManager().list_personalities():
            print(f"  {p_['name']:<12} — {p_['description']}")
        return

    # ── Plugins & Marketplaces (no API key required) ──
    if args.plugin_marketplace_add:
        from zcoder.claude.tools.plugins import cmd_plugin_marketplace_add

        cmd_plugin_marketplace_add(args.plugin_marketplace_add, args.plugin_marketplace_name)
        return
    if args.plugin_marketplace_list:
        from zcoder.claude.tools.plugins import cmd_plugin_marketplace_list

        cmd_plugin_marketplace_list()
        return
    if args.plugin_marketplace_remove:
        from zcoder.claude.tools.plugins import cmd_plugin_marketplace_remove

        cmd_plugin_marketplace_remove(args.plugin_marketplace_remove)
        return
    if args.plugin_install:
        from zcoder.claude.tools.plugins import cmd_plugin_install

        cmd_plugin_install(args.plugin_install)
        return
    if args.plugin_dir:
        from zcoder.claude.tools.plugins import cmd_plugin_install_dir

        cmd_plugin_install_dir(args.plugin_dir)
        return
    if args.plugin_uninstall:
        from zcoder.claude.tools.plugins import cmd_plugin_uninstall

        cmd_plugin_uninstall(args.plugin_uninstall)
        return
    if args.plugin_list:
        from zcoder.claude.tools.plugins import cmd_plugin_list

        cmd_plugin_list()
        return
    if args.plugin_info:
        from zcoder.claude.tools.plugins import cmd_plugin_info

        cmd_plugin_info(args.plugin_info)
        return
    if args.plugin_enable:
        from zcoder.claude.tools.plugins import cmd_plugin_enable

        cmd_plugin_enable(args.plugin_enable)
        return
    if args.plugin_disable:
        from zcoder.claude.tools.plugins import cmd_plugin_disable

        cmd_plugin_disable(args.plugin_disable)
        return

    # ── Settings (no API key required) ──
    if args.settings_show:
        from zcoder.claude.enterprise.settings import cmd_settings_show

        cmd_settings_show()
        return
    if args.status_line:
        from zcoder.claude.enterprise.settings import cmd_status_line

        cmd_status_line(model=args.model or "claude-sonnet-5", cwd=args.code_agent_cwd)
        return
    if args.list_output_styles:
        from zcoder.claude.eval.output_styles import cmd_list_output_styles

        cmd_list_output_styles()
        return

    if args.fable5_info:
        from zcoder.claude.models.fable5 import cmd_fable5_info

        cmd_fable5_info()
        return

    if args.mythos5_info:
        from zcoder.claude.models.mythos5 import cmd_mythos5_info

        cmd_mythos5_info()
        return

    if args.opus5_info:
        from zcoder.claude.models.opus5 import cmd_opus5_info

        cmd_opus5_info()
        return

    if args.sonnet5_info:
        from zcoder.claude.models.sonnet5 import cmd_sonnet5_info

        cmd_sonnet5_info()
        return

    if args.sonnet5_cost:
        from zcoder.claude.models.sonnet5 import cmd_sonnet5_cost

        cmd_sonnet5_cost(args.sonnet5_cost)
        return

    if args.haiku45_info:
        from zcoder.claude.models.haiku45 import cmd_haiku45_info

        cmd_haiku45_info()
        return

    if args.skills_list:
        from zcoder.claude.enterprise.skills import cmd_skills_list

        cmd_skills_list()
        return
    if args.skills_info:
        from zcoder.claude.enterprise.skills import cmd_skills_info

        cmd_skills_info(args.skills_info)
        return

    if (
        args.usage_report
        or args.cost_report
        or args.admin_list_keys
        or args.admin_revoke_key
        or args.admin_create_key
        or args.spend_limits_list
        or args.spend_limit_set
        or args.spend_limit_get
        or args.spend_limit_delete
        or args.spend_limit_requests_list
        or args.spend_limit_request_approve
        or args.spend_limit_request_deny
        or args.rate_limits
        or args.rate_limits_workspace
        or args.claude_code_usage_report
        or args.cmek_list
    ):
        admin_key = args.admin_api_key or os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        if args.admin_create_key:
            from zcoder.claude.enterprise.admin_api import cmd_admin_create_key

            cmd_admin_create_key(args.admin_create_key)
            return
        if not admin_key:
            print(
                "[ERROR] This requires an Admin API key: pass --admin-api-key or set ANTHROPIC_ADMIN_API_KEY",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.usage_report:
            from zcoder.claude.enterprise.admin_api import cmd_usage_report

            cmd_usage_report(
                admin_key,
                start=args.usage_report_start,
                end=args.usage_report_end,
                group_by=args.usage_report_group_by,
            )
            return
        if args.cost_report:
            from zcoder.claude.enterprise.admin_api import cmd_cost_report

            cmd_cost_report(
                admin_key,
                start=args.cost_report_start,
                end=args.cost_report_end,
                group_by=args.cost_report_group_by,
            )
            return
        if args.admin_list_keys:
            from zcoder.claude.enterprise.admin_api import cmd_admin_list_keys

            cmd_admin_list_keys(admin_key)
            return
        if args.admin_revoke_key:
            from zcoder.claude.enterprise.admin_api import cmd_admin_revoke_key

            cmd_admin_revoke_key(admin_key, args.admin_revoke_key)
            return
        if args.spend_limits_list:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limits_list

            cmd_spend_limits_list(admin_key)
            return
        if args.spend_limit_set:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limit_set

            user_id, amount = args.spend_limit_set
            cmd_spend_limit_set(user_id, amount, admin_key)
            return
        if args.spend_limit_get:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limit_get

            cmd_spend_limit_get(args.spend_limit_get, admin_key)
            return
        if args.spend_limit_delete:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limit_delete

            cmd_spend_limit_delete(args.spend_limit_delete, admin_key)
            return
        if args.spend_limit_requests_list:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limits_requests_list

            cmd_spend_limits_requests_list(admin_key, status=args.spend_limit_status or None)
            return
        if args.spend_limit_request_approve:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limit_request_approve

            cmd_spend_limit_request_approve(args.spend_limit_request_approve, admin_key)
            return
        if args.spend_limit_request_deny:
            from zcoder.claude.enterprise.admin_api import cmd_spend_limit_request_deny

            cmd_spend_limit_request_deny(args.spend_limit_request_deny, admin_key)
            return
        if args.rate_limits_workspace:
            from zcoder.claude.enterprise.admin_api import cmd_rate_limits_workspace

            cmd_rate_limits_workspace(args.rate_limits_workspace, admin_key)
            return
        if args.rate_limits:
            from zcoder.claude.enterprise.admin_api import cmd_rate_limits

            cmd_rate_limits(admin_key, model=args.rate_limits_model or None)
            return
        if args.claude_code_usage_report:
            from zcoder.claude.enterprise.admin_api import cmd_claude_code_usage_report

            starting_at = args.claude_code_usage_report_start
            if not starting_at:
                import datetime as _dt

                starting_at = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            cmd_claude_code_usage_report(admin_key, starting_at)
            return
        if args.cmek_list:
            from zcoder.claude.enterprise.admin_api import cmd_cmek_list

            cmd_cmek_list(admin_key, workspace_id=args.cmek_workspace or None)
            return

    if (
        args.members_list
        or args.member_get
        or args.member_role_set
        or args.member_remove
        or args.invite_create
        or args.invites_list
        or args.invite_withdraw
        or args.groups_list
        or args.group_create
        or args.group_delete
        or args.group_members_list
        or args.group_member_add
        or args.group_member_remove
        or args.roles_list
        or args.role_permissions
    ):
        admin_key = args.admin_api_key or os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        if not admin_key:
            print(
                "[ERROR] This requires an Admin API key: pass --admin-api-key or set ANTHROPIC_ADMIN_API_KEY",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.members_list:
            from zcoder.claude.enterprise.admin_api import cmd_members_list

            cmd_members_list(admin_key, email=args.members_email or None)
            return
        if args.member_get:
            from zcoder.claude.enterprise.admin_api import cmd_member_get

            cmd_member_get(args.member_get, admin_key)
            return
        if args.member_role_set:
            from zcoder.claude.enterprise.admin_api import cmd_member_role_set

            user_id, role = args.member_role_set
            cmd_member_role_set(user_id, role, admin_key)
            return
        if args.member_remove:
            from zcoder.claude.enterprise.admin_api import cmd_member_remove

            cmd_member_remove(args.member_remove, admin_key)
            return
        if args.invite_create:
            from zcoder.claude.enterprise.admin_api import cmd_invite_create

            email, role = args.invite_create
            rbac_group_ids = (
                [g.strip() for g in args.invite_rbac_groups.split(",") if g.strip()]
                if args.invite_rbac_groups
                else None
            )
            cmd_invite_create(email, role, admin_key, rbac_group_ids=rbac_group_ids)
            return
        if args.invites_list:
            from zcoder.claude.enterprise.admin_api import cmd_invites_list

            cmd_invites_list(admin_key)
            return
        if args.invite_withdraw:
            from zcoder.claude.enterprise.admin_api import cmd_invite_withdraw

            cmd_invite_withdraw(args.invite_withdraw, admin_key)
            return
        if args.groups_list:
            from zcoder.claude.enterprise.admin_api import cmd_groups_list

            cmd_groups_list(admin_key)
            return
        if args.group_create:
            from zcoder.claude.enterprise.admin_api import cmd_group_create

            cmd_group_create(args.group_create, admin_key)
            return
        if args.group_delete:
            from zcoder.claude.enterprise.admin_api import cmd_group_delete

            cmd_group_delete(args.group_delete, admin_key)
            return
        if args.group_members_list:
            from zcoder.claude.enterprise.admin_api import cmd_group_members_list

            cmd_group_members_list(args.group_members_list, admin_key)
            return
        if args.group_member_add:
            from zcoder.claude.enterprise.admin_api import cmd_group_member_add

            group_id, user_id = args.group_member_add
            cmd_group_member_add(group_id, user_id, admin_key)
            return
        if args.group_member_remove:
            from zcoder.claude.enterprise.admin_api import cmd_group_member_remove

            group_id, user_id = args.group_member_remove
            cmd_group_member_remove(group_id, user_id, admin_key)
            return
        if args.roles_list:
            from zcoder.claude.enterprise.admin_api import cmd_roles_list

            cmd_roles_list(admin_key)
            return
        if args.role_permissions:
            from zcoder.claude.enterprise.admin_api import cmd_role_permissions_list

            cmd_role_permissions_list(args.role_permissions, admin_key)
            return

    if (
        args.wif_exchange_token
        or args.wif_status
        or args.wif_create_service_account
        or args.wif_list_service_accounts
        or args.wif_create_issuer
        or args.wif_list_issuers
        or args.wif_create_rule
        or args.wif_list_rules
    ):
        if args.wif_status:
            from zcoder.claude.integrations.wif import cmd_wif_status

            cmd_wif_status()
            return
        if args.wif_exchange_token:
            from zcoder.claude.integrations.wif import cmd_wif_exchange_token

            cmd_wif_exchange_token()
            return
        org_admin_token = args.org_admin_token or os.environ.get("ANTHROPIC_ORG_ADMIN_TOKEN")
        if not org_admin_token:
            print(
                "[ERROR] This requires an org:admin OAuth token: pass --org-admin-token or "
                "set ANTHROPIC_ORG_ADMIN_TOKEN",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.wif_create_service_account:
            from zcoder.claude.integrations.wif import cmd_wif_create_service_account

            cmd_wif_create_service_account(args.wif_create_service_account, org_admin_token)
            return
        if args.wif_list_service_accounts:
            from zcoder.claude.integrations.wif import cmd_wif_list_service_accounts

            cmd_wif_list_service_accounts(org_admin_token)
            return
        if args.wif_create_issuer:
            from zcoder.claude.integrations.wif import cmd_wif_create_issuer

            if not args.wif_issuer_url:
                print("[ERROR] --wif-create-issuer requires --wif-issuer-url")
                sys.exit(1)
            cmd_wif_create_issuer(args.wif_create_issuer, args.wif_issuer_url, org_admin_token)
            return
        if args.wif_list_issuers:
            from zcoder.claude.integrations.wif import cmd_wif_list_issuers

            cmd_wif_list_issuers(org_admin_token)
            return
        if args.wif_create_rule:
            from zcoder.claude.integrations.wif import cmd_wif_create_rule

            if not (args.wif_rule_issuer and args.wif_rule_service_account and args.wif_rule_subject_prefix):
                print(
                    "[ERROR] --wif-create-rule requires --wif-rule-issuer, "
                    "--wif-rule-service-account, and --wif-rule-subject-prefix"
                )
                sys.exit(1)
            cmd_wif_create_rule(
                args.wif_create_rule,
                args.wif_rule_issuer,
                args.wif_rule_service_account,
                args.wif_rule_subject_prefix,
                org_admin_token,
            )
            return
        if args.wif_list_rules:
            from zcoder.claude.integrations.wif import cmd_wif_list_rules

            cmd_wif_list_rules(org_admin_token)
            return

    _compliance_flags = (
        args.compliance_activities,
        args.compliance_chats_list,
        args.compliance_chat_messages,
        args.compliance_chat_delete,
        args.compliance_file_download,
        args.compliance_file_delete,
        args.compliance_projects_list,
        args.compliance_project_info,
        args.compliance_project_attachments,
        args.compliance_project_delete,
        args.compliance_orgs_list,
        args.compliance_org_users,
        args.compliance_org_roles,
        args.compliance_org_settings,
        args.compliance_groups_list,
        args.compliance_group_members,
        args.compliance_local_sessions_list,
        args.compliance_local_session_info,
        args.compliance_local_session_messages,
    )
    if any(_compliance_flags):
        compliance_key = (
            args.compliance_api_key
            or os.environ.get("ANTHROPIC_COMPLIANCE_API_KEY")
            or args.admin_api_key
            or os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        )
        if not compliance_key:
            print(
                "[ERROR] This requires a Compliance Access Key or Admin API key: pass "
                "--compliance-api-key or set ANTHROPIC_COMPLIANCE_API_KEY (or "
                "--admin-api-key / ANTHROPIC_ADMIN_API_KEY for Activity-Feed-only access)",
                file=sys.stderr,
            )
            sys.exit(1)
        activity_types = args.compliance_activity_types.split(",") if args.compliance_activity_types else None
        user_ids = args.compliance_user_ids.split(",") if args.compliance_user_ids else None

        if args.compliance_activities:
            from zcoder.claude.enterprise.compliance import cmd_compliance_activities

            cmd_compliance_activities(
                compliance_key,
                since=args.compliance_activities_since,
                until=args.compliance_activities_until,
                activity_types=activity_types,
                limit=args.compliance_activities_limit,
                all_pages=args.compliance_activities_all,
            )
            return
        if args.compliance_chats_list:
            from zcoder.claude.enterprise.compliance import cmd_compliance_chats_list

            if not user_ids:
                print("[ERROR] --compliance-chats-list requires --compliance-user-ids", file=sys.stderr)
                sys.exit(1)
            cmd_compliance_chats_list(compliance_key, user_ids)
            return
        if args.compliance_chat_messages:
            from zcoder.claude.enterprise.compliance import cmd_compliance_chat_messages

            cmd_compliance_chat_messages(compliance_key, args.compliance_chat_messages)
            return
        if args.compliance_chat_delete:
            from zcoder.claude.enterprise.compliance import cmd_compliance_chat_delete

            cmd_compliance_chat_delete(compliance_key, args.compliance_chat_delete, yes=args.compliance_yes)
            return
        if args.compliance_file_download:
            from zcoder.claude.enterprise.compliance import cmd_compliance_file_download

            cmd_compliance_file_download(
                compliance_key, args.compliance_file_download, output_path=args.compliance_output
            )
            return
        if args.compliance_file_delete:
            from zcoder.claude.enterprise.compliance import cmd_compliance_file_delete

            cmd_compliance_file_delete(compliance_key, args.compliance_file_delete, yes=args.compliance_yes)
            return
        if args.compliance_projects_list:
            from zcoder.claude.enterprise.compliance import cmd_compliance_projects_list

            cmd_compliance_projects_list(compliance_key)
            return
        if args.compliance_project_info:
            from zcoder.claude.enterprise.compliance import cmd_compliance_project_info

            cmd_compliance_project_info(compliance_key, args.compliance_project_info)
            return
        if args.compliance_project_attachments:
            from zcoder.claude.enterprise.compliance import cmd_compliance_project_attachments

            cmd_compliance_project_attachments(compliance_key, args.compliance_project_attachments)
            return
        if args.compliance_project_delete:
            from zcoder.claude.enterprise.compliance import cmd_compliance_project_delete

            cmd_compliance_project_delete(
                compliance_key, args.compliance_project_delete, yes=args.compliance_yes
            )
            return
        if args.compliance_orgs_list:
            from zcoder.claude.enterprise.compliance import cmd_compliance_orgs_list

            cmd_compliance_orgs_list(compliance_key)
            return
        if args.compliance_org_users:
            from zcoder.claude.enterprise.compliance import cmd_compliance_org_users

            cmd_compliance_org_users(compliance_key, args.compliance_org_users)
            return
        if args.compliance_org_roles:
            from zcoder.claude.enterprise.compliance import cmd_compliance_org_roles

            cmd_compliance_org_roles(compliance_key, args.compliance_org_roles)
            return
        if args.compliance_org_settings:
            from zcoder.claude.enterprise.compliance import cmd_compliance_org_settings

            cmd_compliance_org_settings(compliance_key, args.compliance_org_settings)
            return
        if args.compliance_groups_list:
            from zcoder.claude.enterprise.compliance import cmd_compliance_groups_list

            cmd_compliance_groups_list(compliance_key)
            return
        if args.compliance_group_members:
            from zcoder.claude.enterprise.compliance import cmd_compliance_group_members

            cmd_compliance_group_members(compliance_key, args.compliance_group_members)
            return
        if args.compliance_local_sessions_list:
            from zcoder.claude.enterprise.compliance import cmd_compliance_local_sessions_list

            cmd_compliance_local_sessions_list(compliance_key, user_ids=user_ids)
            return
        if args.compliance_local_session_info:
            from zcoder.claude.enterprise.compliance import cmd_compliance_local_session_info

            cmd_compliance_local_session_info(compliance_key, args.compliance_local_session_info)
            return
        if args.compliance_local_session_messages:
            from zcoder.claude.enterprise.compliance import cmd_compliance_local_session_messages

            cmd_compliance_local_session_messages(compliance_key, args.compliance_local_session_messages)
            return

    if args.check_deprecated:
        from zcoder.claude.models.registry import cmd_check_deprecated

        cmd_check_deprecated(args.check_deprecated)
        return
    if args.upgrade_all:
        from zcoder.claude.models.registry import cmd_upgrade_all

        cmd_upgrade_all(
            args.upgrade_all,
            target=args.upgrade_target,
            apply=args.upgrade_yes,
            no_backup=args.upgrade_no_backup,
        )
        return

    if args.project_list:
        from zcoder.services.projects import cmd_project_list

        cmd_project_list()
        return
    if args.project_templates:
        from zcoder.services.projects import cmd_project_templates

        cmd_project_templates()
        return
    if args.project_show:
        from zcoder.services.projects import cmd_project_show

        cmd_project_show(args.project_show)
        return
    if args.project_delete:
        from zcoder.services.projects import ProjectManager

        ProjectManager().delete_project(args.project_delete)
        print("✓ Deleted.")
        return
    if args.project_archive:
        from zcoder.services.projects import ProjectManager

        ProjectManager().archive_project(args.project_archive)
        print("✓ Archived.")
        return
    if args.project_create:
        from zcoder.services.projects import cmd_project_create

        cmd_project_create(args.project_create, args.project_desc, args.project_template)
        return
    if args.project_add_task:
        from zcoder.services.projects import cmd_project_add_task

        cmd_project_add_task(
            args.project_add_task,
            args.task_title or args.prompt or "",
            args.task_desc,
            args.task_agent,
            args.task_priority,
        )
        return
    if args.artifact_types:
        from zcoder.infrastructure.artifacts import cmd_artifact_types

        cmd_artifact_types()
        return
    if args.artifact_list:
        from zcoder.infrastructure.artifacts import cmd_artifact_list

        cmd_artifact_list(
            query=args.artifact_query,
            artifact_type=args.artifact_type if args.artifact_type != "code" else "",
            project_id=args.artifact_project,
            tag=args.tag,
        )
        return
    if args.artifact_show:
        from zcoder.infrastructure.artifacts import cmd_artifact_show

        cmd_artifact_show(args.artifact_show, args.artifact_version)
        return
    if args.artifact_export:
        from zcoder.infrastructure.artifacts import cmd_artifact_export

        cmd_artifact_export(args.artifact_export, args.output or "", args.artifact_version)
        return
    if args.artifact_export_all:
        from zcoder.infrastructure.artifacts import cmd_artifact_export_all

        cmd_artifact_export_all(args.artifact_export_all, args.artifact_output_dir)
        return
    if args.artifact_diff:
        from zcoder.infrastructure.artifacts import cmd_artifact_diff

        cmd_artifact_diff(args.artifact_diff, args.v1, args.v2)
        return
    if args.artifact_delete:
        from zcoder.infrastructure.artifacts import cmd_artifact_delete

        cmd_artifact_delete(args.artifact_delete)
        return
    if args.artifact_tag:
        from zcoder.infrastructure.artifacts import cmd_artifact_tag

        cmd_artifact_tag(args.artifact_tag, args.tag)
        return
    if args.artifact_attach:
        from zcoder.infrastructure.artifacts import cmd_artifact_attach

        cmd_artifact_attach(args.artifact_attach, args.to_project)
        return
    if args.list_server_tools:
        from zcoder.claude.tools.registry import cmd_list_server_tools

        cmd_list_server_tools()
        return

    if args.mid_conv_tool_check:
        from zcoder.claude.tools.registry import (
            MID_CONVERSATION_TOOL_CHANGES_SUPPORTED,
            validate_mid_conversation_tool_change,
        )

        model_id = args.mid_conv_tool_check
        warning = validate_mid_conversation_tool_change(model_id)
        if warning is None:
            print(
                f"\033[92m✓ {model_id} supports mid-conversation tool changes\033[0m "
                f"(mid-conversation-tool-changes-2026-07-01 beta)"
            )
        else:
            print(f"\033[93m⚠ {warning}\033[0m")
            print(f"  Supported models: {', '.join(sorted(MID_CONVERSATION_TOOL_CHANGES_SUPPORTED))}")
        return
    if args.cowork_list:
        from zcoder.services.cowork import cmd_cowork_list

        cmd_cowork_list()
        return
    if args.agent_list_sessions:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_list_sessions

        cmd_agent_list_sessions()
        return
    if args.list_tool_presets:
        from zcoder.claude.orchestration.agents_sdk import cmd_list_tool_presets

        cmd_list_tool_presets()
        return
    if args.code_agent_list_sessions:
        from zcoder.claude.capabilities.code import cmd_code_list_sessions

        cmd_code_list_sessions()
        return
    if args.code_agent_list_tools:
        from zcoder.claude.capabilities.code import cmd_code_list_tools

        cmd_code_list_tools()
        return

    # ── New in v1.10.0 — no API key required ──
    if args.memory_add:
        from zcoder.claude.memory.memory import cmd_memory_add

        cmd_memory_add(
            args.memory_add, args.memory_type, args.memory_tags, args.memory_importance, args.memory_ns
        )
        return
    if args.memory_recall:
        from zcoder.claude.memory.memory import cmd_memory_recall

        cmd_memory_recall(args.memory_recall, args.memory_ns)
        return
    if args.memory_forget:
        from zcoder.claude.memory.memory import cmd_memory_forget

        cmd_memory_forget(args.memory_forget, args.memory_ns)
        return
    if args.memory_stats:
        from zcoder.claude.memory.memory import cmd_memory_stats

        cmd_memory_stats(args.memory_ns)
        return
    if args.memory_retention:
        from zcoder.claude.memory.memory import cmd_memory_retention

        cmd_memory_retention(args.memory_ns)
        return
    if args.sessions_list:
        from zcoder.claude.orchestration.sessions import cmd_sessions_list

        cmd_sessions_list()
        return
    if args.session_show:
        from zcoder.claude.orchestration.sessions import cmd_session_show

        cmd_session_show(args.session_show)
        return
    if args.checkpoint_list:
        from zcoder.claude.orchestration.sessions import cmd_checkpoint_list

        cmd_checkpoint_list(args.checkpoint_list)
        return
    if args.away_summary:
        from zcoder.claude.orchestration.sessions import cmd_away_summary

        cmd_away_summary(args.away_summary)
        return
    if args.rag_index and args.rag_folder:
        from zcoder.claude.rag.engine import cmd_rag_index

        cmd_rag_index(args.rag_index, args.rag_folder, tenant_id=args.rag_tenant)
        return
    if args.rag_list:
        from zcoder.claude.rag.engine import cmd_rag_list

        cmd_rag_list(tenant_id=args.rag_tenant)
        return
    if args.eval_list:
        from zcoder.claude.eval.eval import cmd_eval_list

        cmd_eval_list()
        return
    if args.eval_scaffold:
        from zcoder.claude.eval.eval import cmd_eval_scaffold

        cmd_eval_scaffold(args.eval_scaffold)
        return
    if args.cost_summary:
        from zcoder.claude.optimization.cost import cmd_cost_summary

        cmd_cost_summary()
        return
    if args.cost_reset:
        from zcoder.claude.optimization.cost import cmd_cost_reset

        cmd_cost_reset()
        return
    if args.metrics_show:
        from zcoder.claude.enterprise.metrics import cmd_metrics_show

        cmd_metrics_show(today_only=args.metrics_today, model_filter=args.metrics_model or None)
        return
    if args.metrics_clear:
        from zcoder.claude.enterprise.metrics import cmd_metrics_clear

        cmd_metrics_clear()
        return
    if args.metrics_export:
        from zcoder.claude.enterprise.metrics import cmd_metrics_export

        cmd_metrics_export(args.metrics_export, today_only=args.metrics_today)
        return
    if args.obs_latency:
        from zcoder.claude.observability import cmd_obs_latency

        cmd_obs_latency(args.obs_hours)
        return
    if args.obs_tail is not None:
        from zcoder.claude.observability import cmd_obs_tail

        cmd_obs_tail(args.obs_tail)
        return
    if args.obs_clear:
        from zcoder.claude.observability import cmd_obs_clear

        cmd_obs_clear()
        return
    if args.workflow_scaffold:
        from zcoder.claude.orchestration.workflow import cmd_workflow_scaffold

        cmd_workflow_scaffold(args.workflow_scaffold)
        return
    if args.hooks_add:
        from zcoder.claude.enterprise.hooks_perms import cmd_hooks_add

        cmd_hooks_add(args.hooks_add[0], args.hooks_add[1], args.hook_tool_match)
        return
    if args.hooks_list:
        from zcoder.claude.enterprise.hooks_perms import cmd_hooks_list

        cmd_hooks_list()
        return
    if args.hooks_remove is not None:
        from zcoder.claude.enterprise.hooks_perms import cmd_hooks_remove

        cmd_hooks_remove(args.hooks_remove)
        return
    if args.perms_list:
        from zcoder.claude.enterprise.hooks_perms import cmd_perms_list

        cmd_perms_list()
        return
    if args.perms_add:
        from zcoder.claude.enterprise.hooks_perms import cmd_perms_add

        cmd_perms_add(args.perms_add[0], args.perms_add[1], args.perms_reason)
        return

    if args.tui:
        from zcoder.interfaces.cli.tui import run_tui

        run_tui(api_key=getattr(args, "api_key", None) or os.getenv("ANTHROPIC_API_KEY", ""))
        return

    # ── API key required ──
    key = _api_key(args)
    model = _model(args)

    if args.interactive:
        from zcoder.claude.orchestration.interactive import cmd_interactive

        cmd_interactive(
            key,
            model,
            system=args.interactive_system,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            personality_style=args.personality,
        )
        return

    if args.excel is not None:
        from zcoder.claude.integrations.excel import cmd_excel_chat

        cmd_excel_chat(
            key,
            model,
            input_path=args.excel or None,
            output_path=args.excel_output,
            sheet_name=args.excel_sheet,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            native=args.excel_native,
        )
        return

    if args.pptx is not None:
        from zcoder.claude.integrations.powerpoint import cmd_pptx_chat

        cmd_pptx_chat(
            key,
            model,
            input_path=args.pptx or None,
            output_path=args.pptx_output,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            native=args.pptx_native,
        )
        return

    if args.browse:
        if not args.browse_task:
            print("[ERROR] --browse requires --browse-task", file=sys.stderr)
            sys.exit(1)
        from zcoder.claude.integrations.chrome import cmd_browse

        cmd_browse(
            key,
            model,
            args.browse,
            args.browse_task,
            max_steps=args.browse_max_steps,
            allowed_domains=args.browse_allow_domains,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        return

    if args.list_models:
        from zcoder.claude.models.registry import cmd_list_models

        cmd_list_models(key, include_legacy=getattr(args, "list_models_legacy", False))
        return
    if args.model_info:
        from zcoder.claude.models.registry import cmd_model_info

        cmd_model_info(args.model_info, key)
        return
    if args.fable5:
        from zcoder.claude.models.fable5 import cmd_fable5_call, parse_fallback_chain

        try:
            chain = parse_fallback_chain(getattr(args, "fable5_fallback_chain", None))
        except ValueError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        cmd_fable5_call(
            args.fable5,
            key,
            fallback_model=args.fallback_model,
            allow_fallback=not args.fable5_no_fallback,
            fallback_chain=chain,
        )
        return
    if args.mythos5:
        from zcoder.claude.models.mythos5 import cmd_mythos5_call

        cmd_mythos5_call(args.mythos5, key)
        return
    if args.opus5:
        from zcoder.claude.models.opus5 import cmd_opus5_call

        cmd_opus5_call(
            args.opus5,
            key,
            effort=args.opus5_effort,
            disable_thinking=args.opus5_disable_thinking,
            fast=args.opus5_fast,
            use_geo=args.opus5_geo,
        )
        return
    if args.sonnet5:
        from zcoder.claude.models.sonnet5 import cmd_sonnet5_call

        cmd_sonnet5_call(args.sonnet5, key, use_geo=args.sonnet5_geo)
        return
    if args.haiku45:
        from zcoder.claude.models.haiku45 import cmd_haiku45_call

        cmd_haiku45_call(args.haiku45, key, thinking_budget=args.haiku45_thinking_budget)
        return

    # ── zai-live ──
    if args.live:
        from zcoder.claude.orchestration.live import cmd_live

        # --temperature was accepted by the parser but never reached cmd_live,
        # so live mode always used LiveSession's 0.7 default regardless of the
        # flag. Now threaded through (still safely dropped by sampling_kwargs()
        # for claude-sonnet-5 and later, which reject it).
        cmd_live(key, model=model, temperature=args.temperature)
        return

    # ── Deep Research ──
    if args.research:
        from zcoder.claude.rag.research import cmd_research

        cmd_research(
            args.research,
            key,
            model,
            depth=args.research_depth,
            source_urls=args.research_urls,
            output=args.output,
        )
        return

    # ── RAG (query needs the key for generation; index/list handled above) ──
    if args.rag_query:
        from zcoder.claude.rag.engine import cmd_rag_query

        cmd_rag_query(
            args.rag_index_name, args.rag_query, key, model, k=args.rag_k, tenant_id=args.rag_tenant
        )
        return

    # ── Evaluation (run/compare call the model; list/scaffold handled above) ──
    if args.eval_run:
        from zcoder.claude.eval.eval import cmd_eval_run

        cmd_eval_run(args.eval_run, key, model, threshold=args.eval_threshold, output=args.output)
        return
    if args.eval_compare:
        from zcoder.claude.eval.eval import cmd_eval_compare

        cmd_eval_compare(
            args.eval_run or args.eval_scaffold or "", args.eval_compare[0], args.eval_compare[1], key
        )
        return

    # ── Git Integration ──
    if args.git_commit:
        from zcoder.claude.integrations.git import cmd_git_commit

        cmd_git_commit(key, model, style=args.git_commit_style, write=args.git_commit_write)
        return
    if args.git_pr:
        from zcoder.claude.integrations.git import cmd_git_pr

        cmd_git_pr(args.git_pr[0], args.git_pr[1], key, model)
        return
    if args.git_changelog:
        from zcoder.claude.integrations.git import cmd_git_changelog

        cmd_git_changelog(args.git_changelog, key, model, output=args.output)
        return
    if args.git_review:
        from zcoder.claude.integrations.git import cmd_git_review

        cmd_git_review(key, model)
        return
    if args.git_blame_explain:
        from zcoder.claude.integrations.git import cmd_git_blame_explain

        f, s, e = args.git_blame_explain
        cmd_git_blame_explain(f, int(s), int(e), key, model)
        return

    # ── GitHub Integration ──
    if args.gh_review_pr:
        from zcoder.claude.integrations.github import cmd_gh_review_pr

        cmd_gh_review_pr(args.gh_review_pr, args.gh_token or None, key, model)
        return
    if args.gh_triage_issues:
        from zcoder.claude.integrations.github import cmd_gh_triage

        cmd_gh_triage(args.gh_triage_issues, args.gh_max_items, args.gh_token or None, key, model)
        return
    if args.gh_summarise_commits:
        from zcoder.claude.integrations.github import cmd_gh_commits

        cmd_gh_commits(args.gh_summarise_commits, args.gh_max_items, args.gh_token or None, key, model)
        return
    if args.gh_pr_description:
        from zcoder.claude.integrations.github import cmd_gh_pr_description

        cmd_gh_pr_description(args.gh_pr_description, args.gh_token or None, key, model)
        return

    # ── Multi-Agent Router ──
    if args.route_list:
        from zcoder.claude.orchestration.router import cmd_route_list

        cmd_route_list()
        return
    if args.route:
        from zcoder.claude.orchestration.router import cmd_route

        cmd_route(
            args.route,
            key,
            model,
            explain=args.route_explain,
            parallel=args.route_parallel,
            provider=getattr(args, "provider", None),
            base_url=getattr(args, "base_url", None),
        )
        return

    # ── Prompt Optimizer ──
    if args.prompt_lib_list:
        from zcoder.claude.optimization.prompt import cmd_prompt_lib_list

        cmd_prompt_lib_list()
        return
    if args.prompt_lib_get:
        from zcoder.claude.optimization.prompt import lib_get

        found = lib_get(args.prompt_lib_get)
        print(found if found is not None else f"No prompt saved under tag '{args.prompt_lib_get}'")
        return
    if args.prompt_lib_add:
        from zcoder.claude.optimization.prompt import lib_add

        if not args.prompt:
            print("\033[91m--prompt-lib-add requires --prompt\033[0m")
            return
        import time as _time

        tag = lib_add(args.prompt, args.tag or _time.strftime("%Y%m%d-%H%M%S"))
        print(f"Saved to prompt library under tag '{tag}'")
        return
    if args.ab_test:
        from zcoder.claude.optimization.prompt import cmd_ab_test

        if not (args.prompt and args.ab_prompt_b):
            print("\033[91m--ab-test requires --prompt (variant A) and --ab-prompt-b (variant B)\033[0m")
            return
        cmd_ab_test(args.prompt, args.ab_prompt_b, args.ab_task, key, model)
        return
    if args.score_prompt:
        from zcoder.claude.optimization.prompt import cmd_score

        cmd_score(args.score_prompt, key, model)
        return
    if args.prompt_optimize:
        from zcoder.claude.optimization.prompt import cmd_optimize

        cmd_optimize(args.prompt_optimize, key, model)
        return

    # ── Cost Optimizer (optimized calls the model; summary/reset handled above) ──
    if args.optimized:
        from zcoder.claude.optimization.cost import cmd_optimized

        cmd_optimized(args.optimized, key, verbose=True, force_model=args.force_model)
        return

    # ── Observability (errors needs the model for analysis; rest handled above) ──
    if args.obs_errors:
        from zcoder.claude.observability import cmd_obs_errors

        cmd_obs_errors(key, model, args.obs_hours)
        return

    # ── Workflows (run calls the model; scaffold handled above) ──
    if args.workflow_run:
        from zcoder.claude.orchestration.workflow import cmd_workflow_run

        cmd_workflow_run(args.workflow_run, key, input_text=args.workflow_input, output=args.output)
        return

    # ── Plan Mode ──
    if args.plan:
        from zcoder.claude.enterprise.hooks_perms import cmd_plan

        cmd_plan(
            args.plan, key, model, context=args.plan_context, execute=args.plan_execute, output=args.output
        )
        return

    if args.thinking or args.adaptive or args.effort_legacy_budget:
        from zcoder.claude.capabilities.thinking import ThinkingModeError, cmd_thinking

        prompt = args.prompt or (args.file and _read_file(args.file)) or ""
        try:
            cmd_thinking(
                prompt=prompt,
                api_key=key,
                model=model,
                budget=args.thinking_budget,
                effort=args.effort or None,
                adaptive=(True if args.adaptive else None),
                legacy_budget=args.effort_legacy_budget,
                show_thinking=args.show_thinking,
                stream=args.stream,
                display_omitted=args.thinking_display_omitted,
            )
        except ThinkingModeError as e:
            print(f"\033[91m✗ {e}\033[0m", file=sys.stderr)
            sys.exit(1)
        return
    if args.stream:
        from zcoder.claude.capabilities.stream import cmd_stream

        cmd_stream(
            args.prompt or "",
            key,
            model,
            file_content=_read_file(args.file) if args.file else None,
            show_thinking=args.show_thinking,
        )
        return
    if args.web_search or args.web_fetch:
        from zcoder.claude.capabilities.search import cmd_web_search

        cmd_web_search(
            args.prompt or "",
            key,
            model,
            max_searches=args.max_searches,
            show_citations=not args.no_citations,
            web_fetch=args.web_fetch,
            response_inclusion=args.response_inclusion or None,
        )
        return
    if args.fetch_url:
        from zcoder.claude.capabilities.search import cmd_fetch_url

        cmd_fetch_url(args.fetch_url, args.prompt or "", key, model)
        return
    if args.vision:
        from zcoder.claude.capabilities.vision import cmd_vision

        cmd_vision(
            args.vision, args.prompt or "", key, model, is_code=args.vision_code, language=args.vision_lang
        )
        return
    if args.vision_pdf:
        from zcoder.claude.capabilities.vision import cmd_vision_pdf

        cmd_vision_pdf(args.vision_pdf, args.prompt or "", key, model)
        return
    if args.vision_url:
        from zcoder.claude.capabilities.vision import cmd_vision_url

        cmd_vision_url(args.vision_url, args.prompt or "", key, model)
        return
    if args.vision_compare:
        from zcoder.claude.capabilities.vision import cmd_vision_compare

        cmd_vision_compare(args.vision_compare, args.prompt or "", key, model)
        return
    if args.vision_ocr:
        from zcoder.claude.capabilities.vision import cmd_vision_ocr

        cmd_vision_ocr(args.vision_ocr, key, model)
        return
    if args.batch_submit:
        from zcoder.claude.orchestration.batch import cmd_batch_submit

        cmd_batch_submit(args.batch_submit, key, model, use_300k_output=args.batch_300k_output)
        return
    if args.batch_status:
        from zcoder.claude.orchestration.batch import cmd_batch_status

        cmd_batch_status(args.batch_status, key)
        return
    if args.batch_results:
        from zcoder.claude.orchestration.batch import cmd_batch_results

        cmd_batch_results(args.batch_results, key, save_to=args.output or None)
        return
    if args.batch_cancel:
        from zcoder.claude.orchestration.batch import cmd_batch_cancel

        cmd_batch_cancel(args.batch_cancel, key)
        return
    if args.batch_list:
        from zcoder.claude.orchestration.batch import cmd_batch_list

        cmd_batch_list(key)
        return
    if args.batch_generate > 0:
        from zcoder.claude.orchestration.batch import cmd_batch_generate

        cmd_batch_generate(args.prompt or "", args.batch_generate, key, model, wait=args.batch_wait)
        return
    if args.cache_warm:
        from zcoder.claude.memory.cache import cmd_cache_warm

        cmd_cache_warm(
            key, model, system=args.cache_system or None, doc_files=args.cache_docs or [], ttl=args.cache_ttl
        )
        return
    if args.cache_multi_turn:
        from zcoder.claude.memory.cache import cmd_cache_multi_turn

        cmd_cache_multi_turn(
            args.cache_multi_turn,
            key,
            model,
            system=args.cache_system or None,
            ttl=args.cache_ttl,
            mid_system=args.cache_mid_system or None,
            mid_system_after=args.cache_mid_system_after,
            show_stats=args.cache_stats,
        )
        return
    if args.cache:
        from zcoder.claude.memory.cache import cmd_cache_generate

        docs = [open(f).read() for f in (args.cache_docs or [])]
        cmd_cache_generate(
            args.prompt or "",
            key,
            model,
            system=args.cache_system or None,
            docs=docs,
            ttl=args.cache_ttl,
            show_stats=args.cache_stats,
            diagnose=args.cache_diagnose,
        )
        return
    if args.tool_agent:
        from zcoder.claude.tools.registry import cmd_tool_agent

        cmd_tool_agent(args.prompt or "", key, model, max_turns=args.max_turns)
        return
    if args.server_tool:
        from zcoder.claude.tools.registry import cmd_server_tool

        extra_tool_defs = None
        if args.file:
            import json as _json

            extra_tool_defs = _json.loads(_read_file(args.file))
            if isinstance(extra_tool_defs, dict):
                extra_tool_defs = [extra_tool_defs]
        cmd_server_tool(
            args.prompt or "",
            [t.strip() for t in args.server_tool.split(",")],
            key,
            model,
            use_context_management=args.context_management,
            use_compaction=args.compaction,
            task_budget_tokens=args.task_budget or None,
            use_ptc=args.ptc,
            extra_tool_defs=extra_tool_defs,
        )
        return
    if args.memory_agent:
        from zcoder.claude.tools.registry import cmd_memory_agent

        cmd_memory_agent(args.memory_agent, key, model, memory_dir=args.memory_dir, max_turns=args.max_turns)
        return
    if args.advisor:
        from zcoder.claude.capabilities.advisor import cmd_advisor

        cmd_advisor(
            args.advisor,
            key,
            model,
            advisor_model=args.advisor_model,
            max_uses=args.advisor_max_uses or None,
            advisor_max_tokens=args.advisor_max_tokens or None,
        )
        return
    if args.embed:
        from zcoder.claude.capabilities.embeddings import cmd_embed

        cmd_embed(args.embed, model=args.embed_model, input_type=args.embed_input_type)
        return
    if args.embed_file:
        from zcoder.claude.capabilities.embeddings import cmd_embed_file

        cmd_embed_file(args.embed_file, model=args.embed_model, input_type=args.embed_input_type)
        return
    if args.embed_similarity:
        from zcoder.claude.capabilities.embeddings import cmd_embed_similarity

        cmd_embed_similarity(args.embed_similarity[0], args.embed_similarity[1], model=args.embed_model)
        return
    if args.stream_tools:
        import json as _json

        from zcoder.claude.capabilities.stream import cmd_stream_tools

        tool_defs = _json.loads(_read_file(args.file)) if args.file else []
        if isinstance(tool_defs, dict):
            tool_defs = [tool_defs]
        cmd_stream_tools(args.stream_tools, tool_defs, key, model)
        return
    if args.structured:
        from zcoder.claude.capabilities.structured import cmd_structured

        cmd_structured(
            args.prompt or "", key, model, schema_path=args.schema, schema_inline=args.schema_inline
        )
        return
    if args.structured_analyse:
        from zcoder.claude.capabilities.structured import cmd_structured_analyse

        cmd_structured_analyse(args.structured_analyse, key, model)
        return
    if args.structured_extract:
        from zcoder.claude.capabilities.structured import cmd_structured_extract

        cmd_structured_extract(args.structured_extract, args.schema, key, model)
        return
    if args.file_upload:
        from zcoder.claude.integrations.files import cmd_file_upload

        cmd_file_upload(args.file_upload, key, model)
        return
    if args.file_list:
        from zcoder.claude.integrations.files import cmd_file_list

        cmd_file_list(key, model)
        return
    if args.file_delete:
        from zcoder.claude.integrations.files import cmd_file_delete

        cmd_file_delete(args.file_delete, key)
        return
    if args.file_ask:
        from zcoder.claude.integrations.files import cmd_file_ask

        cmd_file_ask(args.file_ask, args.prompt or "Summarise.", key, model, media_type=args.file_media_type)
        return
    if args.file_download:
        from zcoder.claude.integrations.files import cmd_file_download

        cmd_file_download(
            args.file_download, args.file_output or args.output or f"{args.file_download}.bin", key
        )
        return
    if args.code_exec:
        from zcoder.claude.capabilities.code_exec import cmd_code_exec

        cmd_code_exec(
            args.prompt or "",
            key,
            model,
            output_dir=args.code_exec_output or None,
            code_exec_version=args.code_exec_version,
        )
        return
    if args.code_debug:
        from zcoder.claude.capabilities.code_exec import cmd_code_debug

        cmd_code_debug(args.code_debug, key, model, code_exec_version=args.code_exec_version)
        return
    if args.count_tokens:
        from zcoder.claude.optimization.tokens import cmd_count_tokens

        cmd_count_tokens(args.prompt or "", key, model, file_path=args.file, budget=args.count_budget or None)
        return
    if args.cite:
        from zcoder.claude.capabilities.citations import cmd_cite

        cmd_cite(args.prompt or "", args.cite, key, model)
        return
    if args.rag:
        from zcoder.claude.capabilities.citations import cmd_rag

        cmd_rag(args.prompt or "", args.rag, key, model, pattern=args.rag_pattern)
        return
    if args.computer_use:
        from zcoder.claude.models.registry import cmd_computer_use

        cmd_computer_use(args.computer_use, key, model)
        return
    if args.interleaved_thinking:
        from zcoder.claude.models.registry import cmd_adaptive_thinking

        cmd_adaptive_thinking(args.prompt or "", key, model, effort=args.effort or "medium")
        return
    if args.agent_session or args.agent_orchestrate:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_chat, cmd_agent_orchestrate

        if args.agent_orchestrate:
            cmd_agent_orchestrate(args.prompt or "", key, model, session_id=args.agent_session)
        else:
            cmd_agent_chat(args.prompt or "", key, model, session_id=args.agent_session)
        return
    if args.agent_rewind:
        if not args.agent_session:
            print("--agent-rewind requires --agent-session")
            sys.exit(1)
        from zcoder.claude.capabilities.code import CodeSession

        session = CodeSession.load(args.agent_session)
        session.rewind(args.agent_rewind)
        session.save()
        print(f"Rewound session {args.agent_session} to checkpoint {args.agent_rewind}")
        return
    if args.agent_branch:
        if not args.agent_session:
            print("--agent-branch requires --agent-session")
            sys.exit(1)
        from zcoder.claude.capabilities.code import CodeSession

        session = CodeSession.load(args.agent_session)
        branched = session.branch(args.agent_branch)
        branched.save()
        print(f"Branched session {args.agent_session} at checkpoint {args.agent_branch} → {branched.id}")
        return
    if args.agent_dream:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_dream

        sess_ids = [s.strip() for s in args.agent_dream_sessions.split(",") if s.strip()] or None
        cmd_agent_dream(
            args.agent_dream,
            key,
            model=model,
            session_ids=sess_ids,
            instructions=args.agent_dream_instructions or None,
        )
        return
    if args.agent_dream_get:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_dream_get

        cmd_agent_dream_get(args.agent_dream_get, key)
        return
    if args.agent_dream_cancel:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_dream_cancel

        cmd_agent_dream_cancel(args.agent_dream_cancel, key)
        return
    if args.agent_dream_archive:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_dream_archive

        cmd_agent_dream_archive(args.agent_dream_archive, key)
        return
    if args.agent_dream_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_dream_list

        cmd_agent_dream_list(
            key,
            include_archived=args.agent_dream_list_include_archived,
            limit=args.agent_dream_list_limit,
            page=args.agent_dream_list_page or None,
        )
        return
    if args.agent_webhook_register:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_webhook_register

        events = [e.strip() for e in args.agent_webhook_events.split(",") if e.strip()] or None
        cmd_agent_webhook_register(args.agent_webhook_register, key, events=events)
        return
    if args.agent_vault_create:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_vault_create

        cmd_agent_vault_create(
            args.agent_vault_create, key, external_user_id=args.agent_vault_external_user or None
        )
        return
    if args.agent_vault_add_credential:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_vault_add_credential

        if not args.agent_vault_cred_type:
            print("[ERROR] --agent-vault-add-credential requires --agent-vault-cred-type")
            sys.exit(1)
        domains = [d.strip() for d in args.agent_vault_allowed_domains.split(",") if d.strip()] or None
        cmd_agent_vault_add_credential(
            args.agent_vault_add_credential,
            args.agent_vault_cred_type,
            key,
            mcp_server_url=args.agent_vault_mcp_url or None,
            secret_name=args.agent_vault_secret_name or None,
            secret_value=args.agent_vault_secret,
            allowed_domains=domains,
            injection_location=args.agent_vault_injection_location or None,
        )
        return
    if args.agent_vault_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_vault_list

        cmd_agent_vault_list(key)
        return
    if args.agent_schedule_create:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_schedule_create

        if not args.agent_schedule_env or not args.agent_schedule_cron:
            print("[ERROR] --agent-schedule-create requires --agent-schedule-env and --agent-schedule-cron")
            sys.exit(1)
        cmd_agent_schedule_create(
            args.agent_schedule_create,
            args.agent_schedule_env,
            args.agent_schedule_cron,
            key,
            timezone=args.agent_schedule_tz,
            task=args.agent_schedule_task,
        )
        return
    if args.agent_schedule_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_schedule_list

        cmd_agent_schedule_list(key)
        return
    if args.agent_schedule_cancel:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_schedule_cancel

        cmd_agent_schedule_cancel(args.agent_schedule_cancel, key)
        return
    if args.agent_review_multiagent:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_review_multiagent

        specialists = [s.strip() for s in args.agent_review_specialists.split(",") if s.strip()]
        cmd_agent_review_multiagent(args.agent_review_multiagent, specialists, key, model=model)
        return
    if args.agent_outcome_rubric_upload:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_outcome_rubric_upload

        cmd_agent_outcome_rubric_upload(args.agent_outcome_rubric_upload, key, model)
        return
    if args.agent_env_self_hosted:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_env_self_hosted_create

        cmd_agent_env_self_hosted_create(args.agent_env_self_hosted, key)
        return
    if args.agent_env_work_stats:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_env_work_stats

        cmd_agent_env_work_stats(args.agent_env_work_stats, key)
        return
    if args.agent_managed_run:
        # Real hosted Claude Managed Agents API (/v1/agents, /v1/environments,
        # /v1/sessions) — distinct from --agent-session above, which runs a
        # local agent loop over the plain Messages API. See
        # claude_agents_sdk.ManagedAgentsClient.
        from zcoder.claude.orchestration.agents_sdk import cmd_managed_agent_run

        outcome_rubric_text = None
        if args.agent_outcome_rubric:
            outcome_rubric_text = Path(args.agent_outcome_rubric).read_text(encoding="utf-8")
        if args.agent_outcome and not outcome_rubric_text and not args.agent_outcome_rubric_file:
            print(
                "[ERROR] --agent-outcome requires --agent-outcome-rubric FILE "
                "or --agent-outcome-rubric-file FILE_ID"
            )
            sys.exit(1)
        agent_overrides = None
        if args.agent_override_json:
            import json as _json

            agent_overrides = _json.loads(Path(args.agent_override_json).read_text(encoding="utf-8"))
        if args.agent_override_model or args.agent_override_system:
            agent_overrides = agent_overrides or {}
            if args.agent_override_model:
                agent_overrides["model"] = args.agent_override_model
            if args.agent_override_system:
                agent_overrides["system"] = args.agent_override_system
        cmd_managed_agent_run(
            args.agent_managed_run,
            key,
            model=model,
            memory_store=args.agent_memory_store or None,
            outcome_description=args.agent_outcome or None,
            outcome_rubric=outcome_rubric_text,
            outcome_rubric_file_id=args.agent_outcome_rubric_file or None,
            outcome_max_iterations=args.agent_outcome_max_iter,
            vault_id=args.agent_vault or None,
            agent_overrides=agent_overrides,
            stream_deltas=args.agent_stream_deltas,
            budget_usd_cents=(
                round(args.agent_session_budget_usd * 100) if args.agent_session_budget_usd else None
            ),
        )
        return
    if args.agent_create:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_create

        cmd_agent_create(
            args.agent_create,
            key,
            model=model,
            system=args.agent_system,
            effort=args.agent_effort or None,
            inference_geo=args.agent_inference_geo or None,
        )
        return
    if args.agent_get:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_get

        cmd_agent_get(args.agent_get, key, version=args.agent_get_version)
        return
    if args.agent_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_list

        cmd_agent_list(key, limit=args.agent_list_limit)
        return
    if args.agent_update:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_update

        cmd_agent_update(
            args.agent_update,
            key,
            model=model if model else None,
            effort=args.agent_effort or None,
            system=args.agent_system or None,
            inference_geo=args.agent_inference_geo or None,
        )
        return
    if args.agent_session_get:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_session_get

        cmd_agent_session_get(args.agent_session_get, key)
        return
    if args.agent_session_budget_set:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_session_budget_set

        if not args.agent_session_budget_usd:
            print("[ERROR] --agent-session-budget-set requires --agent-session-budget-usd DOLLARS")
            sys.exit(1)
        cmd_agent_session_budget_set(
            args.agent_session_budget_set, key, round(args.agent_session_budget_usd * 100)
        )
        return
    if args.agent_session_budget_remove:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_session_budget_remove

        cmd_agent_session_budget_remove(args.agent_session_budget_remove, key)
        return
    if args.agent_memory_store_create:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_store_create

        if not args.agent_memory_store:
            print("[ERROR] --agent-memory-store-create requires --agent-memory-store NAME")
            sys.exit(1)
        cmd_agent_memory_store_create(args.agent_memory_store, key)
        return
    if args.agent_memory_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_list

        depth = int(args.agent_memory_depth) if args.agent_memory_depth else None
        cmd_agent_memory_list(
            args.agent_memory_list, key, path_prefix=args.agent_memory_path_prefix or None, depth=depth
        )
        return
    if args.agent_memory_stores_list:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_stores_list

        cmd_agent_memory_stores_list(key, include_archived=args.agent_memory_stores_include_archived)
        return
    if args.agent_memory_store_archive:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_store_archive

        cmd_agent_memory_store_archive(args.agent_memory_store_archive, key)
        return
    if args.agent_memory_store_delete:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_store_delete

        cmd_agent_memory_store_delete(
            args.agent_memory_store_delete, key, confirm=args.agent_memory_store_delete_yes
        )
        return
    if args.agent_memory_get:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_get

        if not args.agent_memory_id:
            print("[ERROR] --agent-memory-get requires --agent-memory-id")
            sys.exit(1)
        cmd_agent_memory_get(args.agent_memory_get, args.agent_memory_id, key)
        return
    if args.agent_memory_create:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_create

        if not args.agent_memory_path or not args.agent_memory_content:
            print("[ERROR] --agent-memory-create requires --agent-memory-path and --agent-memory-content")
            sys.exit(1)
        cmd_agent_memory_create(
            args.agent_memory_create, args.agent_memory_path, args.agent_memory_content, key
        )
        return
    if args.agent_memory_update:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_update

        if not args.agent_memory_id:
            print("[ERROR] --agent-memory-update requires --agent-memory-id")
            sys.exit(1)
        cmd_agent_memory_update(
            args.agent_memory_update,
            args.agent_memory_id,
            key,
            content=args.agent_memory_content or None,
            path=args.agent_memory_path or None,
        )
        return
    if args.agent_memory_delete:
        from zcoder.claude.orchestration.agents_sdk import cmd_agent_memory_delete

        if not args.agent_memory_id:
            print("[ERROR] --agent-memory-delete requires --agent-memory-id")
            sys.exit(1)
        cmd_agent_memory_delete(
            args.agent_memory_delete, args.agent_memory_id, key, confirm=args.agent_memory_delete_yes
        )
        return
    if args.cowork:
        from zcoder.services.cowork import cmd_cowork

        prompt = args.cowork_prompt or args.prompt or ""
        if not prompt:
            print("[ERROR] --cowork requires -p or --cowork-prompt")
            sys.exit(1)
        cmd_cowork(
            args.cowork,
            prompt,
            key,
            model,
            files=args.cowork_files,
            depth=args.cowork_depth,
            output_fmt=args.cowork_format,
            output_file=args.output,
        )
        return

    # Claude Code commands
    if args.code_agent_mcp_tunnel:
        from zcoder.claude.orchestration.agents_sdk import cmd_mcp_tunnel_open

        cmd_mcp_tunnel_open(key, args.code_agent_mcp_tunnel)
        return
    if args.code_agent or args.code_agent_session or args.code_agent_resume:
        from zcoder.claude.capabilities.code import cmd_code_agent

        prompt = args.prompt or ""
        if not prompt:
            print("[ERROR] --code-agent requires -p PROMPT")
            sys.exit(1)
        result = cmd_code_agent(
            prompt=prompt,
            api_key=key,
            model=model,
            cwd=args.code_agent_cwd,
            tools=args.code_agent_tools,
            permission=args.code_agent_permission,
            session_id=args.code_agent_session or args.code_agent_resume,
            system=args.code_agent_system,
            mcp_urls=args.code_agent_mcp or [],
            output_mode=args.code_agent_output,
            hooks_file=args.code_agent_hooks,
            checkpoint=args.code_agent_checkpoint,
            output_file=args.output,
            output_style=args.code_agent_output_style,
            sandbox=args.code_agent_sandbox,
            sandbox_allow_net=args.code_agent_sandbox_allow_net,
            sandbox_roots=args.code_agent_sandbox_roots or [],
            headless=args.code_agent_headless,
            agent_context_editing=args.agent_context_editing,
            load_project_memory=not args.no_project_memory,
            tenant_id=args.code_agent_tenant or "",
        )
        if args.code_agent_output == "json":
            print(result)
        elif args.output:
            Path(args.output).write_text(result)
        return
    if args.code_agent_subagent:
        from zcoder.claude.capabilities.code import cmd_code_subagent

        result = cmd_code_subagent(
            args.code_agent_subagent,
            key,
            model,
            cwd=args.code_agent_cwd,
            load_project_memory=not args.no_project_memory,
            max_turns=args.code_agent_subagent_turns or 10,
            max_cost_usd=args.code_agent_subagent_cost,
            tenant_id=args.code_agent_subagent_tenant or "",
        )
        if args.code_agent_output == "json":
            print(result)
        elif args.output:
            Path(args.output).write_text(result)
        return
    if args.code_agent_todo:
        from zcoder.claude.capabilities.code import cmd_code_todo

        cmd_code_todo(args.code_agent_todo, key, model)
        return
    if args.code_agent_slash:
        from zcoder.claude.capabilities.code import cmd_code_slash

        cmd_code_slash(args.code_agent_slash, key, model, cwd=args.code_agent_cwd, prompt=args.prompt or "")
        return
    if args.code_agent_cost:
        from zcoder.claude.capabilities.code import cmd_code_cost

        cmd_code_cost(key)
        return

    if args.project_plan:
        from zcoder.services.coder import Coder
        from zcoder.services.projects import cmd_project_plan

        cmd_project_plan(args.project_plan, Coder(api_key=key, model=model))
        return
    if args.project_run:
        from zcoder.services.coder import Coder
        from zcoder.services.projects import cmd_project_run

        cmd_project_run(args.project_run, args.task or "all", Coder(api_key=key, model=model))
        return
    if args.artifact_create:
        from zcoder.infrastructure.artifacts import cmd_artifact_create
        from zcoder.services.coder import Coder

        if not args.prompt:
            print("[ERROR] --artifact-create requires -p")
            sys.exit(1)
        tags = [t.strip() for t in args.artifact_tags.split(",") if t.strip()]
        cmd_artifact_create(
            args.artifact_create,
            args.prompt,
            artifact_type=args.artifact_type,
            language=args.artifact_lang,
            tags=tags,
            project_id=args.artifact_project,
            coder=Coder(api_key=key, model=model),
        )
        return
    if args.artifact_iterate:
        from zcoder.infrastructure.artifacts import cmd_artifact_iterate
        from zcoder.services.coder import Coder

        cmd_artifact_iterate(args.artifact_iterate, args.prompt or "", Coder(api_key=key, model=model))
        return

    if args.prompt or args.file:
        from zcoder.services.coder import Coder

        c = Coder(
            api_key=key,
            model=model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            service_tier=args.service_tier,
            inference_geo=args.inference_geo,
            fast_mode=args.fast_mode,
            # Previously never sourced from a CLI flag at all — see
            # the Skills & Agents arg group comment above.
            personality_style=args.personality,
        )
        # --skill and --agent now actually affect the request: each
        # contributes a system-prompt fragment instead of being accepted
        # and discarded.
        system_parts = []
        if args.skill:
            from zcoder.services.skills import SkillManager

            skill = SkillManager().get_skill(args.skill)
            if skill:
                system_parts.append(f"Skill focus — {skill['name']}: {skill['description']}")
            else:
                print(
                    f"\033[93m⚠ Unknown --skill '{args.skill}' (see --list-skills); ignoring.\033[0m",
                    file=sys.stderr,
                )
        if args.agent:
            system_parts.append(AGENT_SYSTEM_PROMPTS[args.agent])
        system = "\n\n".join(system_parts) or None

        result = c.generate(
            args.prompt or "", system=system, file_content=_read_file(args.file) if args.file else None
        )
        print(result)
        if args.output:
            open(args.output, "w").write(result)
        return

    parser.print_help()


if __name__ == "__main__":
    main()

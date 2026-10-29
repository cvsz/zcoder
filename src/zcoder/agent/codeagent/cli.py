"""Command-line entry point for the CodeAgent Textual TUI."""

from __future__ import annotations

import argparse
from pathlib import Path

from zcoder.agent.codeagent.factory import build_agent
from zcoder.agent.codeagent.settings import load_settings
from zcoder.interfaces.cli.agent_tui import run_agent_tui


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local CodeAgent TUI.")
    parser.add_argument("--cwd", default=".", help="Workspace root (default: current directory)")
    parser.add_argument(
        "--mode",
        choices=("default", "acceptEdits", "plan"),
        default=None,
        help="Permission mode override; otherwise use settings",
    )
    parser.add_argument("--model", help="Override the configured local model name")
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Explicitly opt in to bypass mode (still subject to managed policy)",
    )
    parser.add_argument(
        "--no-discover-model",
        action="store_true",
        help="Skip the local llama-server model discovery request",
    )
    args = parser.parse_args(argv)

    root = Path(args.cwd).expanduser().resolve()
    settings = load_settings(root)
    if args.model:
        settings.model = args.model
    mode = "bypass" if args.dangerously_skip_permissions else args.mode
    agent = build_agent(
        root,
        settings=settings,
        mode=mode,
        allow_bypass=args.dangerously_skip_permissions,
        discover_model=not args.no_discover_model,
    )
    run_agent_tui(agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

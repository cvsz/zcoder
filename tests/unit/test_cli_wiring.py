"""Architecture and CLI wiring regression tests for the src-layout package."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
CLAUDE_ROOT = SRC_ROOT / "zcoder" / "claude"
MAIN_PATH = SRC_ROOT / "zcoder" / "main.py"

# The plural eval harness is intentionally superseded by eval/eval.py.
KNOWN_EXCEPTIONS = {
    ("eval/evals.py", "cmd_eval"),
}


def _cmd_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.name
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("cmd_")
    ]


def _claude_modules() -> list[Path]:
    return sorted(path for path in CLAUDE_ROOT.rglob("*.py") if path.name != "__init__.py")


def _module_key(path: Path) -> str:
    return path.relative_to(CLAUDE_ROOT).as_posix()


@pytest.fixture(scope="module")
def main_source() -> str:
    return MAIN_PATH.read_text(encoding="utf-8")


def test_canonical_cli_source_exists():
    assert MAIN_PATH.is_file()
    assert CLAUDE_ROOT.is_dir()
    assert _claude_modules(), "canonical Claude package must contain implementation modules"


@pytest.mark.parametrize("module_path", _claude_modules(), ids=_module_key)
def test_every_cmd_function_is_referenced_in_main(module_path: Path, main_source: str):
    key = _module_key(module_path)
    for fn in _cmd_functions(module_path):
        if (key, fn) in KNOWN_EXCEPTIONS:
            continue
        assert re.search(r"\b" + re.escape(fn) + r"\b", main_source), (
            f"{key}:{fn} is defined but not referenced by zcoder.main; "
            "wire it into the CLI or document an intentional exception"
        )


def test_known_exceptions_still_point_at_real_functions():
    for relative_path, fn in KNOWN_EXCEPTIONS:
        path = CLAUDE_ROOT / relative_path
        assert path.is_file(), f"stale CLI-wiring exception: {relative_path}"
        assert fn in _cmd_functions(path), f"stale CLI-wiring exception: {relative_path}:{fn}"


def test_legacy_and_canonical_main_share_version():
    import main as legacy_main
    from zcoder import main as canonical_main

    assert legacy_main.VERSION == canonical_main.VERSION


def test_parser_uses_zcoder_as_the_displayed_cli_name():
    import main as main_mod

    parser = main_mod.build_parser()

    assert parser.prog == "zcoder"
    assert "usage: zcoder" in parser.format_help()
    assert "usage: ai-coder" not in parser.format_help()


@pytest.fixture
def parsed_args():
    import main as main_mod

    parser = main_mod.build_parser()
    return parser.parse_args


def test_route_flags_parse(parsed_args):
    args = parsed_args(["--route", "fix this bug", "--route-explain", "--route-parallel"])
    assert args.route == "fix this bug"
    assert args.route_explain is True
    assert args.route_parallel is True


def test_github_review_flags_parse(parsed_args):
    args = parsed_args(["--gh-review-pr", "acme/widgets/42", "--gh-token", "ghp_x"])
    assert args.gh_review_pr == "acme/widgets/42"
    assert args.gh_token == "ghp_x"


def test_metrics_flags_parse(parsed_args):
    args = parsed_args(["--metrics-show", "--metrics-today", "--metrics-model", "claude-sonnet-5"])
    assert args.metrics_show is True
    assert args.metrics_today is True
    assert args.metrics_model == "claude-sonnet-5"


def test_member_role_flag_parse(parsed_args):
    args = parsed_args(["--member-role-set", "user_01Ab", "managed"])
    assert args.member_role_set == ["user_01Ab", "managed"]


def _run_main_with(monkeypatch, argv, api_key="sk-ant-test"):
    import main as main_mod

    monkeypatch.setattr("sys.argv", ["main.py"] + argv)
    monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    main_mod.main()


def test_route_list_dispatches(monkeypatch):
    import claude_router

    called = {}
    monkeypatch.setattr(claude_router, "cmd_route_list", lambda *a, **k: called.setdefault("hit", True))
    _run_main_with(monkeypatch, ["--route-list"])
    assert called.get("hit") is True


def test_metrics_clear_dispatches(monkeypatch):
    import claude_metrics

    called = {}
    monkeypatch.setattr(claude_metrics, "cmd_metrics_clear", lambda *a, **k: called.setdefault("hit", True))
    _run_main_with(monkeypatch, ["--metrics-clear"])
    assert called.get("hit") is True


def test_ce_user_management_requires_admin_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        _run_main_with(monkeypatch, ["--members-list"])
    assert "Admin API key" in capsys.readouterr().err

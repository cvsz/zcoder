"""tests/test_cli_wiring.py — CLI-to-API wiring coverage

Regression test for the v1.30.0 wiring audit: every `cmd_*` function
defined in a `claude_*.py` module is expected to be reachable from
`main.py`'s dispatch, either directly or via a re-exported name. This
doesn't verify the *behavior* of each wired command (that's each
module's own test file's job) — only that nothing gets left behind the
way claude_github.py, claude_metrics.py, claude_prompt_optimizer.py,
and claude_router.py were before this cycle: fully written, fully
tested at the function level, and never given a CLI flag.
"""
import ast
import glob
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Modules intentionally excluded from the "every cmd_* must be wired"
# sweep, with the reason on file:
KNOWN_EXCEPTIONS = {
    # claude_evals.py (plural) is the pre-v1.10 eval harness, superseded
    # by claude_eval.py (singular) — cmd_eval_run/cmd_eval_list/
    # cmd_eval_scaffold/cmd_eval_compare in claude_eval.py cover the same
    # ground with more features (threshold, output file, verbose). Wiring
    # claude_evals.cmd_eval too would create a second, conflicting
    # `--eval`-family flag set for the same job. Left unwired on purpose;
    # a candidate for deletion in a future cycle, not a wiring gap.
    ("claude_evals.py", "cmd_eval"),
}


def _cmd_functions(path):
    """Top-level `def cmd_*` function names in a Python source file."""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    return [node.name for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("cmd_")]


def _all_claude_modules():
    return sorted(glob.glob(os.path.join(REPO_ROOT, "claude_*.py")))


@pytest.fixture(scope="module")
def main_source():
    with open(os.path.join(REPO_ROOT, "main.py"), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("module_path", _all_claude_modules(),
                         ids=lambda p: os.path.basename(p))
def test_every_cmd_function_is_referenced_in_main(module_path, main_source):
    module_name = os.path.basename(module_path)
    for fn in _cmd_functions(module_path):
        if (module_name, fn) in KNOWN_EXCEPTIONS:
            continue
        pattern = r"\b" + re.escape(fn) + r"\b"
        assert re.search(pattern, main_source), (
            f"{module_name}.{fn}() is defined but never referenced in "
            f"main.py — add a CLI flag and dispatch line, or add it to "
            f"KNOWN_EXCEPTIONS with a reason if it's intentionally unwired."
        )


def test_known_exceptions_still_point_at_real_functions():
    """Guards against KNOWN_EXCEPTIONS silently going stale (e.g. the
    excepted function gets renamed or the file gets deleted, and the
    exception entry keeps suppressing a check that would now catch
    something real)."""
    for module_name, fn in KNOWN_EXCEPTIONS:
        module_path = os.path.join(REPO_ROOT, module_name)
        assert os.path.exists(module_path), f"{module_name} no longer exists"
        assert fn in _cmd_functions(module_path), (
            f"{module_name}.{fn} no longer defined — remove from KNOWN_EXCEPTIONS"
        )


# ── Targeted dispatch tests for the four newly-wired modules ────────────


@pytest.fixture
def parsed_args():
    import main as main_mod
    parser = main_mod.build_parser()

    def _parse(argv):
        return parser.parse_args(argv)
    return _parse


def test_gh_review_pr_flag_parses(parsed_args):
    args = parsed_args(["--gh-review-pr", "acme/widgets/42", "--gh-token", "ghp_x"])
    assert args.gh_review_pr == "acme/widgets/42"
    assert args.gh_token == "ghp_x"


def test_gh_max_items_defaults_to_20(parsed_args):
    args = parsed_args(["--gh-triage-issues", "acme/widgets"])
    assert args.gh_max_items == 20


def test_route_flags_parse(parsed_args):
    args = parsed_args(["--route", "fix this bug", "--route-explain", "--route-parallel"])
    assert args.route == "fix this bug"
    assert args.route_explain is True
    assert args.route_parallel is True


def test_route_list_is_independent_flag(parsed_args):
    args = parsed_args(["--route-list"])
    assert args.route_list is True
    assert args.route is None


def test_optimize_flag_parses(parsed_args):
    args = parsed_args(["--optimize", "write me a poem"])
    assert args.prompt_optimize == "write me a poem"


def test_ab_test_flags_parse(parsed_args):
    args = parsed_args(["--ab-test", "--prompt", "variant A", "--ab-prompt-b", "variant B",
                        "--ab-task", "summarize a doc"])
    assert args.ab_test is True
    assert args.prompt == "variant A"
    assert args.ab_prompt_b == "variant B"
    assert args.ab_task == "summarize a doc"


def test_metrics_show_and_modifiers_parse(parsed_args):
    args = parsed_args(["--metrics-show", "--metrics-today", "--metrics-model", "claude-sonnet-5"])
    assert args.metrics_show is True
    assert args.metrics_today is True
    assert args.metrics_model == "claude-sonnet-5"


def test_metrics_export_flag_parses(parsed_args):
    args = parsed_args(["--metrics-export", "out.json"])
    assert args.metrics_export == "out.json"


# ── Dispatch-level tests (monkeypatch the imported cmd_* function) ──────


def _run_main_with(monkeypatch, argv, api_key="sk-ant-test"):
    import main as main_mod
    monkeypatch.setattr("sys.argv", ["main.py"] + argv)
    monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    main_mod.main()


def test_route_list_dispatches_to_cmd_route_list(monkeypatch):
    import claude_router
    called = {}
    monkeypatch.setattr(claude_router, "cmd_route_list", lambda *a, **k: called.setdefault("hit", True))
    _run_main_with(monkeypatch, ["--route-list"])
    assert called.get("hit") is True


def test_prompt_lib_list_dispatches(monkeypatch):
    import claude_prompt_optimizer
    called = {}
    monkeypatch.setattr(claude_prompt_optimizer, "cmd_prompt_lib_list",
                        lambda *a, **k: called.setdefault("hit", True))
    _run_main_with(monkeypatch, ["--prompt-lib-list"])
    assert called.get("hit") is True


def test_metrics_clear_dispatches(monkeypatch):
    import claude_metrics
    called = {}
    monkeypatch.setattr(claude_metrics, "cmd_metrics_clear",
                        lambda *a, **k: called.setdefault("hit", True))
    _run_main_with(monkeypatch, ["--metrics-clear"])
    assert called.get("hit") is True


def test_gh_triage_dispatches_with_positional_order(monkeypatch):
    import claude_github
    seen = {}

    def fake_triage(repo, max_items, token, api_key, model):
        seen.update(repo=repo, max_items=max_items, token=token)

    monkeypatch.setattr(claude_github, "cmd_gh_triage", fake_triage)
    _run_main_with(monkeypatch, ["--gh-triage-issues", "acme/widgets",
                                "--gh-max-items", "5", "--gh-token", "ghp_x"])
    assert seen == {"repo": "acme/widgets", "max_items": 5, "token": "ghp_x"}


def test_prompt_lib_add_requires_prompt(monkeypatch, capsys):
    _run_main_with(monkeypatch, ["--prompt-lib-add", "--tag", "my-tag"])
    out = capsys.readouterr().out
    assert "requires --prompt" in out


def test_ab_test_requires_both_variants(monkeypatch, capsys):
    _run_main_with(monkeypatch, ["--ab-test", "--prompt", "only A"])
    out = capsys.readouterr().out
    assert "requires --prompt" in out and "--ab-prompt-b" in out

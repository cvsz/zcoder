import sys

import pytest

from zcoder.main import main


@pytest.mark.parametrize(
    "argv",
    [
        ["zcoder", "--thinking", "--prompt", "hello"],
        ["zcoder", "--web-search", "--prompt", "hello"],
        ["zcoder", "--list-models"],
        ["zcoder", "--obs-errors"],
    ],
)
def test_provider_specific_api_commands_fail_closed_in_local_mode(argv, monkeypatch, capsys):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "unavailable in local-only mode" in output


def test_every_direct_provider_cli_flag_fails_closed_in_local_mode(monkeypatch, capsys):
    from zcoder.main import DIRECT_PROVIDER_FEATURE_FLAGS, build_parser

    parser = build_parser()
    actions = {action.dest: action for action in parser._actions}
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.delenv("ZCODER_PROVIDER", raising=False)

    assert len(DIRECT_PROVIDER_FEATURE_FLAGS) == len(set(DIRECT_PROVIDER_FEATURE_FLAGS))
    assert set(DIRECT_PROVIDER_FEATURE_FLAGS) <= set(actions)

    for dest in DIRECT_PROVIDER_FEATURE_FLAGS:
        action = actions[dest]
        option = next(iter(action.option_strings), None)
        assert option is not None, f"guarded CLI destination {dest!r} has no option"
        argv = ["zcoder", option]
        if action.nargs == 0:
            pass
        elif isinstance(action.nargs, int):
            argv.extend("local-test" for _ in range(action.nargs))
        elif action.nargs in ("*", "?", "+"):
            argv.append("local-test")
        elif action.type is int:
            argv.append("1")
        elif action.type is float:
            argv.append("1.0")
        elif action.choices:
            argv.append(str(next(iter(action.choices))))
        else:
            argv.append("local-test")
        monkeypatch.setattr(sys, "argv", argv)

        with pytest.raises(SystemExit) as error:
            main()

        assert error.value.code == 2, dest
        assert "unavailable in local-only mode" in capsys.readouterr().err, dest


def test_migrated_local_commands_are_not_blocked(monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    args = type("Args", (), {"provider": None, "base_url": None, "prompt": "hello"})()

    from zcoder.main import _has_direct_provider_feature, _is_local_only

    assert _is_local_only(args)
    assert not _has_direct_provider_feature(args)


def test_advisor_dispatches_in_local_only_mode(monkeypatch, capsys):
    import zcoder.agent.capabilities.advisor as advisor_module

    called = {}
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.setattr(sys, "argv", ["zcoder", "--advisor", "review this", "--model", "local-qwen"])
    monkeypatch.setattr(
        advisor_module,
        "cmd_advisor",
        lambda *args, **kwargs: called.update(args=args, kwargs=kwargs),
    )

    main()

    assert called["args"][:3] == ("review this", "", "local-qwen")
    assert called["kwargs"]["advisor_model"] is None
    capsys.readouterr()


def test_structured_local_command_is_not_blocked_by_guard():
    from zcoder.main import _has_direct_provider_feature

    args = type("Args", (), {"structured": True, "structured_analyse": None})()

    assert not _has_direct_provider_feature(args)


@pytest.mark.parametrize(
    "args",
    [
        type("Args", (), {"excel": "", "excel_native": False})(),
        type("Args", (), {"pptx": "", "pptx_native": False})(),
    ],
)
def test_local_office_workflows_remain_available(args):
    from zcoder.main import _has_direct_provider_feature

    assert not _has_direct_provider_feature(args)


@pytest.mark.parametrize(
    "command",
    [
        "skills_list",
        "skills_info",
        "check_deprecated",
        "upgrade_all",
        "list_server_tools",
        "mid_conv_tool_check",
    ],
)
def test_local_catalog_and_filesystem_commands_are_not_blocked(command):
    from zcoder.main import _has_direct_provider_feature

    args = type("Args", (), {command: True})()

    assert not _has_direct_provider_feature(args)


@pytest.mark.parametrize(
    "command",
    [
        "interactive",
        "excel",
        "pptx",
        "eval_run",
        "eval_compare",
        "ab_test",
        "score_prompt",
        "prompt_optimize",
        "code_agent",
        "code_agent_subagent",
        "code_agent_todo",
        "code_agent_slash",
        "code_agent_cost",
    ],
)
def test_local_coder_features_are_not_blocked(command):
    from zcoder.main import _has_direct_provider_feature

    args = type("Args", (), {command: True})()

    assert not _has_direct_provider_feature(args)


def test_remote_provider_is_not_treated_as_local_only(monkeypatch):
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)
    monkeypatch.setenv("ZCODER_PROVIDER", "gemini")
    args = type("Args", (), {"provider": None, "base_url": None})()

    from zcoder.main import _is_local_only

    assert not _is_local_only(args)


@pytest.mark.parametrize("provider", ["gemini", "invalid-provider"])
def test_local_mode_overrides_provider_environment(provider, monkeypatch):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.setenv("ZCODER_PROVIDER", provider)
    args = type("Args", (), {"provider": None, "base_url": None})()

    from zcoder.main import _is_local_only

    assert _is_local_only(args)


def test_local_mode_blocks_direct_provider_command_with_remote_override(monkeypatch, capsys):
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")
    monkeypatch.setenv("ZCODER_PROVIDER", "gemini")
    monkeypatch.setattr(sys, "argv", ["zcoder", "--thinking", "--prompt", "hello"])

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    assert "unavailable in local-only mode" in capsys.readouterr().err

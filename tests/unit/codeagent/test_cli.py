from pathlib import Path

from zcoder.agent.codeagent import cli
from zcoder.agent.codeagent.settings import Settings


def test_main_builds_agent_and_launches_tui(monkeypatch, tmp_path):
    calls = {}
    agent = object()
    monkeypatch.setattr(cli, "load_settings", lambda root: Settings())
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda root, **kwargs: calls.update(root=Path(root), kwargs=kwargs) or agent,
    )
    monkeypatch.setattr(cli, "run_agent_tui", lambda value: calls.update(launched=value))

    result = cli.main(
        [
            "--cwd",
            str(tmp_path),
            "--model",
            "test-local-model",
            "--no-discover-model",
        ]
    )

    assert result == 0
    assert calls["root"] == tmp_path.resolve()
    assert calls["kwargs"]["settings"].model == "test-local-model"
    assert calls["kwargs"]["mode"] is None
    assert calls["kwargs"]["allow_bypass"] is False
    assert calls["kwargs"]["discover_model"] is False
    assert calls["launched"] is agent


def test_bypass_requires_explicit_flag_and_passes_opt_in(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(cli, "load_settings", lambda root: Settings())
    monkeypatch.setattr(
        cli,
        "build_agent",
        lambda root, **kwargs: calls.update(kwargs=kwargs) or object(),
    )
    monkeypatch.setattr(cli, "run_agent_tui", lambda agent: None)

    cli.main(
        [
            "--cwd",
            str(tmp_path),
            "--dangerously-skip-permissions",
            "--no-discover-model",
        ]
    )

    assert calls["kwargs"]["mode"] == "bypass"
    assert calls["kwargs"]["allow_bypass"] is True

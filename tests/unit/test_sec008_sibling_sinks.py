"""tests/test_sec008_sibling_sinks.py — env filtering at remaining spawn sinks.

Follow-up to SEC-008: HookManager.fire (hooks_perms) and render_status_line
(settings) must spawn children with the filtered environment.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from zcoder.claude.enterprise import hooks_perms
from zcoder.claude.enterprise.hooks_perms import Hook, HookEvent, HookManager
from zcoder.claude.enterprise.settings import render_status_line


def test_hook_manager_fire_filters_env(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(hooks_perms, "HOOKS_FILE", Path(tmp_path) / "hooks.json")

    mgr = HookManager()
    mgr.hooks.append(Hook(event=HookEvent.PRE_TOOL_USE, command="echo-hook"))
    results = mgr.fire(HookEvent.PRE_TOOL_USE, tool_name="Bash")

    assert results and results[0].returncode == 0
    env = captured["env"]
    assert env["ZCODER_HOOK_EVENT"] == "pre_tool_use"
    assert env["ZCODER_TOOL_NAME"] == "Bash"
    assert env["PATH"] == "/usr/bin"
    assert "ANTHROPIC_API_KEY" not in env


def test_render_status_line_filters_env(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, input=None, capture_output=None, text=None, timeout=None, env=None):
        captured["env"] = env
        return subprocess.CompletedProcess(argv, 0, stdout="ready | 3 turns", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setattr(
        "zcoder.claude.enterprise.settings.load_settings",
        lambda: {"statusLine": {"command": "statusline-cmd"}},
    )

    line = render_status_line({"model": "m", "cwd": str(tmp_path), "turns": 3})
    assert line == "ready | 3 turns"
    assert captured["env"] is not None
    assert "GITHUB_TOKEN" not in captured["env"]

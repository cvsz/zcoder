"""tests/test_sec008_env_inheritance.py — Secrets/environment inheritance regressions.

Covers SEC-008:
- build_child_env drops secret-named variables from inherited environments
  and applies trusted overrides last;
- model-facing sinks (CodeAgent Bash tool, tool-registry run_python) spawn
  children with the filtered environment;
- HooksEngine children receive filtered env with operator overrides applied
  after filtering;
- backup/restore children never see the database password on argv and
  logged errors redact it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from zcoder.claude.capabilities.code import CodeAgent, CodeSession, HooksEngine
from zcoder.claude.tools.registry import build_code_tools_registry
from zcoder.core.security import build_child_env, is_secret_env_name
from zcoder.services.backup_restore import (
    BackupManager,
    RestoredStateVerification,
    _redact,
    _split_dsn_password,
)

# ── Primitive ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "BACKUP_ENCRYPTION_PASSWORD",
        "MY_DSN",
        "PGPASSWORD",
        "SOME_PASSWD",
        "DB_PASSWORD",
    ],
)
def test_is_secret_env_name_matches(name):
    assert is_secret_env_name(name) is True


@pytest.mark.parametrize(
    "name",
    ["PATH", "HOME", "ZCODER_SANDBOX", "LANG", "EDITOR", "VIRTUAL_ENV"],
)
def test_is_secret_env_name_allows(name):
    assert is_secret_env_name(name) is False


def test_build_child_env_filters_and_overrides():
    base = {
        "PATH": "/usr/bin",
        "ANTHROPIC_API_KEY": "sk-leak",
        "GITHUB_TOKEN": "gh-leak",
        "HOME": "/home/u",
    }
    env = build_child_env({"EXTRA_FLAG": "1"}, base=base)
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/u"
    assert env["EXTRA_FLAG"] == "1"
    assert "ANTHROPIC_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env


def test_build_child_env_override_can_reinject_deliberately():
    base = {"PATH": "/usr/bin", "OTHER_TOKEN": "leak"}
    env = build_child_env({"PGPASSWORD": "explicit"}, base=base)
    assert env["PGPASSWORD"] == "explicit"  # deliberate, trusted-code override
    assert "OTHER_TOKEN" not in env


# ── F1: CodeAgent Bash tool ───────────────────────────────────────────────


class _NoopHooks:
    def pre_tool_use(self, *_a, **_k):
        return {"allowed": True, "message": ""}

    def post_tool_use(self, *_a, **_k):
        return None


def test_bash_tool_spawns_filtered_env(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="(ok)", stderr="")

    monkeypatch.setattr("zcoder.claude.capabilities.code.subprocess.run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    session = CodeSession(cwd=str(tmp_path), model="test-model")
    result = CodeAgent(api_key="k", model="m")._execute_tool(
        "Bash",
        {"command": "echo hi"},
        session,
        _NoopHooks(),
        permission="bypassPermissions",
    )
    assert result == "(ok)"
    assert captured["env"]["PATH"] == "/usr/bin"
    assert "ANTHROPIC_API_KEY" not in captured["env"]
    assert "GITHUB_TOKEN" not in captured["env"]


# ── F2: tool-registry run_python ──────────────────────────────────────────


def test_run_python_spawns_filtered_env(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="1", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    reg = build_code_tools_registry(cwd=str(tmp_path))
    result = reg.execute("run_python", {"code": "print(1)"})
    assert result == "1"
    assert captured["env"]["PATH"] == "/usr/bin"
    assert "ANTHROPIC_API_KEY" not in captured["env"]


# ── F3: HooksEngine ───────────────────────────────────────────────────────


def test_hooks_receive_filtered_env_with_overrides(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, input=None, capture_output=None, text=None, timeout=None, env=None):
        captured["env"] = env
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    hooks = HooksEngine(
        {"PreToolUse": [{"command": "hook-cmd", "env": {"HOOK_MODE": "strict", "HOOK_TOKEN": "x"}}]}
    )
    hooks.fire("PreToolUse", {"tool": "Bash"})
    env = captured["env"]
    assert env["HOOK_MODE"] == "strict"  # explicit hook config preserved
    assert env["HOOK_TOKEN"] == "x"
    assert env["PATH"] == "/usr/bin"
    assert "ANTHROPIC_API_KEY" not in env


# ── F4: backup/restore DSN handling ───────────────────────────────────────


def test_split_dsn_password_strips_password():
    url = "postgresql://user:s3cret@db.example.com:5432/zcoder"
    safe_url, password = _split_dsn_password(url)
    assert "s3cret" not in safe_url
    assert password == "s3cret"
    assert safe_url == "postgresql://user@db.example.com:5432/zcoder"


def test_split_dsn_password_noop_without_password():
    url = "postgresql://db.example.com:5432/zcoder"
    safe_url, password = _split_dsn_password(url)
    assert safe_url == url
    assert password == ""


def test_redact_removes_secret():
    assert _redact("password s3cret invalid", "s3cret") == "password [redacted] invalid"


def test_pg_dump_keeps_password_off_argv(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        for a in argv:
            if a.startswith("--file="):
                Path(a.split("=", 1)[1]).write_bytes(b"dump")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    manager = BackupManager(
        database_url="postgresql://admin:pgpw123@localhost/db",
        backup_destination=str(tmp_path),
    )
    record = manager.run_pg_dump_backup()
    assert record.success is True
    argv = json.dumps(captured["argv"])
    assert "pgpw123" not in argv  # password never on the command line
    assert captured["env"]["PGPASSWORD"] == "pgpw123"
    assert "ANTHROPIC_API_KEY" not in captured["env"]  # filtered inheritance


def test_pg_dump_error_redacts_password(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="auth failed for pw-hunter")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = BackupManager(
        database_url="postgresql://admin:pw-hunter@localhost/db",
        backup_destination=str(tmp_path),
    )
    record = manager.run_pg_dump_backup()
    assert record.success is False
    assert "pw-hunter" not in (record.error or "")
    assert "[redacted]" in (record.error or "")


def test_pg_restore_keeps_password_off_argv(tmp_path, monkeypatch):
    dump_file = tmp_path / "b.sql.gz"
    dump_file.write_bytes(b"x")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    class M(BackupManager):
        def _verify_restored_state(self, *_a, **_k):
            return RestoredStateVerification()

    manager = M(
        database_url="postgresql://u:v@localhost/source",
        backup_destination=str(tmp_path),
    )
    result = manager.run_restore_drill(
        backup_id=dump_file.name.replace(".sql.gz", ""),
        target_database_url="postgresql://u:restorepw@localhost/target",
    )
    assert result.success is True
    assert "restorepw" not in json.dumps(captured["argv"])
    assert captured["env"]["PGPASSWORD"] == "restorepw"


def test_is_secret_env_name_passphrase_and_lowercase():
    assert is_secret_env_name("GPG_PASSPHRASE") is True
    assert is_secret_env_name("api_key") is True  # case-insensitive


def test_split_dsn_password_preserves_encoded_username():
    url = "postgresql://us%2Fer:p%40ss@localhost/db"
    safe_url, password = _split_dsn_password(url)
    assert password == "p@ss"  # decoded for PGPASSWORD
    assert "p%40ss" not in safe_url
    assert safe_url == "postgresql://us%2Fer@localhost/db"  # username kept encoded


def test_split_dsn_password_malformed_url_returns_unchanged():
    weird = "postgresql://user:pw@localhost:notaport/db"
    safe_url, password = _split_dsn_password(weird)
    assert safe_url == weird  # fail-safe: unchanged rather than crash
    assert password == ""

"""Regression tests for Slice E.6 plugin manifest provenance + permission validation."""

import json
from pathlib import Path

from zcoder.claude.tools.plugins import validate_plugin


def _write_manifest(plugin_dir: Path, data: dict) -> Path:
    mf = plugin_dir / ".claude-plugin" / "plugin.json"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(data))
    return mf


def _levels(findings, level):
    return [m for (lev, m) in findings if lev == level]


def test_trusted_provenance_with_source_info(tmp_path):
    _write_manifest(
        tmp_path, {"name": "ok", "provenance": {"source": "marketplace:trusted", "trusted": True}}
    )
    findings = validate_plugin(tmp_path)
    assert any("provenance.source=marketplace:trusted" in m for (_, m) in findings)


def test_trusted_provenance_empty_source_warns(tmp_path):
    _write_manifest(tmp_path, {"name": "ok", "provenance": {"source": "", "trusted": True}})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "warn")
    assert any("provenance.trusted=true" in m for (_, m) in findings)


def test_network_permission_warns(tmp_path):
    _write_manifest(tmp_path, {"name": "ok", "permissions": {"network": True}})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "warn")
    assert any("network access" in m for (_, m) in findings)


def test_filesystem_invalid_permission_errors(tmp_path):
    _write_manifest(tmp_path, {"name": "ok", "permissions": {"filesystem": "invalid"}})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "error")
    assert any("permissions.filesystem" in m for (_, m) in findings)


def test_tools_unknown_tool_warns(tmp_path):
    _write_manifest(tmp_path, {"name": "ok", "permissions": {"tools": ["Read", "FakeTool"]}})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "warn")
    assert any("unknown tool: FakeTool" in m for (_, m) in findings)


def test_tools_not_a_list_errors(tmp_path):
    _write_manifest(tmp_path, {"name": "ok", "permissions": {"tools": "Read"}})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "error")
    assert any("permissions.tools must be a list" in m for (_, m) in findings)


def test_no_manifest_auto_discovery_info(tmp_path):
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "info")
    assert any("no manifest found" in m for (_, m) in findings)


def test_valid_manifest_no_provenance_ok(tmp_path):
    _write_manifest(tmp_path, {"name": "ok"})
    findings = validate_plugin(tmp_path)
    assert _levels(findings, "ok")


def test_filesystem_allowed_values_pass(tmp_path):
    for fs in ("none", "readonly", "plugin", "write"):
        _write_manifest(tmp_path, {"name": "ok", "permissions": {"filesystem": fs}})
        findings = validate_plugin(tmp_path)
        assert not _levels(findings, "error"), f"filesystem={fs!r} should not error"

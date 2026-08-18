"""tests/test_claude_tools.py

Covers claude_tools.py's v1.24.0 server tool version bumps
(code_execution_20260521, web_search_20260318, web_fetch_20260318) and
the new response_inclusion parameter — see
docs/36_upgrade_v1.24.0_audit_and_impl.md Finding 1.
"""

import json

import zcoder.claude.tools.registry as mod
from zcoder.claude.tools.registry import RETIRED_TOOL_VERSIONS, SERVER_TOOLS, ToolCoder


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_urlopen(monkeypatch, captured: dict, response_body: dict = None):
    response_body = response_body or {"content": [], "usage": {}, "stop_reason": "end_turn"}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp(json.dumps(response_body).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)


def test_server_tools_defaults_bumped_to_v1_24_0_versions():
    assert SERVER_TOOLS["web_search"]["type"] == "web_search_20260318"
    assert SERVER_TOOLS["web_fetch"]["type"] == "web_fetch_20260318"
    assert SERVER_TOOLS["code_execution"]["type"] == "code_execution_20260521"


def test_retired_tool_versions_tracks_v1_24_0_supersessions():
    assert RETIRED_TOOL_VERSIONS["web_search_20260209"]["replacement"] == "web_search_20260318"
    assert RETIRED_TOOL_VERSIONS["web_fetch_20250910"]["replacement"] == "web_fetch_20260318"
    assert RETIRED_TOOL_VERSIONS["code_execution_20260120"]["replacement"] == "code_execution_20260521"


def test_check_retired_tool_version_flags_previous_defaults():
    assert mod.check_retired_tool_version("code_execution_20260120") is not None
    assert mod.check_retired_tool_version("web_search_20260209") is not None
    assert mod.check_retired_tool_version("code_execution_20260521") is None  # current, not retired


def test_generate_with_server_tools_response_inclusion_applied(monkeypatch):
    captured = {}
    _install_fake_urlopen(monkeypatch, captured)
    tc = ToolCoder(api_key="sk-test")

    tc.generate_with_server_tools("do it", ["web_search", "web_fetch"], response_inclusion="excluded")

    tools = captured["body"]["tools"]
    web_search = next(t for t in tools if t["name"] == "web_search")
    web_fetch = next(t for t in tools if t["name"] == "web_fetch")
    assert web_search["response_inclusion"] == "excluded"
    assert web_fetch["response_inclusion"] == "excluded"


def test_generate_with_server_tools_response_inclusion_omitted_by_default(monkeypatch):
    captured = {}
    _install_fake_urlopen(monkeypatch, captured)
    tc = ToolCoder(api_key="sk-test")

    tc.generate_with_server_tools("do it", ["web_search"])

    tools = captured["body"]["tools"]
    assert "response_inclusion" not in tools[0]


def test_generate_with_server_tools_response_inclusion_not_applied_to_other_tools(monkeypatch):
    captured = {}
    _install_fake_urlopen(monkeypatch, captured)
    tc = ToolCoder(api_key="sk-test")

    tc.generate_with_server_tools("do it", ["code_execution"], response_inclusion="excluded")

    tools = captured["body"]["tools"]
    assert "response_inclusion" not in tools[0]


def test_generate_with_server_tools_uses_bumped_code_execution_version(monkeypatch):
    captured = {}
    _install_fake_urlopen(monkeypatch, captured)
    tc = ToolCoder(api_key="sk-test")

    tc.generate_with_server_tools("do it", ["code_execution"])

    assert captured["body"]["tools"][0]["type"] == "code_execution_20260521"


def test_computer_use_tool_for_model_exists_and_is_callable():
    # Regression: this function's `def` line was previously missing, so it
    # didn't exist as a module attribute at all — its body had silently
    # become unreachable dead code appended to check_retired_tool_version().
    assert callable(mod.computer_use_tool_for_model)


def test_computer_use_tool_for_model_current_model_uses_2025_11_24():
    tool, beta = mod.computer_use_tool_for_model("claude-sonnet-5")
    assert tool["type"] == "computer_20251124"
    assert tool["name"] == "computer"
    assert beta == "computer-use-2025-11-24"


def test_computer_use_tool_for_model_older_model_uses_2025_01_24():
    tool, beta = mod.computer_use_tool_for_model("claude-sonnet-4-5")
    assert tool["type"] == "computer_20250124"
    assert beta == "computer-use-2025-01-24"


def test_computer_use_tool_for_model_respects_custom_dimensions():
    tool, _ = mod.computer_use_tool_for_model("claude-sonnet-5", width=1280, height=800)
    assert tool["display_width_px"] == 1280
    assert tool["display_height_px"] == 800


def test_generate_with_server_tools_computer_use_builds_tool_without_crashing(monkeypatch):
    # Regression: previously raised NameError (model/width/height undefined)
    # any time "computer_use" was requested, because computer_use_tool_for_model
    # didn't exist as a callable.
    captured = {}
    _install_fake_urlopen(monkeypatch, captured)
    tc = ToolCoder(api_key="sk-test", model="claude-sonnet-5")

    tc.generate_with_server_tools("take a screenshot", ["computer_use"])

    tools = captured["body"]["tools"]
    computer_tool = next(t for t in tools if t["name"] == "computer")
    assert computer_tool["type"] == "computer_20251124"
    assert computer_tool["display_width_px"] == SERVER_TOOLS["computer_use"]["display_width_px"]
    assert computer_tool["display_height_px"] == SERVER_TOOLS["computer_use"]["display_height_px"]


def test_validate_mid_conversation_tool_change_supported_models():
    from zcoder.claude.tools.registry import validate_mid_conversation_tool_change

    for model_id in ("claude-fable-5", "claude-mythos-5", "claude-opus-4-8", "claude-opus-5"):
        assert validate_mid_conversation_tool_change(model_id) is None


def test_validate_mid_conversation_tool_change_unsupported_model_warns():
    from zcoder.claude.tools.registry import validate_mid_conversation_tool_change

    warning = validate_mid_conversation_tool_change("claude-sonnet-5")
    assert warning is not None
    assert "claude-sonnet-5" in warning


def test_with_mid_conversation_tool_changes_adds_beta_header_for_supported_model():
    from zcoder.claude.tools.registry import (
        MID_CONVERSATION_TOOL_CHANGES_BETA,
        with_mid_conversation_tool_changes,
    )

    headers = with_mid_conversation_tool_changes({}, "claude-opus-5")
    assert MID_CONVERSATION_TOOL_CHANGES_BETA in headers["anthropic-beta"]


def test_with_mid_conversation_tool_changes_appends_to_existing_beta_header():
    from zcoder.claude.tools.registry import (
        MID_CONVERSATION_TOOL_CHANGES_BETA,
        with_mid_conversation_tool_changes,
    )

    headers = with_mid_conversation_tool_changes({"anthropic-beta": "some-other-beta"}, "claude-fable-5")
    assert "some-other-beta" in headers["anthropic-beta"]
    assert MID_CONVERSATION_TOOL_CHANGES_BETA in headers["anthropic-beta"]


def test_with_mid_conversation_tool_changes_noop_for_unsupported_model():
    from zcoder.claude.tools.registry import with_mid_conversation_tool_changes

    headers = {"anthropic-beta": "some-other-beta"}
    result = with_mid_conversation_tool_changes(headers, "claude-sonnet-5")
    assert result == headers

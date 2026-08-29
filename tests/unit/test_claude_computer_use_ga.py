"""Wire-level tests for GA computer-use and its legacy rollback path."""

import json

import pytest

import zcoder.claude.models.registry as models_module
from zcoder.claude.models.registry import (
    COMPUTER_USE_BETA,
    COMPUTER_USE_TOOLSET_GA,
    DEFAULT_COMPUTER_USE_SHAPE,
    ComputerUseCoder,
    computer_use_toolset_for_model,
)
from zcoder.core.exceptions import ZCoderError


def install_json_response(monkeypatch, captured, response=None):
    def fake_urlopen_json(request, timeout):
        captured["body"] = json.loads(request.data.decode())
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return response or {"content": [], "stop_reason": "end_turn"}

    monkeypatch.setattr(models_module, "urlopen_json", fake_urlopen_json)


def test_default_computer_use_shape_is_ga():
    assert DEFAULT_COMPUTER_USE_SHAPE == "ga"


def test_ga_request_uses_single_descriptor_without_beta_header(monkeypatch):
    captured = {}
    install_json_response(monkeypatch, captured)

    ComputerUseCoder(api_key="sk-test", model="claude-opus-4-8").run_task("open a terminal")

    tools = captured["body"]["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == COMPUTER_USE_TOOLSET_GA
    assert tools[0]["name"] == "computer"
    assert tools[0]["zoom"] is True
    assert tools[0]["batch_actions"] is True
    assert tools[0]["configs"]["bash"]["enabled"] is True
    assert tools[0]["configs"]["text_editor"]["enabled"] is True
    assert "anthropic-beta" not in captured["headers"]


def test_ga_request_respects_dimensions_and_custom_configs(monkeypatch):
    captured = {}
    install_json_response(monkeypatch, captured)
    configs = {"bash": {"enabled": False}}

    ComputerUseCoder(
        api_key="sk-test",
        model="claude-fable-5",
        width=1280,
        height=800,
        configs=configs,
    ).run_task("edit a file")

    tool = captured["body"]["tools"][0]
    assert tool["display_width_px"] == 1280
    assert tool["display_height_px"] == 800
    assert tool["configs"] == configs


def test_ga_response_returns_all_tool_calls_in_order(monkeypatch):
    captured = {}
    install_json_response(
        monkeypatch,
        captured,
        {
            "content": [
                {"type": "text", "text": "clicking then typing"},
                {"type": "tool_use", "id": "a1", "name": "computer", "input": {"action": "screenshot"}},
                {"type": "tool_use", "id": "a2", "name": "bash", "input": {"command": "ls"}},
            ],
            "stop_reason": "tool_use",
        },
    )

    result = ComputerUseCoder(api_key="sk-test", model="claude-mythos-5").run_task("do two things")

    assert [call["id"] for call in result["tool_calls"]] == ["a1", "a2"]
    assert result["text"] == "clicking then typing"
    assert result["stop_reason"] == "tool_use"


def test_ga_supported_models_pass_client_side_gating():
    for model in (
        "claude-fable-5",
        "claude-mythos-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
    ):
        assert computer_use_toolset_for_model(model)["type"] == COMPUTER_USE_TOOLSET_GA


def test_unsupported_ga_model_fails_before_http(monkeypatch):
    captured = {}
    install_json_response(monkeypatch, captured)

    with pytest.raises(ZCoderError) as exc:
        ComputerUseCoder(api_key="sk-test", model="claude-haiku-4-5").run_task("x")

    assert "claude-haiku-4-5" in str(exc.value)
    assert "body" not in captured


def test_ga_gating_error_lists_supported_models():
    with pytest.raises(ZCoderError) as exc:
        computer_use_toolset_for_model("claude-sonnet-4-5")

    message = str(exc.value)
    assert COMPUTER_USE_TOOLSET_GA in message
    for model in ("claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-sonnet-5", "claude-opus-4-8"):
        assert model in message


def test_legacy_opt_in_keeps_dated_tools_and_beta_header(monkeypatch):
    captured = {}
    install_json_response(monkeypatch, captured)

    ComputerUseCoder(api_key="sk-test", model="claude-sonnet-4-5", toolset="legacy").run_task("old shape")

    assert [tool["type"] for tool in captured["body"]["tools"]] == [
        "computer_20250124",
        "bash_20250124",
        "text_editor_20250124",
    ]
    assert captured["headers"]["anthropic-beta"] == COMPUTER_USE_BETA


def test_unknown_computer_use_toolset_is_rejected():
    with pytest.raises(ValueError):
        ComputerUseCoder(api_key="sk-test", toolset="beta")

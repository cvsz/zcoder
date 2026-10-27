"""tests/test_claude_structured.py

claude_structured.py had no prior test coverage. Added alongside the
v1.30.0 fix that removed the unconditional (and, since GA, unnecessary)
structured-outputs-2025-11-13 beta header and the dead, unused
StructuredCoder.BETA attribute — see docs/42_upgrade_v1.30.0.md.
"""

import json
from unittest.mock import patch

import zcoder.agent.capabilities.structured as mod


def _fake_urlopen_json(payload_text):
    def _fake(req, timeout=120):
        return {"content": [{"type": "text", "text": payload_text}]}

    return _fake


def test_structured_request_uses_local_coder_without_api_headers():
    sc = mod.StructuredCoder(api_key="sk-test")

    with patch("zcoder.agent.capabilities.structured.Coder.generate", return_value="{}") as generate:
        sc.json_object("say hi")
    generate.assert_called_once()


def test_bare_class_has_no_dead_beta_attribute():
    assert not hasattr(mod.StructuredCoder, "BETA")


def test_json_object_still_uses_ga_output_config_format():
    sc = mod.StructuredCoder(api_key="sk-test")
    captured_req = {}

    def _fake_urlopen_json(req, timeout=120):
        captured_req["body"] = json.loads(req.data)
        return {"content": [{"type": "text", "text": '{"ok": true}'}]}

    with patch(
        "zcoder.agent.capabilities.structured.Coder.generate", return_value='{"ok": true}'
    ) as generate:
        result = sc.json_object("say hi")

    generate.assert_called_once()
    assert result == {"ok": True}


def test_json_schema_mode_validates_required_fields():
    sc = mod.StructuredCoder(api_key="sk-test")
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

    def _fake_urlopen_json(req, timeout=120):
        return {"content": [{"type": "text", "text": '{"name": "ok"}'}]}

    with patch("zcoder.agent.capabilities.structured.Coder.generate", return_value='{"name": "ok"}'):
        result = sc.json_schema("extract the name", schema)

    assert result == {"name": "ok"}


def test_json_schema_mode_raises_on_missing_required_field():
    sc = mod.StructuredCoder(api_key="sk-test")
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}

    def _fake_urlopen_json(req, timeout=120):
        return {"content": [{"type": "text", "text": "{}"}]}

    with patch("zcoder.agent.capabilities.structured.Coder.generate", return_value="{}"):
        try:
            sc.json_schema("extract the name", schema)
            raise AssertionError("expected ValueError for missing required field")
        except ValueError as e:
            assert "name" in str(e)


def test_local_generation_does_not_forward_api_key():
    sc = mod.StructuredCoder(api_key="sk-never-forward", model="local-model")

    with patch("zcoder.agent.capabilities.structured.Coder") as coder_type:
        coder_type.return_value.generate.return_value = "{}"
        sc.json_object("say hi")

    kwargs = coder_type.call_args.kwargs
    assert kwargs["model"] == "local-model"
    assert "api_key" not in kwargs
    assert sc.api_key == ""

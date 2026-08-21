"""Regression tests for Slice E.9 — hook event name validation."""

from zcoder.claude.capabilities.code import HOOK_EVENTS, HooksEngine


def test_known_events_preserved():
    engine = HooksEngine(
        {
            "PreToolUse": [{"command": "echo ok"}],
            "PostToolUse": [{"command": "echo done"}],
        }
    )
    assert "PreToolUse" in engine.config
    assert "PostToolUse" in engine.config


def test_unknown_event_rejected():
    engine = HooksEngine({"FakeEvent": [{"command": "echo bad"}]})
    assert "FakeEvent" not in engine.config


def test_mixed_known_and_unknown():
    engine = HooksEngine(
        {
            "PreToolUse": [{"command": "echo ok"}],
            "UnknownEvent": [{"command": "echo bad"}],
        }
    )
    assert "PreToolUse" in engine.config
    assert "UnknownEvent" not in engine.config


def test_all_known_events_accepted():
    handlers = [{"command": "echo ok"}]
    config = {event: handlers for event in HOOK_EVENTS}
    engine = HooksEngine(config)
    for event in HOOK_EVENTS:
        assert event in engine.config


def test_empty_config_ok():
    engine = HooksEngine({})
    assert engine.config == {}


def test_none_config_ok():
    engine = HooksEngine()
    assert engine.config == {}


def test_with_plugins_filters_unknown():
    base = HooksEngine({"PreToolUse": [{"command": "echo base"}]})
    plugin_hooks = {"UnknownPluginEvent": [{"command": "echo bad", "_plugin": "test"}]}
    merged = dict(base.config)
    for event, handlers in plugin_hooks.items():
        merged.setdefault(event, [])
        merged[event] = merged[event] + handlers
    result = HooksEngine(merged)
    assert "PreToolUse" in result.config
    assert "UnknownPluginEvent" not in result.config

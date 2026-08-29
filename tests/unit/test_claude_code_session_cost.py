"""Regression coverage for model-aware CodeSession cost accounting."""

from zcoder.claude.capabilities.code import CodeSession


def test_code_session_uses_current_sonnet5_pricing():
    session = CodeSession(model="claude-sonnet-5")

    session.add_turn("assistant", "done", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})

    assert session.cost_usd == 12.0


def test_code_session_preserves_legacy_sonnet45_pricing():
    session = CodeSession(model="claude-sonnet-4-5")

    session.add_turn("assistant", "done", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})

    # Sonnet 4.5 retains its long-context surcharge above 200K input tokens.
    assert session.cost_usd == 28.5

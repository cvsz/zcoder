"""Unit tests for pure functions in zcoder.agent.capabilities.code."""

from __future__ import annotations

from zcoder.agent.capabilities.code import estimate_tokens, render_context_report


class TestEstimateTokens:
    """Tests for estimate_tokens() — ~4 chars per token heuristic."""

    def test_empty_string(self):
        assert estimate_tokens("") == 1

    def test_single_char(self):
        assert estimate_tokens("a") == 1

    def test_four_chars(self):
        assert estimate_tokens("abcd") == 1

    def test_five_chars(self):
        assert estimate_tokens("abcde") == 2

    def test_exact_multiple(self):
        # 8 chars -> (8+3)//4 = 2
        assert estimate_tokens("abcdefgh") == 2

    def test_long_text(self):
        text = "x" * 100
        assert estimate_tokens(text) == 25  # (100+3)//4 = 25

    def test_rounds_up(self):
        # Always round up so warnings come early
        assert estimate_tokens("a" * 5) == 2  # (5+3)//4 = 2
        assert estimate_tokens("a" * 6) == 2  # (6+3)//4 = 2
        assert estimate_tokens("a" * 7) == 2  # (7+3)//4 = 2
        assert estimate_tokens("a" * 8) == 2  # (8+3)//4 = 2
        assert estimate_tokens("a" * 9) == 3  # (9+3)//4 = 3

    def test_never_zero(self):
        # Guaranteed minimum of 1
        for n in range(0, 100):
            assert estimate_tokens("x" * n) >= 1

    def test_unicode(self):
        # len() counts characters, not bytes
        text = "héllo wörld"
        assert estimate_tokens(text) == max(1, (len(text) + 3) // 4)


class TestRenderContextReport:
    """Tests for render_context_report() — plain-text budget bar."""

    def test_minimal_report(self):
        rep = {"window": 1000, "used": 250, "system": 100, "tools": 50, "conversation": 100}
        out = render_context_report(rep, model="test-model")
        assert "Context budget (test-model)" in out
        assert "system" in out
        assert "tools" in out
        assert "conversation" in out
        assert "free" in out
        assert "tok" in out

    def test_unknown_model_default(self):
        rep = {"window": 1000, "used": 0, "system": 0, "tools": 0, "conversation": 0}
        out = render_context_report(rep)
        assert "Context budget (unknown model)" in out

    def test_live_vs_estimates_only(self):
        rep = {"window": 1000, "used": 100, "system": 50, "tools": 25, "conversation": 25}
        live = render_context_report(rep, live=True)
        estimates = render_context_report(rep, live=False)
        assert "estimates only" in estimates
        assert "estimates only" not in live

    def test_percent_of_window(self):
        rep = {"window": 1000, "used": 500, "system": 0, "tools": 0, "conversation": 0}
        out = render_context_report(rep)
        assert "50% of window" in out

    def test_full_window(self):
        rep = {"window": 1000, "used": 1000, "system": 0, "tools": 0, "conversation": 0}
        out = render_context_report(rep)
        assert "100% of window" in out

    def test_missing_keys_default_to_zero(self):
        # rep with missing keys should not crash
        rep = {"window": 1000}
        out = render_context_report(rep)
        assert "Context budget (unknown model)" in out
        assert "0 tok" in out

    def test_bar_width(self):
        rep = {"window": 100, "used": 50, "system": 0, "tools": 0, "conversation": 0}
        out = render_context_report(rep)
        # Just verify the report renders without error
        assert out

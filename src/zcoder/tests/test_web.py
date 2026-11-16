"""Tests for zcoder.agent.codeagent.web - Web dashboard backend."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zcoder.agent.codeagent.web import AuthLimiter, HostGuard, WebConfig, generate_token, is_loopback


class TestWebConfig:
    """Tests for WebConfig dataclass."""

    def test_creation_defaults(self):
        config = WebConfig(root=Path("/tmp"), token="a" * 32)
        assert config.root == Path("/tmp").resolve()
        assert config.token == "a" * 32
        assert config.host == "127.0.0.1"
        assert config.port == 8421
        assert config.max_connections == 4
        assert config.max_prompt_chars == 100_000
        assert config.prompts_per_minute == 30
        assert config.permission_timeout == 600.0

    def test_creation_with_custom_values(self):
        config = WebConfig(
            root=Path("/custom"),
            token="b" * 32,
            host="0.0.0.0",
            port=9999,
            max_connections=10,
            max_prompt_chars=50_000,
            prompts_per_minute=60,
            permission_timeout=300.0,
        )
        assert config.port == 9999
        assert config.max_connections == 10
        assert config.max_prompt_chars == 50_000
        assert config.prompts_per_minute == 60
        assert config.permission_timeout == 300.0

    def test_token_too_short(self):
        with pytest.raises(ValueError, match="web token must be at least 16 characters"):
            WebConfig(root=Path("/tmp"), token="short")

    def test_token_exactly_16(self):
        config = WebConfig(root=Path("/tmp"), token="a" * 16)
        assert config.token == "a" * 16

    def test_token_longer_than_16(self):
        config = WebConfig(root=Path("/tmp"), token="a" * 100)
        assert config.token == "a" * 100

    def test_extra_hosts(self):
        config = WebConfig(
            root=Path("/tmp"),
            token="a" * 32,
            extra_hosts=("example.com", "192.168.1.1"),
        )
        assert "example.com" in config.allowed_hosts
        assert "192.168.1.1" in config.allowed_hosts

    def test_extra_origins(self):
        config = WebConfig(
            root=Path("/tmp"),
            token="a" * 32,
            extra_origins=("https://example.com",),
        )
        assert "https://example.com" in config.allowed_origins

    def test_allowed_hosts_includes_loopback(self):
        config = WebConfig(root=Path("/tmp"), token="a" * 32)
        assert "127.0.0.1" in config.allowed_hosts
        assert "localhost" in config.allowed_hosts
        assert "::1" in config.allowed_hosts


class TestGenerateToken:
    """Tests for generate_token function."""

    def test_generates_token(self):
        token = generate_token()
        assert isinstance(token, str)
        assert len(token) > 32  # token_urlsafe(32) produces ~43 chars

    def test_generates_unique_tokens(self):
        token1 = generate_token()
        token2 = generate_token()
        assert token1 != token2


class TestIsLoopback:
    """Tests for is_loopback function."""

    def test_ipv4_loopback(self):
        assert is_loopback("127.0.0.1") is True
        assert is_loopback("127.0.0.2") is True
        assert is_loopback("0.0.0.0") is False

    def test_ipv6_loopback(self):
        assert is_loopback("::1") is True

    def test_hostname_loopback(self):
        assert is_loopback("localhost") is True

    def test_non_loopback(self):
        assert is_loopback("192.168.1.1") is False
        assert is_loopback("8.8.8.8") is False
        assert is_loopback("example.com") is False


class TestAuthLimiter:
    """Tests for AuthLimiter class."""

    def test_creation(self):
        limiter = AuthLimiter(max_failures=3, window=60.0)
        assert limiter.max == 3
        assert limiter.window == 60.0

    def test_not_blocked_initially(self):
        limiter = AuthLimiter(max_failures=3, window=60.0)
        assert limiter.blocked("client1") is False

    def test_blocked_after_max_failures(self):
        limiter = AuthLimiter(max_failures=3, window=60.0)
        limiter.fail("client1")
        limiter.fail("client1")
        limiter.fail("client1")
        assert limiter.blocked("client1") is True

    def test_not_blocked_under_limit(self):
        limiter = AuthLimiter(max_failures=3, window=60.0)
        limiter.fail("client1")
        limiter.fail("client1")
        assert limiter.blocked("client1") is False

    def test_clients_independent(self):
        limiter = AuthLimiter(max_failures=1, window=60.0)
        limiter.fail("client1")
        assert limiter.blocked("client1") is True
        assert limiter.blocked("client2") is False

    def test_window_expiry(self):
        import time

        limiter = AuthLimiter(max_failures=1, window=0.1)
        limiter.fail("client1")
        assert limiter.blocked("client1") is True
        time.sleep(0.15)
        assert limiter.blocked("client1") is False


class TestHostGuard:
    """Tests for HostGuard middleware."""

    def test_creation(self):
        app = MagicMock()
        guard = HostGuard(app, {"127.0.0.1", "localhost"})
        assert guard.app is app
        assert guard.allowed == {"127.0.0.1", "localhost"}

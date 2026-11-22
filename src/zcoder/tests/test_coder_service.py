"""Tests for zcoder.services.coder - LLM provider client."""

import json
from unittest.mock import MagicMock, patch

import pytest

from zcoder.core.exceptions import APIError, AuthenticationError, RateLimitError, TransientAPIError
from zcoder.services.coder import Coder


class TestCoderInit:
    """Tests for Coder initialization."""

    def test_default_init(self):
        coder = Coder()
        assert coder.model == "zcoder-flash"
        assert coder.provider == "local"
        assert coder.base_url == "http://127.0.0.1:8080/v1"
        assert coder.temperature == 0.3
        assert coder.max_tokens == 4096

    def test_custom_params(self):
        coder = Coder(
            api_key="test-key",
            model="custom-model",
            temperature=0.7,
            max_tokens=2048,
            provider="ollama",
            base_url="http://localhost:11434/v1",
        )
        assert coder.model == "custom-model"
        assert coder.temperature == 0.7
        assert coder.max_tokens == 2048
        assert coder.provider == "ollama"
        assert coder.base_url == "http://localhost:11434/v1"

    def test_env_var_model(self, monkeypatch):
        monkeypatch.setenv("ZCODER_MODEL", "env-model")
        coder = Coder()
        assert coder.model == "env-model"

    def test_env_var_base_url(self, monkeypatch):
        monkeypatch.setenv("ZCODER_BASE_URL", "http://custom.example.com/v1")
        coder = Coder()
        assert coder.base_url == "http://custom.example.com/v1"

    def test_env_var_api_key(self, monkeypatch):
        monkeypatch.setenv("ZCODER_API_KEY", "test-api-key")
        coder = Coder()
        assert coder.model == "zcoder-flash"


class TestCoderGenerate:
    """Tests for Coder.generate method."""

    def test_generate_success(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        from unittest.mock import MagicMock, patch

        with patch("zcoder.services.coder._open_local") as mock_open:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Hello, world!",
                            }
                        }
                    ]
                }
            ).encode()
            mock_open.return_value.__enter__.return_value = mock_response

            result = coder.generate("Hello")
            assert result == "Hello, world!"

    def test_generate_with_system(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        from unittest.mock import MagicMock, patch

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "System response",
                        }
                    }
                ]
            }
        ).encode()

        with patch("zcoder.services.coder._open_local") as mock_open:
            mock_open.return_value.__enter__.return_value = mock_response
            result = coder.generate("Hello", system="You are helpful")
            assert result == "System response"

    def test_generate_auth_error(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        import urllib.error
        from io import BytesIO
        from unittest.mock import patch

        err_body = json.dumps({"error": {"message": "Invalid API key"}}).encode()
        http_err = urllib.error.HTTPError("http://127.0.0.1:8080/v1/chat/completions", 401, "Unauthorized", {}, BytesIO(err_body))

        with patch("zcoder.services.coder._open_local", side_effect=http_err):
            result = coder.generate("Hello")
            assert "API ERROR 401" in result

    def test_generate_rate_limit(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        import urllib.error
        from io import BytesIO
        from unittest.mock import patch

        err_body = json.dumps({"error": {"message": "Rate limited"}}).encode()
        http_err = urllib.error.HTTPError("http://127.0.0.1:8080/v1/chat/completions", 429, "Too Many Requests", {}, BytesIO(err_body))

        with patch("zcoder.services.coder._open_local", side_effect=http_err):
            result = coder.generate("Hello")
            assert "API ERROR 429" in result

    def test_generate_transient_error(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        import urllib.error
        from io import BytesIO
        from unittest.mock import patch

        err_body = json.dumps({"error": {"message": "Server error"}}).encode()
        http_err = urllib.error.HTTPError("http://127.0.0.1:8080/v1/chat/completions", 500, "Internal Server Error", {}, BytesIO(err_body))

        with patch("zcoder.services.coder._open_local", side_effect=http_err):
            result = coder.generate("Hello")
            assert "[ERROR]" in result

    def test_generate_invalid_response(self):
        coder = Coder(api_key="test-key", model="test-model")

        import json
        from unittest.mock import MagicMock, patch

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"not_choices": {}}).encode()

        with patch("zcoder.services.coder._open_local") as mock_open:
            mock_open.return_value.__enter__.return_value = mock_response
            result = coder.generate("Hello")
            assert "[ERROR]" in result

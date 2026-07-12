"""tests/conftest.py — shared fixtures"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own config file path so tests never read/write
    a real ~/.ai-coder-config.json on the machine running the suite."""
    fake_config = tmp_path / ".ai-coder-config.json"
    monkeypatch.setattr("config.CONFIG_PATH", str(fake_config))
    yield fake_config


@pytest.fixture(autouse=True)
def no_real_api_key(monkeypatch):
    """Prevent tests from accidentally hitting the real API because a
    developer happens to have ANTHROPIC_API_KEY set in their shell."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture
def fake_logger_setup():
    from logging_config import setup_logging
    setup_logging(level="DEBUG", fmt="text")

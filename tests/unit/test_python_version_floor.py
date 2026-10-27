"""Runtime compatibility tests for the supported Python version floor."""

from types import SimpleNamespace

from zcoder.core import health


def test_health_check_rejects_python_311(monkeypatch):
    monkeypatch.setattr(
        health,
        "sys",
        SimpleNamespace(version_info=(3, 11, 9), version="3.11.9"),
    )

    result = health._check_python_version()

    assert not result.ok
    assert "requires >= 3.12" in result.detail


def test_health_check_accepts_python_312(monkeypatch):
    monkeypatch.setattr(
        health,
        "sys",
        SimpleNamespace(version_info=(3, 12, 0), version="3.12.0"),
    )

    result = health._check_python_version()

    assert result.ok
    assert "requires >= 3.12" not in result.detail

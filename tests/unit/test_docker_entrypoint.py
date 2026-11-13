from __future__ import annotations

import pytest

from scripts.docker_entrypoint import configure_database_url


def test_database_url_uses_dedicated_zcoder_database_and_role(tmp_path):
    secret = tmp_path / "postgresql.password"
    secret.write_text("a" * 64, encoding="utf-8")
    env = {"ZCODER_POSTGRES_PASSWORD_FILE": str(secret)}

    result = configure_database_url(env)

    assert result == f"postgresql://zcoder:{'a' * 64}@zpostgressql:5432/zcoder_db"
    assert env["DATABASE_URL"] == result


def test_explicit_database_url_is_preserved():
    original = "postgresql://override@db.example/other"
    env = {"DATABASE_URL": original, "ZCODER_POSTGRES_PASSWORD_FILE": "/missing"}

    assert configure_database_url(env) == original
    assert env["DATABASE_URL"] == original


def test_missing_mounted_secret_fails_without_exposing_path(tmp_path):
    secret_path = tmp_path / "missing-secret"
    env = {"ZCODER_POSTGRES_PASSWORD_FILE": str(secret_path)}

    with pytest.raises(RuntimeError, match="secret file is unavailable") as exc_info:
        configure_database_url(env)

    assert str(secret_path) not in str(exc_info.value)


@pytest.mark.parametrize("password", ["", "short", "z" * 64])
def test_invalid_mounted_secret_fails_closed(tmp_path, password):
    secret = tmp_path / "postgresql.password"
    secret.write_text(password, encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid format"):
        configure_database_url({"ZCODER_POSTGRES_PASSWORD_FILE": str(secret)})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ZCODER_POSTGRES_HOST", "db.example/path", "DNS name or IPv4"),
        ("ZCODER_POSTGRES_PORT", "70000", "between 1 and 65535"),
    ],
)
def test_invalid_database_endpoint_fails_closed(tmp_path, key, value, message):
    secret = tmp_path / "postgresql.password"
    secret.write_text("a" * 64, encoding="utf-8")
    env = {"ZCODER_POSTGRES_PASSWORD_FILE": str(secret), key: value}

    with pytest.raises(RuntimeError, match=message):
        configure_database_url(env)

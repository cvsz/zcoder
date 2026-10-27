from __future__ import annotations

import pytest

from scripts import local_postgres
from zcoder.infrastructure.stores.enterprise_postgres import ENTERPRISE_PG_ROLES, ENTERPRISE_PG_SCHEMA
from zcoder.infrastructure.stores.postgres import POSTGRES_SCHEMA


def test_enterprise_role_ddl_does_not_embed_application_credentials():
    assert "zcoder_app LOGIN;" in ENTERPRISE_PG_ROLES
    assert "PASSWORD '" not in ENTERPRISE_PG_ROLES.upper()
    assert "placeholder" not in ENTERPRISE_PG_ROLES.lower()


def test_job_schema_defaults_select_the_local_model():
    local_model = "zqwen2.5-coder-7b-instruct-q4_k_m"
    assert f"model TEXT NOT NULL DEFAULT '{local_model}'" in ENTERPRISE_PG_SCHEMA
    assert f"model TEXT NOT NULL DEFAULT '{local_model}'" in POSTGRES_SCHEMA


def test_password_accepts_generated_hex_credential(tmp_path, monkeypatch):
    path = tmp_path / "postgresql.password"
    path.write_text("a" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(local_postgres, "PASSWORD_FILE", path)

    assert local_postgres._password() == "a" * 64


@pytest.mark.parametrize("value", ["short", "a" * 63, "g" * 64, "a" * 63 + "' OR TRUE --"])
def test_password_rejects_unexpected_credential_format(tmp_path, monkeypatch, value):
    path = tmp_path / "postgresql.password"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setattr(local_postgres, "PASSWORD_FILE", path)

    with pytest.raises(RuntimeError, match="credential file is invalid"):
        local_postgres._password()

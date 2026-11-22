"""Integration tests for credential resolution flow and .env config loading."""

from __future__ import annotations

import os

import pytest

from zcoder.config import settings as _settings_mod
from zcoder.credentials.credential_seam import (
    CredentialError,
    CredentialInfo,
    CredentialKey,
    CredentialProvider,
    CredentialRecord,
    CredentialRef,
    ResolvedCredential,
    credentialRef,
    is_credential_ref_name,
)


class TestCredentialRef:
    """Tests for CredentialRef branded type."""

    def test_parse_valid_name(self):
        ref = CredentialRef.parse("DEEPSEEK_API_KEY")
        assert str(ref) == "DEEPSEEK_API_KEY"
        assert isinstance(ref, str)

    def test_parse_rejects_invalid(self):
        with pytest.raises(ValueError, match="credential ref"):
            CredentialRef.parse("123-invalid")
        with pytest.raises(ValueError, match="credential ref"):
            CredentialRef.parse("has spaces")
        with pytest.raises(ValueError, match="credential ref"):
            CredentialRef.parse("has-dash")

    def test_credentialRef_helper(self):
        ref = credentialRef("OPENAI_API_KEY")
        assert str(ref) == "OPENAI_API_KEY"
        # brandString is compile-time branding only; at runtime it's a plain str
        assert isinstance(ref, str)

    def test_is_credential_ref_name(self):
        assert is_credential_ref_name("API_KEY") is True
        assert is_credential_ref_name("DEEPSEEK_API_KEY") is True
        assert is_credential_ref_name("_private_key") is True
        assert is_credential_ref_name("123invalid") is False
        assert is_credential_ref_name("has-dash") is False
        assert is_credential_ref_name("has space") is False
        assert is_credential_ref_name("") is False


class TestCredentialKey:
    """Tests for CredentialKey branded type."""

    def test_parse_valid_key(self):
        key = CredentialKey.parse("deepseek/my-key-id")
        assert str(key) == "deepseek/my-key-id"

    def test_parse_rejects_invalid(self):
        with pytest.raises(ValueError, match="must be"):
            CredentialKey.parse("no-slash")
        with pytest.raises(ValueError, match="must be"):
            CredentialKey.parse("a/b/c")
        with pytest.raises(ValueError, match="must match"):
            CredentialKey.parse("DeepSeek/key")  # uppercase in scope
        with pytest.raises(ValueError, match="must match"):
            CredentialKey.parse("deepseek/Key-Id")  # uppercase in id

    def test_parse_rejects_empty_segments(self):
        with pytest.raises(ValueError):
            CredentialKey.parse("/key")
        with pytest.raises(ValueError):
            CredentialKey.parse("scope/")


class TestMockCredentialProvider:
    """Tests using a mock CredentialProvider to verify resolution flow."""

    class InMemoryProvider(CredentialProvider):
        """In-memory CredentialProvider for testing."""

        def __init__(self):
            self._store: dict[str, str] = {}
            self._records: dict[str, CredentialRecord] = {}

        def resolve(self, ref: CredentialRef) -> ResolvedCredential | None:
            value = self._store.get(str(ref))
            if value is None or value == "":
                return None
            return ResolvedCredential(value=value, source="provider")

        def describe(self, ref: CredentialRef) -> CredentialInfo:
            value = self._store.get(str(ref), "")
            return CredentialInfo(
                configured=bool(value and value != ""),
                kind="secret",
                writable=True,
            )

        def set(self, ref: CredentialRef, value: str) -> None:
            if not value:
                raise CredentialError("empty values are not allowed; use unset")
            self._store[str(ref)] = value

        def unset(self, ref: CredentialRef) -> None:
            self._store.pop(str(ref), None)

        def readRecord(self, key: CredentialKey) -> CredentialRecord | None:
            return self._records.get(str(key))

        def describeRecord(self, key: CredentialKey) -> CredentialInfo:
            record = self._records.get(str(key))
            return CredentialInfo(
                configured=record is not None and bool(record.value),
                kind=record.kind if record else None,
                writable=True,
            )

        def listRecords(self):
            from zcoder.credentials.credential_seam import CredentialRecordEntry

            return [
                CredentialRecordEntry(key=CredentialKey.parse(k), kind=r.kind)
                for k, r in self._records.items()
            ]

        def modifyRecord(
            self,
            key: CredentialKey,
            mutate,
        ):
            k = str(key)
            current = self._records.get(k)
            result = mutate(current)
            if result is None:
                # returning None means delete/leave untouched per spec
                if result is None and current is not None:
                    del self._records[k]
                return current
            self._records[k] = result
            return result

        def deleteRecord(self, key: CredentialKey) -> None:
            self._records.pop(str(key), None)

    def test_resolve_returns_value_from_provider(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("DEEPSEEK_API_KEY")
        provider.set(ref, "sk-abc123")

        result = provider.resolve(ref)
        assert result is not None
        assert result.value == "sk-abc123"
        assert result.source == "provider"

    def test_resolve_returns_none_for_unset(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("MISSING_KEY")

        result = provider.resolve(ref)
        assert result is None

    def test_resolve_returns_none_for_empty_value(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("EMPTY_KEY")
        provider._store[str(ref)] = ""

        result = provider.resolve(ref)
        assert result is None

    def test_describe_reports_configured(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("DEEPSEEK_API_KEY")
        provider.set(ref, "sk-abc123")

        info = provider.describe(ref)
        assert info.configured is True
        assert info.kind == "secret"
        assert info.writable is True

    def test_describe_reports_unconfigured(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("MISSING_KEY")

        info = provider.describe(ref)
        assert info.configured is False

    def test_set_and_unset(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("TEST_KEY")

        provider.set(ref, "secret-value")
        assert provider.resolve(ref) is not None

        provider.unset(ref)
        assert provider.resolve(ref) is None

    def test_set_rejects_empty_value(self):
        provider = self.InMemoryProvider()
        ref = CredentialRef.parse("TEST_KEY")

        with pytest.raises(CredentialError):
            provider.set(ref, "")

    def test_record_read_modify_write(self):
        provider = self.InMemoryProvider()
        key = CredentialKey.parse("deepseek/plugin-1")

        # Initially absent
        assert provider.readRecord(key) is None

        # modifyRecord creates a new record
        result = provider.modifyRecord(key, lambda _: CredentialRecord(kind="api_key", value="token-123"))
        assert result is not None
        assert result.value == "token-123"

        # readRecord returns the stored value
        record = provider.readRecord(key)
        assert record is not None
        assert record.value == "token-123"

        # modifyRecord updates existing record
        result = provider.modifyRecord(
            key, lambda rec: CredentialRecord(kind=rec.kind, value="token-456") if rec else None
        )
        assert result is not None
        assert result.value == "token-456"

        # deleteRecord removes it
        provider.deleteRecord(key)
        assert provider.readRecord(key) is None

    def test_list_records_excludes_values(self):
        provider = self.InMemoryProvider()
        provider.modifyRecord(
            CredentialKey.parse("plugin-a/key-1"),
            lambda _: CredentialRecord(kind="api_key", value="secret-value"),
        )
        provider.modifyRecord(
            CredentialKey.parse("plugin-b/key-2"),
            lambda _: CredentialRecord(kind="oauth", value="other-secret"),
        )

        entries = provider.listRecords()
        keys = {str(e.key) for e in entries}
        assert keys == {"plugin-a/key-1", "plugin-b/key-2"}
        # Values should not be leaked through entries
        for entry in entries:
            assert not hasattr(entry, "value") or "secret" not in str(entry.value)


class TestEnvConfigLoading:
    """Integration tests for .env config loading and env var overrides."""

    def test_config_defaults(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ZCODER_MODEL", raising=False)
        monkeypatch.delenv("ZCODER_BASE_URL", raising=False)
        monkeypatch.delenv("ZCODER_PROVIDER", raising=False)

        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = str(tmp_path / "nonexistent.json")
        try:
            config = _settings_mod.Config()
            assert config.get("model") == "zcoder-flash"
            assert config.get("provider") == "openai_compatible"
            assert config.get("base_url") == "http://localhost:11434"
        finally:
            _settings_mod.CONFIG_PATH = original_path

    def test_env_var_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCODER_MODEL", "custom-model")
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "2048")
        monkeypatch.setenv("ZCODER_ALLOW_NETWORK", "false")


        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = str(tmp_path / "nonexistent.json")

        try:
            config = _settings_mod.Config()
            assert config.get("model") == "custom-model"
            assert config.get("max_tokens") == 2048
            assert config.get("allow_network") is False
        finally:
            _settings_mod.CONFIG_PATH = original_path

    def test_env_var_invalid_falls_back_to_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCODER_MAX_TOKENS", "not-a-number")


        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = str(tmp_path / "nonexistent.json")

        try:
            config = _settings_mod.Config()
            assert config.get("max_tokens") == 8192
        finally:
            _settings_mod.CONFIG_PATH = original_path

    def test_config_persistence_round_trip(self, monkeypatch, tmp_path):


        config_path = os.path.join(tmp_path, "test-config.json")
        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = config_path

        try:
            config = _settings_mod.Config()
            config.set("model", "persisted-model")
            config.set("timeout_ms", 5000)

            monkeypatch.delenv("ZCODER_MODEL", raising=False)
            # Reload from file
            config2 = _settings_mod.Config()
            assert config2.get("model") == "persisted-model"
            assert config2.get("timeout_ms") == 5000
        finally:
            _settings_mod.CONFIG_PATH = original_path

    def test_env_var_overrides_file_value(self, monkeypatch, tmp_path):
        import json


        config_path = os.path.join(tmp_path, "test-config.json")
        with open(config_path, "w") as f:
            json.dump({"model": "file-model"}, f)

        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = config_path

        try:
            monkeypatch.delenv("ZCODER_MODEL", raising=False)
            config = _settings_mod.Config()
            assert config.get("model") == "file-model"

            monkeypatch.delenv("ZCODER_MODEL", raising=False)
            monkeypatch.setenv("ZCODER_MODEL", "env-model")
            config2 = _settings_mod.Config()
            assert config2.get("model") == "env-model"
        finally:
            _settings_mod.CONFIG_PATH = original_path

    def test_env_var_api_key(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZCODER_API_KEY", "sk-test-12345")


        original_path = _settings_mod.CONFIG_PATH
        _settings_mod.CONFIG_PATH = str(tmp_path / "nonexistent.json")

        try:
            config = _settings_mod.Config()
            assert config.get("api_key") == "sk-test-12345"
        finally:
            _settings_mod.CONFIG_PATH = original_path

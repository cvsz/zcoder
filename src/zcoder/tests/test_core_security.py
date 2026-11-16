"""Tests for zcoder.core.security - branded IDs and credential provider."""

import pytest

from zcoder.core.security import (
    CredentialKey,
    brandNumber,
    brandSessionId,
    brandSessionSeq,
    brandString,
    brandToolCallId,
    credentialKey,
    credentialKeyId,
    credentialKeyScope,
    credentialRef,
    is_branded,
    isCredentialRefName,
    parseCredentialKey,
)


class TestBrandedIds:
    """Tests for branded ID types."""

    def test_brand_string(self):
        session_id = brandString("session-123")
        assert isinstance(session_id, str)
        assert session_id == "session-123"

    def test_brand_number(self):
        seq = brandNumber(42)
        assert isinstance(seq, float)
        assert seq == 42.0

    def test_brand_session_id(self):
        sid = brandSessionId("session-abc")
        assert isinstance(sid, str)
        assert sid == "session-abc"

    def test_brand_session_seq(self):
        seq = brandSessionSeq(42)
        assert isinstance(seq, float)
        assert seq == 42.0

    def test_brand_tool_call_id(self):
        tcid = brandToolCallId("tool-123")
        assert isinstance(tcid, str)
        assert tcid == "tool-123"

    def test_is_branded(self):
        branded = brandString("test-value")
        assert is_branded(branded, "SessionId") is False  # wrong brand
        assert isinstance(branded, str)

    def test_credential_key(self):
        key = credentialKey("my-plugin", "my-id")
        assert isinstance(key, str)
        assert key == "my-plugin/my-id"

    def test_credential_key_invalid_segment(self):
        with pytest.raises(ValueError):
            credentialKey("Invalid Scope", "my-id")
        with pytest.raises(ValueError):
            credentialKey("my-scope", "Invalid Id")

    def test_parse_credential_key(self):
        key = credentialKey("my-plugin", "my-key")
        parsed = parseCredentialKey(key)
        assert parsed == key

    def test_credential_key_scope(self):
        key = credentialKey("my-plugin", "my-id")
        assert credentialKeyScope(key) == "my-plugin"

    def test_credential_key_id(self):
        key = credentialKey("my-plugin", "my-id")
        assert credentialKeyId(key) == "my-id"

    def test_credential_ref(self):
        ref = credentialRef("ZCODER_API_KEY")
        assert isinstance(ref, str)
        assert ref == "ZCODER_API_KEY"

    def test_credential_ref_invalid(self):
        with pytest.raises(ValueError):
            credentialRef("invalid key!")

    def test_is_credential_ref_name(self):
        assert isCredentialRefName("ZCODER_API_KEY") is True
        assert isCredentialRefName("my-key-123") is True
        assert isCredentialRefName("invalid key!") is False
        assert isCredentialRefName("123-start") is False


class TestCredentialKey:
    """Tests for CredentialKey branded type."""

    def test_create(self):
        key = credentialKey("my-plugin", "my-id")
        assert isinstance(key, str)
        assert key == "my-plugin/my-id"

    def test_parse(self):
        key = credentialKey("my-plugin", "my-id")
        parsed = CredentialKey.parse(key)
        assert parsed == key

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            CredentialKey.parse("invalid-key")

    def test_scope_and_id(self):
        key = credentialKey("my-plugin", "my-id")
        assert credentialKeyScope(key) == "my-plugin"
        assert credentialKeyId(key) == "my-id"

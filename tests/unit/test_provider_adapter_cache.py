from zcoder.agent.orchestration import adapters


def test_adapter_cache_uses_opaque_credential_id(monkeypatch):
    adapters._PROVIDER_ADAPTER_CACHE.clear()
    monkeypatch.setattr(adapters, "_CREDENTIAL_CACHE_IDS", {})

    first = adapters.get_adapter(
        "ollama",
        base_url="http://127.0.0.1:11434",
        api_key="credential-one",
    )
    same = adapters.get_adapter(
        "ollama",
        base_url="http://127.0.0.1:11434",
        api_key="credential-one",
    )
    other = adapters.get_adapter(
        "ollama",
        base_url="http://127.0.0.1:11434",
        api_key="credential-two",
    )

    assert first is same
    assert first is not other
    assert all("credential-" not in key for key in adapters._PROVIDER_ADAPTER_CACHE)
    # The cache key carries an opaque surrogate, never the credential itself.
    ids = adapters._CREDENTIAL_CACHE_IDS
    assert set(ids) == {"credential-one", "credential-two"}
    assert all(isinstance(value, str) and len(value) == 16 for value in ids.values())
    adapters._PROVIDER_ADAPTER_CACHE.clear()

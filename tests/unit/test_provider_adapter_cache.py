from zcoder.agent.orchestration import adapters


def test_adapter_cache_uses_process_keyed_credential_fingerprint(monkeypatch):
    adapters._PROVIDER_ADAPTER_CACHE.clear()
    monkeypatch.setattr(adapters, "_CACHE_FINGERPRINT_KEY", b"x" * 32)

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
    adapters._PROVIDER_ADAPTER_CACHE.clear()

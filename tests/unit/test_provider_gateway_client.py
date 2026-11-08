"""Regression tests for ZCoder's local-only inference boundary."""

import json
import urllib.request

import pytest

import zcoder.core.resilience as resilience
import zcoder.services.coder as coder_module


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        coder_module,
        "_default_breaker",
        resilience.CircuitBreaker(failure_threshold=10, reset_timeout=0.01),
    )


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_generate_uses_loopback_endpoint_without_forwarding_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_open(request: urllib.request.Request, timeout: float) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({"choices": [{"message": {"content": "local response"}}]})

    monkeypatch.setattr(coder_module, "_open_local", fake_open)
    coder = coder_module.Coder(
        model="qwen-local",
        provider="openai_compatible",
        base_url="http://127.0.0.1:8080/v1",
    )

    assert coder.generate("hello") == "local response"

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == "http://127.0.0.1:8080/v1/chat/completions"
    assert request.get_header("Authorization") is None
    assert request.data is not None
    assert json.loads(request.data.decode("utf-8"))["model"] == "qwen-local"
    assert captured["timeout"] == 120


@pytest.mark.parametrize(
    "base_url",
    [
        "http://192.168.1.100:8080/v1",
        "http://example.com/v1",
        "https://127.0.0.1:8080/v1",
        "http://user:password@127.0.0.1:8080/v1",
        "http://127.0.0.1:8080/v1?redirect=1",
        "http://127.0.0.1:8080/v1#fragment",
    ],
)
def test_generate_rejects_non_loopback_or_ambiguous_endpoints(
    base_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_network_call(*args: object, **kwargs: object) -> None:
        pytest.fail("disallowed endpoint must be rejected before network access")

    monkeypatch.setattr(coder_module, "_open_local", unexpected_network_call)
    coder = coder_module.Coder(model="qwen-local", base_url=base_url)

    result = coder.generate("must not leave this machine")

    assert result == (
        "[ERROR] ZCODER_BASE_URL must point to a loopback local "
        "OpenAI-compatible endpoint."
    )


@pytest.mark.parametrize("provider", ["anthropic", "nvidia", "hosted"])
def test_generate_rejects_non_local_provider(
    provider: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_network_call(*args: object, **kwargs: object) -> None:
        pytest.fail("unsupported provider must be rejected before network access")

    monkeypatch.setattr(coder_module, "_open_local", unexpected_network_call)
    coder = coder_module.Coder(
        model="qwen-local",
        provider=provider,
        base_url="http://127.0.0.1:8080/v1",
    )

    assert coder.generate("must remain local") == (
        "[ERROR] The command-line coding client only supports local inference."
    )


@pytest.mark.parametrize(
    "options",
    [
        {"service_tier": "auto"},
        {"inference_geo": "us"},
        {"fast_mode": True},
    ],
)
def test_generate_rejects_cloud_only_options(
    options: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_network_call(*args: object, **kwargs: object) -> None:
        pytest.fail("cloud-only option must fail closed before network access")

    monkeypatch.setattr(coder_module, "_open_local", unexpected_network_call)
    coder = coder_module.Coder(
        model="qwen-local",
        base_url="http://127.0.0.1:8080/v1",
        **options,
    )

    assert coder.generate("must remain local") == (
        "[ERROR] Cloud-only inference options are unavailable with the local model."
    )


def test_local_transport_rejects_http_redirects() -> None:
    handler = coder_module._RejectRedirects()
    request = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions")

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "http://127.0.0.1:9090/collect",
    )

    assert redirected is None

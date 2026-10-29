from __future__ import annotations

import io
import json
from urllib.error import URLError

import pytest

from zgpu.integrations.embeddings import EmbeddingProviderError, OpenAICompatibleEmbeddingProvider


class _Response(io.BytesIO):
    def __init__(self, body: bytes, url: str):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class _Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response


def _provider(response: bytes, *, response_url="http://127.0.0.1:11434/v1/embeddings"):
    provider = OpenAICompatibleEmbeddingProvider(
        "http://127.0.0.1:11434/v1", "embedding-test-model", "test-secret", timeout=2.0
    )
    opener = _Opener(_Response(response, response_url))
    provider._opener = opener
    return provider, opener


def test_embedding_client_sends_configured_model_and_validates_vector():
    body = json.dumps({"data": [{"index": 0, "embedding": [0.25, -0.5, 0.75]}]}).encode()
    provider, opener = _provider(body)

    assert provider.embed("A bounded local knowledge query") == [0.25, -0.5, 0.75]
    assert opener.request.full_url.endswith("/v1/embeddings")
    assert opener.request.get_method() == "POST"
    assert opener.request.get_header("Authorization") == "Bearer test-secret"
    payload = json.loads(opener.request.data)
    assert payload == {"model": "embedding-test-model", "input": "A bounded local knowledge query"}
    assert opener.timeout == 2.0


@pytest.mark.parametrize(
    "body",
    [
        b'{"data":[]}',
        b'{"data":[{"embedding":[]}]}',
        b'{"data":[{"embedding":[0,0]}]}',
        b'{"data":[{"embedding":[NaN]}]}',
        b'{"data":[{"embedding":[true]}]}',
    ],
)
def test_embedding_client_rejects_invalid_vectors(body):
    provider, _ = _provider(body)
    with pytest.raises(EmbeddingProviderError, match=r"invalid|non-finite|non-numeric|zero"):
        provider.embed("query")


def test_embedding_client_rejects_redirect_and_public_http():
    provider, _ = _provider(b'{"data":[{"embedding":[1]}]}', response_url="http://127.0.0.1/redirect")
    with pytest.raises(EmbeddingProviderError, match="redirected"):
        provider.embed("query")
    with pytest.raises(ValueError, match="loopback"):
        OpenAICompatibleEmbeddingProvider("http://embedding.example/v1", "model", "token")
    with pytest.raises(ValueError, match="newline or NUL"):
        OpenAICompatibleEmbeddingProvider("http://localhost/v1", "model", "bad\nkey")


def test_embedding_client_sanitizes_transport_failures():
    provider = OpenAICompatibleEmbeddingProvider("http://localhost:11434/v1", "model", "token")
    provider._opener = _Opener(error=URLError("sensitive transport details"))
    with pytest.raises(EmbeddingProviderError, match="could not reach") as error:
        provider.embed("query")
    assert "sensitive" not in str(error.value)


def test_embedding_client_rejects_oversized_response():
    provider, _ = _provider(b" " * (OpenAICompatibleEmbeddingProvider.MAX_RESPONSE_BYTES + 1))
    with pytest.raises(EmbeddingProviderError, match="exceeded 1 MiB"):
        provider.embed("query")

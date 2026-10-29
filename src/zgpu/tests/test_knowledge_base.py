import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from zgpu.integrations.knowledge_base import KnowledgeBaseClient, KnowledgeBaseError


class _Response:
    def __init__(self, body: bytes, url: str):
        self._body = io.BytesIO(body)
        self.status = 200
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url


def _client() -> KnowledgeBaseClient:
    return KnowledgeBaseClient("https://knowledge.example", "service-key")


def test_client_restricts_origins_credentials_and_timeouts():
    for url in (
        "http://knowledge.example",
        "https://user:pass@knowledge.example",
        "https://knowledge.example/api/v1",
        "https://knowledge.example?debug=1",
        "https://knowledge.example:0",
        "https://knowledge.example:99999",
    ):
        with pytest.raises(ValueError):
            KnowledgeBaseClient(url, "service-key")

    assert KnowledgeBaseClient("http://127.0.0.1:8080", "key").base_url == "http://127.0.0.1:8080/api/v1"
    with pytest.raises(ValueError):
        KnowledgeBaseClient("https://knowledge.example", "key", timeout=0)


def test_search_uses_scoped_key_and_returns_only_safe_result_fields():
    client = _client()
    result_body = {
        "results": [
            {
                "document_id": "doc-1",
                "document_name": "guide.md",
                "tenant_id": "private-tenant",
                "chunk_id": "private-chunk",
                "chunk_index": 3,
                "score": 0.9,
                "text": "Relevant content",
                "source_uri": "/srv/private/guide.md",
            }
        ]
    }
    response = _Response(json.dumps(result_body).encode(), "https://knowledge.example/api/v1/search")
    with patch.object(client, "_open", return_value=response) as open_request:
        results = client.search("  kernel compiler  ")

    request = open_request.call_args.args[0]
    assert request.get_header("X-api-key") == "service-key"
    assert json.loads(request.data) == {"query": "kernel compiler", "top_k": 5}
    assert results == [{"id": "doc-1", "title": "guide.md", "excerpt": "Relevant content", "score": 0.9}]
    assert "private-tenant" not in str(results)
    assert "/srv/private" not in str(results)


def test_document_listing_and_search_snippets_are_bounded_and_allowlisted():
    client = _client()
    documents = _Response(
        b'[{"id":"doc-1","name":"guide.md","tenant_id":"private-tenant","status":"completed",'
        b'"size_bytes":24,"chunk_count":2,"source_uri":"/srv/private/guide.md"}]',
        "https://knowledge.example/api/v1/documents",
    )
    with patch.object(client, "_open", return_value=documents):
        assert client.list_documents() == [
            {
                "id": "doc-1",
                "name": "guide.md",
                "status": "completed",
                "size_bytes": 24,
                "chunk_count": 2,
                "created_at": "",
                "updated_at": "",
                "error": None,
            }
        ]

    search = _Response(
        json.dumps(
            {
                "results": [
                    {
                        "document_id": "doc-1",
                        "document_name": "x" * 200,
                        "score": 0.5,
                        "text": "x" * 1000,
                    }
                ]
            }
        ).encode(),
        "https://knowledge.example/api/v1/search",
    )
    with patch.object(client, "_open", return_value=search):
        result = client.search("kernel")
    assert len(result[0]["title"]) == 120
    assert len(result[0]["excerpt"]) == client.MAX_EXCERPT_CHARS


def test_upload_uses_bounded_multipart_async_ingestion():
    client = _client()
    response = _Response(
        b'{"document":{"id":"doc-1","name":"guide.md","status":"queued"},"job":{"id":"job-1","status":"queued"}}',
        "https://knowledge.example/api/v1/ingest/async",
    )
    with patch.object(client, "_open", return_value=response) as open_request:
        result = client.ingest_file("guide.md", b"# zGPU\n")

    request = open_request.call_args.args[0]
    assert request.get_header("X-api-key") == "service-key"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=zgpu-")
    assert b'name="file"; filename="guide.md"' in request.data
    assert request.data.endswith(
        b"# zGPU\n\r\n--" + request.get_header("Content-type").split("boundary=")[1].encode() + b"--\r\n"
    )
    assert result == {
        "document": {"id": "doc-1", "name": "guide.md"},
        "job": {"id": "job-1", "status": "queued"},
    }

    for filename, content in (
        ("../guide.md", b"x"),
        ("guide.docx", b"x"),
        ("guide.md\r\nX:x", b"x"),
        ("guide.md", b""),
    ):
        with pytest.raises(ValueError):
            client.ingest_file(filename, content)
    with pytest.raises(ValueError):
        client.ingest_file("large.txt", b"x" * (client.MAX_RESPONSE_BYTES + 1))


def test_job_listing_and_cancellation_quote_identifiers():
    client = _client()
    jobs = _Response(
        b'[{"id":"job-1","document_id":"doc-1","status":"processing","attempts":2,'
        b'"tenant_id":"private-tenant","updated_at":"2026-10-23T00:00:00Z"}]',
        "https://knowledge.example/api/v1/ingest/jobs?limit=10",
    )
    with patch.object(client, "_open", return_value=jobs) as open_request:
        assert client.list_ingestion_jobs(limit=10) == [
            {
                "id": "job-1",
                "document_id": "doc-1",
                "status": "processing",
                "attempts": 2,
                "updated_at": "2026-10-23T00:00:00Z",
                "error": None,
            }
        ]
    assert open_request.call_args.args[0].full_url.endswith("/ingest/jobs?limit=10")

    no_content = _Response(b"", "https://knowledge.example/api/v1/ingest/jobs/job%2F1")
    no_content.status = 204
    with patch.object(client, "_open", return_value=no_content) as open_request:
        assert client.cancel_ingestion_job("job/1") is None
    assert open_request.call_args.args[0].full_url.endswith("/ingest/jobs/job%2F1")


def test_client_rejects_redirects_oversized_or_malformed_responses():
    client = _client()
    redirect = _Response(b"{}", "https://unexpected.example/api/v1/health")
    with patch.object(client, "_open", return_value=redirect), pytest.raises(KnowledgeBaseError) as raised:
        client.health()
    assert raised.value.code == "REDIRECT_REJECTED"

    redirect_response = urllib.error.HTTPError(
        "https://knowledge.example/api/v1/health",
        302,
        "Found",
        {"Location": "https://unexpected.example"},
        io.BytesIO(b"{}"),
    )
    with (
        patch.object(client, "_open", side_effect=redirect_response),
        pytest.raises(KnowledgeBaseError) as raised,
    ):
        client.health()
    assert raised.value.code == "REDIRECT_REJECTED"

    oversized = _Response(b" " * (client.MAX_RESPONSE_BYTES + 1), "https://knowledge.example/api/v1/health")
    with patch.object(client, "_open", return_value=oversized), pytest.raises(KnowledgeBaseError) as raised:
        client.health()
    assert raised.value.code == "UPSTREAM_RESPONSE_TOO_LARGE"

    malformed = _Response(b"not-json", "https://knowledge.example/api/v1/health")
    with patch.object(client, "_open", return_value=malformed), pytest.raises(KnowledgeBaseError) as raised:
        client.health()
    assert raised.value.code == "INVALID_UPSTREAM_RESPONSE"

    error = urllib.error.HTTPError(
        "https://knowledge.example/api/v1/search", 403, "Forbidden", {}, io.BytesIO(b"secret body")
    )
    with patch.object(client, "_open", side_effect=error), pytest.raises(KnowledgeBaseError) as raised:
        client.search("query")
    assert raised.value.status == 403
    assert "secret" not in str(raised.value)

    with (
        patch.object(client, "_open", side_effect=ConnectionResetError("reset")),
        pytest.raises(KnowledgeBaseError) as raised,
    ):
        client.health()
    assert raised.value.code == "UPSTREAM_UNAVAILABLE"

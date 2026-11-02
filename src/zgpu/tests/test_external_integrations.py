"""Contract tests for optional external service adapters."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from zgpu.integrations.engineering_jobs import EngineeringJobsClient, EngineeringJobsError
from zgpu.integrations.knowledge_chat import KnowledgeChatClient, KnowledgeChatError
from zgpu.integrations.openai_provider import OpenAICompatibleProvider, OpenAIProviderError


class _Response:
    def __init__(self, body: bytes, url: str = "https://engineering.example/api/v1/jobs"):
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


def _client() -> EngineeringJobsClient:
    return EngineeringJobsClient("https://engineering.example", "test-token")


def test_client_restricts_origins_and_port_values():
    for url in (
        "http://engineering.example",
        "https://user:pass@engineering.example",
        "https://engineering.example/path",
        "https://engineering.example:99999",
        "https://engineering.example:0",
    ):
        with pytest.raises(ValueError):
            EngineeringJobsClient(url, "token")

    assert EngineeringJobsClient("http://[::1]:8080", "token").base_url == "http://[::1]:8080"


def test_submit_job_sends_bearer_token_and_idempotency_key():
    client = _client()
    response = _Response(b'{"id":"job-1","status":"ready"}')
    with patch.object(client, "_open", return_value=response) as open_request:
        result = client.submit_job("  compile kernel  ", idempotency_key="request-1")

    request = open_request.call_args.args[0]
    assert result == {"id": "job-1", "status": "ready"}
    assert request.get_header("Authorization") == "Bearer test-token"
    assert request.get_header("Idempotency-key") == "request-1"
    assert json.loads(request.data) == {
        "task": "compile kernel",
        "runtime": "direct",
        "budget_usd": 0.0,
    }


def test_submit_job_can_override_service_default_model():
    client = _client()
    response = _Response(b'{"id":"job-1","status":"ready"}')
    with patch.object(client, "_open", return_value=response) as open_request:
        client.submit_job("compile kernel", model="custom-model")
    assert json.loads(open_request.call_args.args[0].data)["model"] == "custom-model"


def test_job_identifier_is_url_encoded():
    client = _client()
    response = _Response(b'{"jobs":[]} ', "https://engineering.example/api/v1/jobs/a%2Fb")
    with patch.object(client, "_open", return_value=response) as open_request:
        client.get_job("a/b")
    assert open_request.call_args.args[0].full_url.endswith("/api/v1/jobs/a%2Fb")


def test_cancel_job_uses_delete_with_encoded_id_and_idempotency_key():
    client = _client()
    response = _Response(
        b'{"id":"a/b","status":"CANCELLED"}', "https://engineering.example/api/v1/jobs/a%2Fb"
    )
    with patch.object(client, "_open", return_value=response) as open_request:
        result = client.cancel_job("a/b", idempotency_key="cancel-1")

    request = open_request.call_args.args[0]
    assert result == {"id": "a/b", "status": "CANCELLED"}
    assert request.method == "DELETE"
    assert request.full_url.endswith("/api/v1/jobs/a%2Fb")
    assert request.get_header("Idempotency-key") == "cancel-1"

    with pytest.raises(ValueError):
        client.cancel_job("job-1", idempotency_key="bad\nkey")


def test_job_list_uses_bounded_pagination():
    client = _client()
    with patch.object(client, "_request", return_value={"data": [], "pagination": {}}) as request:
        client.list_jobs(limit=25, offset=50)
    assert request.call_args.args == ("GET", "/api/v1/jobs?limit=25&offset=50")
    for limit, offset in ((0, 0), (101, 0), (20, -1), (True, 0)):
        with pytest.raises(ValueError):
            client.list_jobs(limit=limit, offset=offset)


def test_rejects_redirect_and_oversized_response():
    client = _client()
    redirect = _Response(b"{}", "https://attacker.example/collect")
    with (
        patch.object(client, "_open", return_value=redirect),
        pytest.raises(EngineeringJobsError, match="redirected") as raised,
    ):
        client.list_jobs()
    assert raised.value.code == "REDIRECT_REJECTED"

    large = _Response(
        b" " * (client.MAX_RESPONSE_BYTES + 1),
        "https://engineering.example/api/v1/jobs?limit=20&offset=0",
    )
    with patch.object(client, "_open", return_value=large), pytest.raises(EngineeringJobsError) as raised:
        client.list_jobs()
    assert raised.value.code == "UPSTREAM_RESPONSE_TOO_LARGE"


def test_structured_http_errors_are_preserved_without_leaking_token():
    client = _client()
    response = io.BytesIO(b'{"error":{"code":"DENIED","message":"not allowed","request_id":"r1"}}')
    response.code = 403
    response.headers = {}
    error = urllib.error.HTTPError("https://engineering.example/api/v1/jobs", 403, "Forbidden", {}, response)
    with (
        patch.object(client, "_open", side_effect=error),
        pytest.raises(EngineeringJobsError, match="zGPU Engineering") as raised,
    ):
        client.list_jobs()
    assert raised.value.status == 403
    assert raised.value.code == "DENIED"
    assert raised.value.request_id == "r1"
    assert "test-token" not in str(raised.value)


def test_rejects_invalid_job_arguments_before_network_call():
    client = _client()
    with patch.object(client, "_open") as open_request:
        with pytest.raises(ValueError):
            client.submit_job(" ")
        with pytest.raises(ValueError):
            client.submit_job("task", budget_usd=float("nan"))
        with pytest.raises(ValueError):
            client.submit_job("task", idempotency_key="x" * 257)
        with pytest.raises(ValueError):
            client.list_jobs(limit=0)
    open_request.assert_not_called()


class _StreamResponse(_Response):
    def readline(self, size=-1):
        return self._body.readline(size)

    def close(self):
        self._body.close()


class _ProviderResponse(_StreamResponse):
    pass


def test_openai_provider_restricts_endpoint_and_uses_zgpu_aliases():
    for url in (
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1/../admin",
        "https://provider.example/v1?token=secret",
    ):
        with pytest.raises(ValueError):
            OpenAICompatibleProvider(url, "secret")

    assert (
        OpenAICompatibleProvider("http://127.0.0.1:8080/v1", "token").base_url == "http://127.0.0.1:8080/v1"
    )


def test_openai_provider_maps_models_hides_provider_identity_and_routes_completion():
    client = OpenAICompatibleProvider("https://provider.example/v1", "provider-secret")
    model_response = _ProviderResponse(
        b'{"data":[{"id":"vendor/model-large"}]}', "https://provider.example/v1/models"
    )
    completion_response = _ProviderResponse(
        b'{"id":"completion-1","model":"vendor/model-large","choices":[{"message":{"content":"ok"}}]}',
        "https://provider.example/v1/chat/completions",
    )
    with patch.object(
        client._opener, "open", side_effect=[model_response, completion_response]
    ) as open_request:
        model = client.list_models()[0]
        alias = model["id"]
        result = client.create_completion(
            {"model": alias, "messages": [{"role": "user", "content": "hello"}]}
        )

    assert alias.startswith("zgpu-remote-")
    assert model["owned_by"] == "zgpu"
    assert "vendor" not in json.dumps(model)
    request = open_request.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer provider-secret"
    assert json.loads(request.data)["model"] == "vendor/model-large"
    assert result["model"] == alias
    assert result["choices"][0]["message"]["content"] == "ok"
    assert "provider-secret" not in str(result)


def test_openai_provider_streams_bounded_events_with_zgpu_model_alias():
    client = OpenAICompatibleProvider("https://provider.example/v1", "provider-secret")
    client._models = {"zgpu-remote-test": "vendor/model"}
    response = _ProviderResponse(
        b'data: {"model":"vendor/model","choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n',
        "https://provider.example/v1/chat/completions",
    )
    events = []
    with patch.object(client._opener, "open", return_value=response):
        result = client.create_completion(
            {"model": "zgpu-remote-test", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            event_callback=events.append,
        )

    assert result is None
    assert events[0]["model"] == "zgpu-remote-test"
    assert events[0]["choices"][0]["delta"]["content"] == "hello"
    assert response._body.closed


def test_openai_provider_rejects_missing_stream_completion_marker():
    client = OpenAICompatibleProvider("https://provider.example/v1", "token")
    client._models = {"zgpu-remote-test": "vendor/model"}
    response = _ProviderResponse(
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
        "https://provider.example/v1/chat/completions",
    )
    with (
        patch.object(client._opener, "open", return_value=response),
        pytest.raises(OpenAIProviderError, match="completion marker"),
    ):
        client.create_completion(
            {"model": "zgpu-remote-test", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            event_callback=lambda _event: None,
        )
    assert response._body.closed


def _knowledge_client() -> KnowledgeChatClient:
    return KnowledgeChatClient("https://knowledge.example", "knowledge-token")


def test_knowledge_session_uses_bearer_auth_and_validates_response():
    client = _knowledge_client()
    response = _Response(
        b'{"chat_session_id":"session-1"}',
        "https://knowledge.example/api/chat/create-chat-session",
    )
    with patch.object(client, "_open", return_value=response) as open_request:
        assert client.create_chat_session(persona_id=42, project_id="proj-1") == "session-1"
    request = open_request.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer knowledge-token"
    assert json.loads(request.data) == {"persona_id": 42, "project_id": "proj-1"}

    with pytest.raises(ValueError):
        client.create_chat_session(persona_id=True)


def test_knowledge_stream_yields_json_packets_and_closes_response():
    client = _knowledge_client()
    response = _StreamResponse(
        b'{"type":"message_start"}\n{"type":"message_delta","content":"hello"}\n{"type":"stop"}\n',
        "https://knowledge.example/api/chat/send-chat-message",
    )
    with patch.object(client, "_open", return_value=response) as open_request:
        packets = list(client.stream_message("hi", "session-1"))
    request = open_request.call_args.args[0]
    payload = json.loads(request.data)
    assert payload["origin"] == "api"
    assert packets == [
        {"type": "message_start"},
        {"type": "message_delta", "content": "hello"},
        {"type": "stop"},
    ]
    assert response._body.closed


def test_knowledge_stream_rejects_malformed_or_oversized_packets():
    client = _knowledge_client()
    malformed = _StreamResponse(b"not-json\n", "https://knowledge.example/api/chat/send-chat-message")
    with patch.object(client, "_open", return_value=malformed), pytest.raises(KnowledgeChatError) as raised:
        list(client.stream_message("hi", "session-1"))
    assert raised.value.code == "INVALID_UPSTREAM_STREAM"
    assert malformed._body.closed

    oversized = _StreamResponse(
        b"x" * (client.MAX_PACKET_BYTES + 1) + b"\n",
        "https://knowledge.example/api/chat/send-chat-message",
    )
    with patch.object(client, "_open", return_value=oversized), pytest.raises(KnowledgeChatError) as raised:
        list(client.stream_message("hi", "session-1"))
    assert raised.value.code == "UPSTREAM_PACKET_TOO_LARGE"


def test_knowledge_rejects_insecure_remote_origins_redirects_and_bad_payloads():
    with pytest.raises(ValueError):
        KnowledgeChatClient("http://knowledge.example", "token")
    client = _knowledge_client()
    redirect = _Response(b"{}", "https://attacker.example/collect")
    with patch.object(client, "_open", return_value=redirect), pytest.raises(KnowledgeChatError) as raised:
        client.create_chat_session()
    assert raised.value.code == "REDIRECT_REJECTED"
    with patch.object(client, "_open") as open_request:
        with pytest.raises(ValueError):
            list(client.stream_message(" ", "session"))
        open_request.assert_not_called()

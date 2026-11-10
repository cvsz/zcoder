"""Regression tests for the legacy MCP SSE request/response transport."""

import json

import pytest

from zcoder.agent.codeagent.mcp_server import build_fastapi_app


def _test_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    return TestClient(build_fastapi_app(_EchoMCPServer()))


class _EchoMCPServer:
    async def handle(self, message):
        if message.get("method") == "notifications/initialized":
            return None
        return {"result": {"method": message.get("method")}}


def test_sse_session_routes_request_and_response_over_same_stream():
    client = _test_client()

    with client.stream("GET", "/mcp/sse", headers={"Accept": "text/event-stream"}) as stream:
        assert stream.status_code == 200
        lines = iter(stream.iter_lines())
        event_line = next(lines)
        endpoint_line = next(lines)
        assert event_line == "event: endpoint"
        assert endpoint_line.startswith("data: /mcp/messages/")

        message_endpoint = endpoint_line.removeprefix("data: ")
        response = client.post(
            message_endpoint,
            json={"jsonrpc": "2.0", "id": "request-1", "method": "ping", "params": {}},
        )
        assert response.status_code == 202

        assert next(lines) == "event: message"
        message_line = next(lines)
        assert message_line.startswith("data: ")
        payload = json.loads(message_line.removeprefix("data: "))
        assert payload == {
            "result": {"method": "ping"},
            "jsonrpc": "2.0",
            "id": "request-1",
        }


def test_sse_message_endpoint_rejects_unknown_session():
    client = TestClient(build_fastapi_app(_EchoMCPServer()))

    response = client.post(
        "/mcp/messages/not-a-session",
        json={"jsonrpc": "2.0", "id": "request-1", "method": "ping"},
    )

    assert response.status_code == 404


def test_sse_message_endpoint_rejects_non_json_rpc_payload():
    client = TestClient(build_fastapi_app(_EchoMCPServer()))

    with client.stream("GET", "/mcp/sse") as stream:
        lines = iter(stream.iter_lines())
        assert next(lines) == "event: endpoint"
        endpoint_line = next(lines)
        message_endpoint = endpoint_line.removeprefix("data: ")
        response = client.post(message_endpoint, json={"method": "ping"})

    assert response.status_code == 400

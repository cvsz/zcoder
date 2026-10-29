from __future__ import annotations

import json
import time
from urllib.parse import urlunsplit

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from tests.unit.codeagent.conftest import FakeLLM  # noqa: E402
from zcoder.agent.codeagent import web  # noqa: E402
from zcoder.agent.codeagent.loop import CodeAgent  # noqa: E402
from zcoder.agent.codeagent.permissions import Mode, PermissionPolicy  # noqa: E402
from zcoder.agent.codeagent.sessions import SessionStore  # noqa: E402
from zcoder.agent.codeagent.workspace import Workspace  # noqa: E402

TOKEN = "t" * 32
BASE = "http://127.0.0.1:8421"
ORIGIN = {"origin": BASE}
WS_URL = "ws://127.0.0.1:8421/api/agent/ws"


def build(tmp_path, script, *, bypass=False, **cfg_kw):
    holder: dict = {}
    store = SessionStore(tmp_path / "sess")

    def factory(ask):
        ws = Workspace(tmp_path)
        policy = PermissionPolicy(workspace=ws, allow_bypass=bypass)
        if bypass:
            policy.mode = Mode.BYPASS
        agent = CodeAgent(FakeLLM(script), ws, policy=policy, store=store, memory=[], ask=ask)
        holder["agent"] = agent
        return agent

    frontend = tmp_path / "fe"
    frontend.mkdir(exist_ok=True)
    (frontend / "index.html").write_text("<!doctype html><title>agent</title>")
    cfg = web.WebConfig(
        root=tmp_path, token=TOKEN, agent_factory=factory, store=store, frontend_dir=frontend, **cfg_kw
    )
    return web.create_app(cfg), holder


@pytest.fixture
def client(tmp_path):
    app, holder = build(tmp_path, [{"text": "hi"}])
    c = TestClient(app, base_url=BASE)
    c.holder = holder
    return c


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def connect(c, token=TOKEN):
    ws = c.websocket_connect(WS_URL, headers=ORIGIN)
    sock = ws.__enter__()
    sock.send_text(json.dumps({"type": "auth", "token": token}))
    return ws, sock


def until(sock, kind, limit=60):
    seen = []
    for _ in range(limit):
        m = sock.receive_json()
        seen.append(m)
        if m["type"] == kind:
            return m, seen
    raise AssertionError(f"never saw {kind}: {[m['type'] for m in seen]}")


def open_session(c, token=TOKEN):
    ctx, sock = connect(c, token)
    ready, _ = until(sock, "ready")
    return ctx, sock, ready


# ------------------------------------------------------------------ HTTP surface
def test_health_is_open_but_leaks_nothing(client):
    r = client.get("/api/agent/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_info_requires_the_right_bearer_token(client):
    assert client.get("/api/agent/info").status_code == 401
    assert client.get("/api/agent/info", headers=auth("wrong")).status_code == 401
    assert client.get("/api/agent/info", headers={"Authorization": TOKEN}).status_code == 401
    r = client.get("/api/agent/info", headers=auth())
    body = r.json()
    assert r.status_code == 200 and body["model"] == "fake-model" and "bypass" not in body["modes"]
    assert any(c["name"] == "compact" for c in body["commands"])


def test_token_in_query_string_is_not_accepted(client):
    assert client.get(f"/api/agent/info?token={TOKEN}").status_code == 401


def test_repeated_bad_tokens_get_throttled(client):
    codes = [client.get("/api/agent/info", headers=auth("bad")).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert client.get("/api/agent/info", headers=auth()).status_code == 429


def test_foreign_host_header_is_rejected(client):
    r = client.get("/api/agent/health", headers={"host": "evil.example.com"})
    assert r.status_code == 400
    assert client.get("/api/agent/health", headers={"host": "localhost:8421"}).status_code == 200


def test_security_headers_and_csp(client):
    r = client.get("/api/agent/health")
    h = r.headers
    assert (
        h["x-content-type-options"] == "nosniff"
        and h["x-frame-options"] == "DENY"
        and h["referrer-policy"] == "no-referrer"
    )
    assert h["cache-control"] == "no-store"
    csp = h["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "ws://127.0.0.1:8421" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_no_openapi_or_docs(client):
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_frontend_is_served_with_headers(client):
    r = client.get("/")
    assert (
        r.status_code == 200 and "<title>agent</title>" in r.text and "content-security-policy" in r.headers
    )


def test_files_and_session_endpoints(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("")
    app, holder = build(tmp_path, [{"text": "x"}])
    c = TestClient(app, base_url=BASE)
    assert c.get("/api/agent/files?q=mod", headers=auth()).json() == {"files": ["pkg/mod.py"]}
    assert c.get("/api/agent/files?q=mod").status_code == 401
    assert c.delete("/api/agent/sessions/20240101-000000-abcdef").status_code == 401
    assert c.delete("/api/agent/sessions/not-an-id", headers=auth()).status_code == 400
    assert c.delete("/api/agent/sessions/20240101-000000-abcdef", headers=auth()).status_code == 204


# ------------------------------------------------------------------ websocket security
def test_ws_rejects_foreign_origin(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_URL, headers={"origin": "http://evil.example.com"}):
            pass
    assert exc.value.code in {4403, 1006, 403}


def test_ws_rejects_bad_token_without_ready(client):
    ctx, sock = connect(client, "wrong-token-wrong-token-wrong-token")
    with pytest.raises(WebSocketDisconnect) as exc:
        sock.receive_json()
    assert exc.value.code == 4401
    ctx.__exit__(None, None, None)


def test_ws_rejects_non_auth_first_message(client):
    with client.websocket_connect(WS_URL, headers=ORIGIN) as sock:
        sock.send_text(json.dumps({"type": "prompt", "text": "hi"}))
        with pytest.raises(WebSocketDisconnect) as exc:
            sock.receive_json()
        assert exc.value.code == 4401


def test_ws_connection_cap(tmp_path):
    app, _ = build(tmp_path, [], max_connections=1)
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    try:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(WS_URL, headers=ORIGIN):
                pass
    finally:
        ctx.__exit__(None, None, None)


def test_bypass_can_never_be_enabled_from_the_browser(tmp_path):
    app, holder = build(tmp_path, [], bypass=True)
    c = TestClient(app, base_url=BASE)
    ctx, sock, ready = open_session(c)
    assert ready["mode"] == "default" and holder["agent"].policy.allow_bypass is False
    sock.send_json({"type": "mode", "mode": "bypass"})
    note, _ = until(sock, "notice")
    assert note["level"] == "error" and holder["agent"].mode == Mode.DEFAULT
    sock.send_json({"type": "mode", "mode": "cycle"})
    m, _ = until(sock, "mode")
    assert m["mode"] == "acceptEdits"
    ctx.__exit__(None, None, None)


# ------------------------------------------------------------------ websocket behaviour
def test_streamed_turn(client):
    ctx, sock, ready = open_session(client)
    assert ready["cwd"] and ready["model"] == "fake-model" and ready["mode"] == "default"
    sock.send_json({"type": "prompt", "text": "hello"})
    done, seen = until(sock, "done")
    types = [m["type"] for m in seen]
    assert types[0] == "user" and "text" in types and done["stop_reason"] == "end"
    assert "".join(m["text"] for m in seen if m["type"] == "text") == "hi"
    last = None
    for _ in range(10):
        st, _ = until(sock, "state")
        last = st
        if not st["busy"]:
            break
    assert last is not None and last["busy"] is False, "UI must leave the busy state once the turn ends"
    assert last["usage"]["completion"] == 5
    ctx.__exit__(None, None, None)


def test_approval_round_trip_allow(tmp_path):
    app, holder = build(
        tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x = 1\n"})]}, {"text": "done"}]
    )
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "make n.py"})
    perm, seen = until(sock, "permission")
    start = next(m for m in seen if m["type"] == "tool_start")
    assert start["args"]["content"] == "<6 chars>" and start["title"] == "n.py"
    assert perm["tool"] == "Write" and "+x = 1" in perm["diff"] and perm["session_rule"] == "Write"
    assert not (tmp_path / "n.py").exists()
    sock.send_json({"type": "permission", "id": perm["id"], "behavior": "allow"})
    end, _ = until(sock, "tool_end")
    assert not end["is_error"] and end["diff"] and (tmp_path / "n.py").read_text() == "x = 1\n"
    until(sock, "done")
    ctx.__exit__(None, None, None)


def test_approval_deny_with_feedback(tmp_path):
    app, _ = build(tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "go"})
    perm, _ = until(sock, "permission")
    sock.send_json(
        {"type": "permission", "id": perm["id"], "behavior": "deny", "feedback": "no files please"}
    )
    end, _ = until(sock, "tool_end")
    assert end["is_error"] and "no files please" in end["output"] and not (tmp_path / "n.py").exists()
    ctx.__exit__(None, None, None)


def test_bogus_permission_replies_are_ignored(tmp_path):
    app, _ = build(tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "permission", "id": "nope", "behavior": "allow"})
    note, _ = until(sock, "notice")
    assert "expired" in note["text"]
    sock.send_json({"type": "prompt", "text": "go"})
    perm, _ = until(sock, "permission")
    sock.send_json({"type": "permission", "id": perm["id"], "behavior": "yolo"})
    until(sock, "notice")
    assert not (tmp_path / "n.py").exists()
    sock.send_json({"type": "interrupt"})
    until(sock, "done")
    ctx.__exit__(None, None, None)


def test_interrupt_unblocks_a_pending_approval(tmp_path):
    app, _ = build(tmp_path, [{"calls": [("Bash", {"command": "mkdir boom"})]}, {"text": "never"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "go"})
    until(sock, "permission")
    sock.send_json({"type": "interrupt"})
    done, _ = until(sock, "done")
    assert done["stop_reason"] == "interrupted" and not (tmp_path / "boom").exists()
    ctx.__exit__(None, None, None)


def test_second_prompt_while_busy_is_refused(tmp_path):
    app, _ = build(tmp_path, [{"calls": [("Bash", {"command": "mkdir x"})]}, {"text": "ok"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "one"})
    until(sock, "permission")
    sock.send_json({"type": "prompt", "text": "two"})
    note, _ = until(sock, "notice")
    assert "working" in note["text"]
    sock.send_json({"type": "interrupt"})
    until(sock, "done")
    ctx.__exit__(None, None, None)


def test_limits_and_malformed_input(tmp_path):
    app, _ = build(
        tmp_path, [{"text": "a"}, {"text": "b"}, {"text": "c"}], max_prompt_chars=50, prompts_per_minute=2
    )
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_text("{not json")
    assert until(sock, "notice")[0]["text"] == "Malformed message."
    sock.send_json({"type": "prompt", "text": "x" * 51})
    assert "too long" in until(sock, "notice")[0]["text"]
    sock.send_json({"type": "prompt", "text": "   "})
    assert "Empty" in until(sock, "notice")[0]["text"]
    sock.send_json({"type": "nonsense"})
    assert "Unknown" in until(sock, "notice")[0]["text"]
    for _ in range(2):
        sock.send_json({"type": "prompt", "text": "ok"})
        until(sock, "done")
        time.sleep(0.05)
    sock.send_json({"type": "prompt", "text": "third"})
    assert "Rate limit" in until(sock, "notice")[0]["text"]
    ctx.__exit__(None, None, None)


def test_commands_over_websocket(client):
    ctx, sock, _ = open_session(client)
    sock.send_json({"type": "command", "line": "/help"})
    res, _ = until(sock, "command_result")
    assert "/compact" in res["output"] and not res["is_error"]
    sock.send_json({"type": "command", "line": "help"})
    assert "Invalid command" in until(sock, "notice")[0]["text"]
    sock.send_json({"type": "command", "line": "/exit"})
    assert "Close the browser tab" in until(sock, "notice")[0]["text"]
    ctx.__exit__(None, None, None)


def test_resume_sends_history(tmp_path):
    app, holder = build(tmp_path, [{"text": "the answer"}, {"text": "x"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "question"})
    until(sock, "done")
    sid = holder["agent"].session_id
    sock.send_json({"type": "new"})
    until(sock, "command_result")
    assert holder["agent"].messages == []
    sock.send_json({"type": "resume", "id": sid})
    hist, _ = until(sock, "history")
    assert hist["messages"] == [
        {"role": "user", "text": "question"},
        {"role": "assistant", "text": "the answer", "tools": []},
    ]
    sock.send_json({"type": "resume", "id": "../../etc/passwd"})
    res, _ = until(sock, "command_result")
    assert res["is_error"]
    ctx.__exit__(None, None, None)


def test_init_command_runs_a_turn(client):
    ctx, sock, _ = open_session(client)
    sock.send_json({"type": "command", "line": "/init"})
    user, seen = until(sock, "user")
    assert user["text"] == "/init"
    until(sock, "done")
    ctx.__exit__(None, None, None)


def test_disconnect_during_approval_fails_closed(tmp_path):
    app, holder = build(tmp_path, [{"calls": [("Write", {"path": "n.py", "content": "x"})]}, {"text": "ok"}])
    c = TestClient(app, base_url=BASE)
    ctx, sock, _ = open_session(c)
    sock.send_json({"type": "prompt", "text": "go"})
    until(sock, "permission")
    ctx.__exit__(None, None, None)
    for _ in range(40):
        if not holder["agent"].running:
            break
        time.sleep(0.05)
    assert holder["agent"].running is False and not (tmp_path / "n.py").exists()


# ------------------------------------------------------------------ units
def test_config_validation_and_origins(tmp_path):
    with pytest.raises(ValueError):
        web.WebConfig(root=tmp_path, token="short")
    extra_origin = urlunsplit(("https", "dev.example", "", "", ""))
    cfg = web.WebConfig(root=tmp_path, token=TOKEN, host="127.0.0.1", port=9000, extra_origins=(extra_origin,))
    assert cfg.allowed_origins == {
        "http://127.0.0.1:9000",
        "http://localhost:9000",
        "http://[::1]:9000",
        extra_origin,
    }
    assert "evil.com" not in cfg.allowed_hosts and "127.0.0.1" in cfg.allowed_hosts


def test_is_loopback():
    assert all(web.is_loopback(h) for h in ["127.0.0.1", "::1", "localhost", "127.5.5.5"])
    assert not any(web.is_loopback(h) for h in ["0.0.0.0", "192.168.1.5", "example.com", ""])


def test_serve_refuses_remote_bind_without_flag(tmp_path, capsys):
    assert web.serve(tmp_path, host="0.0.0.0") == 1
    assert "refusing to bind" in capsys.readouterr().err


def test_public_args_hides_bodies_and_truncates():
    out = web.public_args(
        {"path": "a", "content": "BODY" * 1000, "command": "x" * 5000, "n": 3, "todos": [{"a": 1}]}
    )
    assert out["content"] == "<4000 chars>" and out["command"].endswith("[5000 chars]") and out["n"] == 3
    assert isinstance(out["todos"], str)


def test_generated_tokens_are_long_and_unique():
    a, b = web.generate_token(), web.generate_token()
    assert a != b and len(a) >= 32


def test_history_for_client_strips_attachments():
    rows = web.history_for_client(
        [
            {"role": "user", "content": 'hi\n\n<file path="a">secret</file>'},
            {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "LS"}}]},
            {"role": "tool", "content": "x"},
        ]
    )
    assert rows == [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "", "tools": ["LS"]}]


def test_ws_rejects_foreign_host_header(client):
    """DNS-rebinding guard also covers the WebSocket upgrade."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("ws://testserver/api/agent/ws", headers=ORIGIN):
            pass
    assert exc.value.code == 1008

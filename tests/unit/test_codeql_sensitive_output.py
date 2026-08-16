from pathlib import Path


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_compliance_activity_does_not_print_sensitive_actor_fields():
    source = _source("src/zcoder/claude/enterprise/compliance.py")
    function = source.split("def _print_activity", 1)[1].split("\ndef ", 1)[0]

    assert 'actor.get("email_address")' not in function
    assert 'actor.get("unauthenticated_email_address")' not in function
    assert 'actor.get("api_key_id")' not in function
    assert 'actor.get("admin_api_key_id")' not in function
    assert 'actor.get("type", "?")' in function


def test_admin_usage_report_does_not_print_sensitive_actor_fields():
    source = _source("src/zcoder/claude/enterprise/admin_api.py")
    function = source.split("def cmd_claude_code_usage_report", 1)[1].split("\ndef ", 1)[0]

    assert 'actor.get("email_address")' not in function
    assert 'actor.get("api_key_name")' not in function
    assert 'actor.get("type")' in function


def test_streaming_error_response_does_not_expose_exception_text():
    source = _source("webapp/backend/server.py")
    function = source.split("def event_stream", 1)[1].split("return StreamingResponse", 1)[0]

    assert "'message': str(e)" not in function
    assert '"message": str(e)' not in function
    assert "Upstream provider request failed" in function
    assert 'logger.exception("stream_chat_failed"' in function

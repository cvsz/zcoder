from pathlib import Path


def test_streaming_error_response_does_not_expose_exception_text():
    source = Path("webapp/backend/server.py").read_text(encoding="utf-8")

    assert "'message': str(e)" not in source
    assert '"message": str(e)' not in source
    assert "Upstream provider request failed" in source
    assert 'logger.exception("stream_chat_failed"' in source

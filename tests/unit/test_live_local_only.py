from unittest.mock import Mock

from zcoder.agent.orchestration.live import LiveSession


def test_live_session_uses_local_coder_and_conversation_history(monkeypatch, capsys):
    client = Mock()
    client.generate.return_value = "local response"
    constructor = Mock(return_value=client)
    monkeypatch.setattr("zcoder.agent.orchestration.live.Coder", constructor)
    monkeypatch.delenv("ZCODER_LOCAL_MODE", raising=False)

    session = LiveSession(api_key="must-not-be-used", model="local-model", temperature=0.4)
    first = session.send("first turn")
    second = session.send("second turn")

    assert first == second == "local response"
    constructor.assert_called_once_with(model="local-model", temperature=0.4, max_tokens=4096)
    assert client.generate.call_args_list[0].args == ("first turn",)
    assert client.generate.call_args_list[0].kwargs["history"] == []
    assert client.generate.call_args_list[1].args == ("second turn",)
    assert client.generate.call_args_list[1].kwargs["history"] == [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "local response"},
    ]
    assert capsys.readouterr().out == "local responselocal response"


def test_live_session_never_uses_placeholder_response(monkeypatch, capsys):
    client = Mock()
    client.generate.return_value = "model generated answer"
    monkeypatch.setattr("zcoder.agent.orchestration.live.Coder", lambda **_: client)
    monkeypatch.setenv("ZCODER_LOCAL_MODE", "1")

    result = LiveSession(api_key="", model="local-model").send("question")

    assert result == "model generated answer"
    client.generate.assert_called_once()
    assert "You said" not in capsys.readouterr().out

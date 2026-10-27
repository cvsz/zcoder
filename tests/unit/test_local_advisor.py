from unittest.mock import Mock

import pytest

from zcoder.agent.capabilities.advisor import AdvisorCoder, build_advisor_tool


def test_advisor_runs_two_local_generation_passes_without_credentials(monkeypatch):
    advisor = Mock()
    advisor.generate.return_value = "Check permissions and preserve the public interface."
    executor = Mock()
    executor.generate.return_value = "Completed with those constraints."
    constructor = Mock(side_effect=[executor, advisor])
    monkeypatch.setattr("zcoder.agent.capabilities.advisor.Coder", constructor)

    client = AdvisorCoder(api_key="must-not-be-used", executor_model="local-qwen", max_tokens=512)
    tool = build_advisor_tool(advisor_model="local-qwen", max_tokens=128)
    result = client.run("Refactor this module", tool, system="Be concise.", verbose=False)

    assert result == "Completed with those constraints."
    assert constructor.call_args_list[0].kwargs == {"model": "local-qwen", "max_tokens": 512}
    assert constructor.call_args_list[1].kwargs == {"model": "local-qwen", "max_tokens": 128}
    assert "api_key" not in constructor.call_args.kwargs
    advisor_prompt = advisor.generate.call_args.args[0]
    assert "Refactor this module" in advisor_prompt
    assert executor.generate.call_args.args[0].startswith("Task:\nRefactor this module")
    assert "Check permissions" in executor.generate.call_args.args[0]
    assert executor.generate.call_args.kwargs["system"] == "Be concise."


def test_advisor_error_prevents_executor_pass(monkeypatch):
    advisor = Mock()
    advisor.generate.return_value = "[ERROR] local service unavailable"
    executor = Mock()
    monkeypatch.setattr("zcoder.agent.capabilities.advisor.Coder", Mock(side_effect=[executor, advisor]))
    client = AdvisorCoder(executor_model="local-qwen")

    result = client.run("Review task", build_advisor_tool(), verbose=False)

    assert result == "[ERROR] local service unavailable"
    executor.generate.assert_not_called()


def test_local_advisor_rejects_provider_tool_payloads(monkeypatch):
    executor = Mock()
    monkeypatch.setattr("zcoder.agent.capabilities.advisor.Coder", Mock(return_value=executor))
    client = AdvisorCoder(executor_model="local-qwen")

    with pytest.raises(ValueError, match="does not support extra provider tools"):
        client.run("Review task", build_advisor_tool(), extra_tools=[{"name": "remote"}])

    executor.generate.assert_not_called()


@pytest.mark.parametrize("kwargs", [{"max_uses": 0}, {"max_tokens": 0}])
def test_advisor_limits_must_be_positive(kwargs):
    with pytest.raises(ValueError):
        build_advisor_tool(**kwargs)

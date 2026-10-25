"""Local model wiring for integrations that summarize repository data."""

from unittest.mock import Mock

from zcoder.agent.eval.evals import EvalCase as SuiteCase
from zcoder.agent.eval.evals import run_case
from zcoder.agent.integrations import git, github
from zcoder.agent.optimization import prompt
from zcoder.agent.rag.engine import Chunk
from zcoder.agent.rag.engine import generate as rag_generate
from zcoder.core.health import _check_model_config, run_health_check


def test_git_generation_uses_local_coder(monkeypatch):
    coder = Mock()
    coder.generate.return_value = "feat: local result"
    constructor = Mock(return_value=coder)
    monkeypatch.setattr("zcoder.services.coder.Coder", constructor)

    result = git._call("ignored-key", "zqwen-model", "Write a commit message", max_tokens=256)

    assert result == "feat: local result"
    constructor.assert_called_once_with(
        api_key="ignored-key", model="zqwen-model", temperature=0.3, max_tokens=256
    )
    coder.generate.assert_called_once_with("Write a commit message", system=git.SYS)


def test_github_generation_uses_local_coder_contract():
    client = Mock()
    client.generate.return_value = "review result"

    result = github._call(client, "zqwen-model", "system prompt", "review this", max_tokens=512)

    assert result == "review result"
    assert client.model == "zqwen-model"
    assert client.max_tokens == 512
    client.generate.assert_called_once_with("review this", system="system prompt")


def test_prompt_optimization_uses_local_generation_client():
    client = Mock()
    client.generate.return_value = "improved prompt"

    result = prompt.optimize("write code", client, "zqwen-model")

    assert result == "improved prompt"
    assert client.model == "zqwen-model"
    assert client.max_tokens == 2048
    client.generate.assert_called_once()


def test_rag_generation_uses_local_coder(monkeypatch):
    coder = Mock()
    coder.generate.return_value = "grounded answer"
    constructor = Mock(return_value=coder)
    monkeypatch.setattr("zcoder.services.coder.Coder", constructor)

    result = rag_generate("question", [Chunk("c1", "notes.md", "answer")])

    assert result == "grounded answer"
    constructor.assert_called_once_with(
        model="zqwen2.5-coder-7b-instruct-q4_k_m", max_tokens=2048, temperature=0.2
    )
    coder.generate.assert_called_once()


def test_evaluation_case_uses_local_generation_client():
    client = Mock()
    client.generate.return_value = "expected phrase"
    case = SuiteCase(id="local", prompt="test", expected_contains=["expected"])

    result = run_case(case, client, "zqwen-model")

    assert result.passed
    assert result.response == "expected phrase"
    assert client.model == "zqwen-model"


def test_health_check_does_not_require_provider_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    report = run_health_check()
    model_check = next(check for check in report.checks if check.name == "local_model_configured")
    assert model_check.ok


def test_health_check_rejects_non_loopback_model_url(monkeypatch):
    monkeypatch.setenv("ZCODER_BASE_URL", "https://models.example.com/v1")
    check = _check_model_config()
    assert not check.ok
    assert check.name == "local_model_configured"

from types import SimpleNamespace

from zcoder.agent.ausi.skills import BaseSkill, SkillInput


class _OutputSkill(BaseSkill):
    @property
    def purpose(self) -> str:
        return "test result conversion"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        return True, []

    def execute(self, inputs: SkillInput):
        return self.get_output("unused")


def test_get_output_preserves_failed_adapter_result():
    result = SimpleNamespace(
        success=False,
        text="partial response",
        model="local-model",
        task_id="task-123",
        metadata={"provider": "ollama"},
        error="provider unavailable",
    )

    output = _OutputSkill("test").get_output(result)

    assert output.success is False
    assert output.result_text == "partial response"
    assert output.model_used == "local-model"
    assert output.task_id == "task-123"
    assert output.metadata == {"provider": "ollama"}
    assert output.error == "provider unavailable"

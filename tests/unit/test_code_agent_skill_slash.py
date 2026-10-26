from zcoder.agent.capabilities.code import cmd_code_slash


def test_skill_info_slash_command_is_reachable(tmp_path, monkeypatch, capsys):
    skill_path = tmp_path / ".claude" / "skills" / "demo" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("---\nname: demo\ndescription: Demo skill\n---\n# Demo\n")
    monkeypatch.chdir(tmp_path)

    cmd_code_slash("skill", api_key="", model="local-qwen", prompt="info demo")

    output = capsys.readouterr().out
    assert "Name: demo" in output
    assert "Source: custom" in output
    assert str(skill_path.resolve()) in output

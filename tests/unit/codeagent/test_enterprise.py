from zcoder.agent.codeagent.audit import redact


def test_redaction_masks_credentials():
    assert "hunter2" not in redact("deploy --password=hunter2")
    assert redact("Authorization: Bearer test-token-123") == "Authorization: Bearer ***"
    assert "s3cr3t" not in redact("git clone https://user:s3cr3t@host/repo.git")
    assert "API_TOKEN=***" in redact("API_TOKEN=abc123 run")
    assert redact("ls -la") == "ls -la"

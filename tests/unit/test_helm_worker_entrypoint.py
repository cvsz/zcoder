"""Helm manifest regression coverage for the packaged worker entrypoint."""

from pathlib import Path


def test_worker_overrides_image_entrypoint_with_packaged_module():
    template = Path("deploy/helm/zcoder/templates/deployment.yaml").read_text()

    assert 'command: ["python", "-m", "zcoder.worker.process"]' in template
    assert 'args: ["--pool-type", "standard"]' in template
    assert 'args: ["python", "worker_process.py"' not in template

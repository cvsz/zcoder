"""Shared fixtures for in-package tests (src/zcoder/tests)."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """ทุก test ใช้ไฟล์ config และ legacy path ชั่วคราว ห้ามอ่าน/เขียน ~/.zcoder-config.json จริง
    และไม่ให้ ZCODER_* จาก shell ของผู้พัฒนามีผลต่อค่า default ที่ทดสอบ"""
    fake_config = tmp_path / ".zcoder-config.json"
    monkeypatch.setattr("zcoder.config.settings.CONFIG_PATH", str(fake_config))
    monkeypatch.setattr("zcoder.config.settings.LEGACY_CONFIG_PATH", str(tmp_path / ".ai-coder-config.json"))
    for name in [n for n in os.environ if n.startswith("ZCODER_")]:
        monkeypatch.delenv(name)
    yield fake_config

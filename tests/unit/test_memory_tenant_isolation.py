"""Regression tests for Slice E.12 — SEC-007 tenant isolation in memory."""

from pathlib import Path

from zcoder.claude.capabilities.code import MemoryLayer, MemoryManager, MemoryScope


def test_memory_layer_carries_tenant_id():
    layer = MemoryLayer(scope=MemoryScope.PROJECT, path=Path("/tmp/x"), content="hello", tenant_id="tenant-1")
    assert layer.tenant_id == "tenant-1"


def test_memory_layer_default_tenant_empty():
    layer = MemoryLayer(scope=MemoryScope.PROJECT, path=Path("/tmp/x"), content="hello")
    assert layer.tenant_id == ""


def test_memory_manager_populates_tenant_id(tmp_path):
    enterprise = tmp_path / "enterprise"
    enterprise.mkdir()
    (enterprise / "CLAUDE.md").write_text("# ENTERPRISE\n")
    user = tmp_path / "user.md"
    user.write_text("# USER\n")
    proj = tmp_path / ".claude" / "CLAUDE.md"
    proj.parent.mkdir(parents=True)
    proj.write_text("# PROJECT\n")

    mm = MemoryManager(
        str(tmp_path), enterprise_dir=str(enterprise), user_memory_path=str(user), tenant_id="t1"
    )
    layers = mm.discover()
    assert all(layer.tenant_id == "t1" for layer in layers)
    assert len(layers) == 3


def test_combined_tag_includes_tenant_when_set(tmp_path):
    enterprise = tmp_path / "enterprise"
    enterprise.mkdir()
    (enterprise / "CLAUDE.md").write_text("# ENTERPRISE\n")
    mm = MemoryManager(str(tmp_path), enterprise_dir=str(enterprise), tenant_id="tenant-1")
    out = mm.combined()
    assert 'tenant="tenant-1"' in out
    assert "<loaded_memory" in out


def test_combined_tag_omits_tenant_when_empty(tmp_path):
    enterprise = tmp_path / "enterprise"
    enterprise.mkdir()
    (enterprise / "CLAUDE.md").write_text("# ENTERPRISE\n")
    mm = MemoryManager(str(tmp_path), enterprise_dir=str(enterprise))
    out = mm.combined()
    assert "tenant=" not in out
    assert "<loaded_memory" in out


def test_tenant_isolation_prevents_cross_tenant_leak(tmp_path):
    tenant_a = tmp_path / "tenant_a"
    tenant_a.mkdir()
    proj_a = tenant_a / ".claude" / "CLAUDE.md"
    proj_a.parent.mkdir(parents=True)
    proj_a.write_text("# TENANT_A_SECRET\n")

    tenant_b = tmp_path / "tenant_b"
    tenant_b.mkdir()
    proj_b = tenant_b / ".claude" / "CLAUDE.md"
    proj_b.parent.mkdir(parents=True)
    proj_b.write_text("# TENANT_B_SECRET\n")

    mm_a = MemoryManager(str(tenant_a), tenant_id="a")
    out_a = mm_a.combined()
    assert "TENANT_A_SECRET" in out_a
    assert "TENANT_B_SECRET" not in out_a

    mm_b = MemoryManager(str(tenant_b), tenant_id="b")
    out_b = mm_b.combined()
    assert "TENANT_B_SECRET" in out_b
    assert "TENANT_A_SECRET" not in out_b

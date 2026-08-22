"""Regression tests for SEC-007.1 — RAG index tenant isolation.

The CLI RAG index store was name-keyed with no tenant boundary; indexes now
require an explicit tenant, are namespaced on disk per tenant, verify stored
identity on load, and fail closed rather than falling back to a shared
namespace.
"""

from __future__ import annotations

import json

import pytest

from zcoder.claude.rag import engine


@pytest.fixture
def rag_dir(tmp_path, monkeypatch):
    d = tmp_path / "rag_indexes"
    monkeypatch.setattr(engine, "INDEX_DIR", d)
    return d


@pytest.fixture
def corpus(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("alpha beta gamma " * 20)
    return str(folder)


def test_build_index_requires_tenant(corpus):
    with pytest.raises(ValueError, match="tenant_id is required"):
        engine.build_index("idx", corpus)


def test_load_index_requires_tenant():
    with pytest.raises(ValueError, match="tenant_id is required"):
        engine.load_index("idx")


def test_save_index_requires_tenant(rag_dir):
    idx = engine.RAGIndex(name="orphan")
    with pytest.raises(ValueError, match="tenant_id is required"):
        engine._save_index(idx)


def test_roundtrip_namespaced_per_tenant(rag_dir, corpus):
    idx = engine.build_index("idx", corpus, tenant_id="tenant-a")
    assert idx.tenant_id == "tenant-a"
    # storage file carries the tenant namespace prefix
    assert (rag_dir / "tenant-a__idx.json").exists()

    loaded = engine.load_index("idx", tenant_id="tenant-a")
    assert loaded is not None
    assert loaded.tenant_id == "tenant-a"
    assert len(loaded.chunks) == len(idx.chunks)


def test_cross_tenant_load_misses(rag_dir, corpus):
    engine.build_index("secret-docs", corpus, tenant_id="tenant-a")
    assert engine.load_index("secret-docs", tenant_id="tenant-b") is None


def test_tampered_tenant_metadata_fails_closed(rag_dir, corpus):
    engine.build_index("idx", corpus, tenant_id="tenant-a")
    p = rag_dir / "tenant-b__idx.json"
    data = json.loads((rag_dir / "tenant-a__idx.json").read_text())
    data["name"] = "idx"  # copied into the wrong namespace on disk
    p.write_text(json.dumps(data))
    # stored identity (tenant-a) does not match requested namespace (tenant-b)
    assert engine.load_index("idx", tenant_id="tenant-b") is None


def test_legacy_unnamespaced_index_not_loaded(rag_dir, corpus):
    rag_dir.mkdir()
    legacy = {"name": "old", "chunks": [], "idf": {}, "file_ids": {}}
    (rag_dir / "old.json").write_text(json.dumps(legacy))
    assert engine.load_index("old", tenant_id="anyone") is None  # invisible: no boundary
    # and still listed for operators so it can be rebuilt
    listed = _capture_list()
    assert any("[no tenant" in ln for ln in listed)


def _capture_list(capsys=None):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        engine.cmd_rag_list()
    return buf.getvalue().splitlines()


def test_traversal_in_name_or_tenant_rejected(rag_dir, corpus):
    from zcoder.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        engine.build_index("../evil", corpus, tenant_id="t")
    with pytest.raises(ValidationError):
        engine._index_path("ok-name", "../../etc")


def test_cmd_rag_query_fails_closed_without_tenant(rag_dir, corpus, capsys):
    engine.build_index("idx", corpus, tenant_id="t")
    with pytest.raises(SystemExit):
        engine.cmd_rag_query("idx", "alpha", api_key="k", model="m")


def test_rag_engine_stays_out_of_server_import_graphs():
    """Guardrail: rag.engine is CLI-local (per-user $HOME store). If it is
    ever imported by an api/services/worker package, its tenant model must
    be re-reviewed as a multi-tenant surface first."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys\n"
                "bad = []\n"
                "for root in ('src/zcoder/api', 'src/zcoder/services', 'src/zcoder/worker'):\n"
                "    for p in pathlib.Path(root).rglob('*.py'):\n"
                "        if 'rag.engine' in p.read_text(errors='replace'):\n"
                "            bad.append(str(p))\n"
                "print('\\n'.join(bad))\n"
                "sys.exit(1 if bad else 0)\n"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"rag.engine imported by server packages:\n{result.stdout}"

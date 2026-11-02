"""Security and contract tests for the explicit local GGUF file inventory."""

from __future__ import annotations

import struct

import pytest

from zgpu.integrations.local_model_catalog import LocalModelCatalog
from zgpu.llm.loaders.gguf import GGUFLoader


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _write_gguf(path, *, architecture: str = "gemma", name: str = "Gemma local test"):
    entries = [
        ("general.architecture", 8, _string(architecture)),
        ("general.name", 8, _string(name)),
        ("general.file_type", 4, struct.pack("<I", 15)),
        ("general.parameter_count", 10, struct.pack("<Q", 2_000_000_000)),
        ("general.quantization_version", 4, struct.pack("<I", 2)),
        ("tokenizer.ggml.model", 8, _string("gpt2")),
        (f"{architecture}.context_length", 4, struct.pack("<I", 32768)),
        (f"{architecture}.block_count", 4, struct.pack("<I", 28)),
    ]
    content = bytearray(struct.pack("<IIQQ", GGUFLoader.GGUF_MAGIC, 3, 0, len(entries)))
    for key, value_type, value in entries:
        content.extend(_string(key))
        content.extend(struct.pack("<I", value_type))
        content.extend(value)
    path.write_bytes(content)


def test_local_model_catalog_lists_metadata_without_exposing_directory(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    model = root / "gemma-2b-q4.gguf"
    _write_gguf(model)
    (root / "not-a-model.gguf").write_bytes(b"invalid GGUF" * 3)
    (root / "notes.txt").write_text("private", encoding="utf-8")

    result = LocalModelCatalog([root]).list_models()
    assert result["scanned"] == 2
    assert result["errors"] == 1
    assert result["truncated"] is False
    assert result["data"] == [
        {
            "id": result["data"][0]["id"],
            "name": "Gemma local test",
            "filename": "gemma-2b-q4.gguf",
            "architecture": "gemma",
            "file_type": 15,
            "quantization": "Q4_K_M",
            "parameter_count": 2_000_000_000,
            "context_length": 32768,
            "block_count": 28,
            "quantization_version": 2,
            "tokenizer_model": "gpt2",
            "size_bytes": model.stat().st_size,
            "state": "metadata_only",
        }
    ]
    assert str(root) not in str(result)


def test_local_model_catalog_distinguishes_configured_runtime_model(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    model = root / "selected.gguf"
    _write_gguf(model)

    result = LocalModelCatalog([root]).list_models(
        runtime_model_path=model, runtime_model_id="zgpu-local-test"
    )
    assert result["data"][0]["state"] == "configured_runtime_model"
    assert result["runtime"] == {
        "provider": "llama.cpp",
        "model_id": "zgpu-local-test",
        "configured_model_in_inventory": True,
    }

    unconfigured = LocalModelCatalog([root]).list_models()
    assert unconfigured["data"][0]["state"] == "metadata_only"
    assert unconfigured["runtime"] is None


def test_local_model_catalog_requires_explicit_real_directories(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="unavailable"):
        LocalModelCatalog([missing])

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        LocalModelCatalog([link])

    with pytest.raises(ValueError, match="at most"):
        LocalModelCatalog([real] * (LocalModelCatalog.MAX_ROOTS + 1))


def test_local_model_catalog_environment_uses_only_configured_directories(tmp_path, monkeypatch):
    root = tmp_path / "configured"
    root.mkdir()
    _write_gguf(root / "local.gguf", architecture="qwen2", name="Qwen local")
    monkeypatch.setenv("ZGPU_MODEL_DIRS", str(root))
    catalog = LocalModelCatalog.from_environment()
    result = catalog.list_models()
    assert len(result["data"]) == 1
    assert result["data"][0]["architecture"] == "qwen2"

    monkeypatch.delenv("ZGPU_MODEL_DIRS")
    assert LocalModelCatalog.from_environment().list_models() == {
        "data": [],
        "scanned": 0,
        "errors": 0,
        "truncated": False,
        "runtime": None,
    }


def test_local_model_catalog_bounds_directory_enumeration(tmp_path, monkeypatch):
    root = tmp_path / "many-files"
    root.mkdir()
    for filename in ("a.txt", "b.txt", "c.txt"):
        (root / filename).write_text("not a model", encoding="utf-8")
    monkeypatch.setattr(LocalModelCatalog, "MAX_DIRECTORY_ENTRIES", 2)

    result = LocalModelCatalog([root]).list_models()
    assert result == {"data": [], "scanned": 0, "errors": 0, "truncated": True, "runtime": None}

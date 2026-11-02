"""Bounded inventory for GGUF files in explicitly configured local directories."""

from __future__ import annotations

import hashlib
import itertools
import os
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from zgpu.llm.loaders.gguf import GGUFLoader


class LocalModelCatalogError(ValueError):
    """A bounded model inventory or integrity-manifest operation failed."""

    def __init__(self, message: str, status: int = 400):
        self.status = status
        super().__init__(message)


class LocalModelCatalog:
    """Inspect GGUF metadata without loading model tensor data or starting runtimes."""

    MAX_ROOTS = 8
    MAX_MODELS = 100
    MAX_DIRECTORY_ENTRIES = 10_000
    MAX_MANIFEST_BYTES = 8 * 1024**3
    HASH_BLOCK_BYTES = 8 * 1024**2
    _METADATA_KEYS: ClassVar[set[str]] = {
        "general.architecture",
        "general.name",
        "general.file_type",
        "general.parameter_count",
        "general.quantization_version",
        "tokenizer.ggml.model",
    }
    _FILE_TYPE_NAMES: ClassVar[dict[int, str]] = {
        0: "F32",
        1: "F16",
        2: "Q4_0",
        3: "Q4_1",
        4: "Q4_1_SOME_F16",
        7: "Q8_0",
        8: "Q5_0",
        9: "Q5_1",
        10: "Q2_K",
        11: "Q3_K_S",
        12: "Q3_K_M",
        13: "Q3_K_L",
        14: "Q4_K_S",
        15: "Q4_K_M",
        16: "Q5_K_S",
        17: "Q5_K_M",
        18: "Q6_K",
    }

    def __init__(self, roots: list[Path] | tuple[Path, ...] = ()):
        if len(roots) > self.MAX_ROOTS:
            raise ValueError(f"at most {self.MAX_ROOTS} local model directories may be configured")
        normalized = []
        for root in roots:
            candidate = Path(root).expanduser()
            if candidate.is_symlink():
                raise ValueError("configured local model directories must not be symbolic links")
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise ValueError("a configured local model directory is unavailable") from exc
            if not resolved.is_dir():
                raise ValueError("configured local model paths must be directories")
            if resolved not in normalized:
                normalized.append(resolved)
        self.roots = tuple(normalized)
        self._manifest_lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> LocalModelCatalog:
        configured = os.environ.get("ZGPU_MODEL_DIRS", "").strip()
        roots = [Path(value) for value in configured.split(os.pathsep) if value.strip()]
        return cls(roots)

    def list_models(
        self,
        *,
        runtime_model_path: Path | None = None,
        runtime_model_id: str | None = None,
    ) -> dict[str, Any]:
        models = []
        errors = 0
        scanned = 0
        truncated = False
        configured_model_seen = False
        configured_path = Path(runtime_model_path).resolve() if runtime_model_path is not None else None
        for root_index, root in enumerate(self.roots):
            try:
                entries = list(itertools.islice(root.iterdir(), self.MAX_DIRECTORY_ENTRIES + 1))
            except OSError:
                errors += 1
                continue
            if len(entries) > self.MAX_DIRECTORY_ENTRIES:
                entries = entries[: self.MAX_DIRECTORY_ENTRIES]
                truncated = True
            entries.sort(key=lambda item: item.name.casefold())
            for path in entries:
                if path.suffix.casefold() != ".gguf" or path.name.startswith(".") or path.is_symlink():
                    continue
                try:
                    stat_result = path.stat(follow_symlinks=False)
                    if not stat.S_ISREG(stat_result.st_mode):
                        continue
                    if stat_result.st_size < 24:
                        errors += 1
                        continue
                except OSError:
                    errors += 1
                    continue
                scanned += 1
                if scanned > self.MAX_MODELS:
                    truncated = True
                    scanned -= 1
                    break
                try:
                    metadata = GGUFLoader(str(path)).read_metadata(
                        keys=self._METADATA_KEYS,
                        key_suffixes={"context_length", "block_count"},
                    )
                    architecture = metadata.get("general.architecture")
                    if not isinstance(architecture, str) or not architecture:
                        errors += 1
                        continue
                    is_configured_runtime_model = (
                        configured_path is not None and path.resolve() == configured_path
                    )
                    configured_model_seen = configured_model_seen or is_configured_runtime_model
                    name = metadata.get("general.name")
                    file_type = metadata.get("general.file_type")
                    parameter_count = metadata.get("general.parameter_count")
                    context_length = metadata.get(f"{architecture}.context_length")
                    block_count = metadata.get(f"{architecture}.block_count")
                    quantization_version = metadata.get("general.quantization_version")
                    tokenizer_model = metadata.get("tokenizer.ggml.model")
                    fingerprint = self._fingerprint(root_index, path.name)
                    models.append(
                        {
                            "id": f"zgpu-local-{fingerprint}",
                            "name": name[:200] if isinstance(name, str) and name else path.stem[:200],
                            "filename": path.name[:255],
                            "architecture": architecture[:80],
                            "file_type": (
                                file_type
                                if isinstance(file_type, int) and not isinstance(file_type, bool)
                                else None
                            ),
                            "quantization": (
                                self._FILE_TYPE_NAMES.get(file_type, f"Unknown ({file_type})")
                                if isinstance(file_type, int) and not isinstance(file_type, bool)
                                else "Unknown"
                            ),
                            "parameter_count": (
                                parameter_count
                                if isinstance(parameter_count, int)
                                and not isinstance(parameter_count, bool)
                                and parameter_count >= 0
                                else None
                            ),
                            "context_length": (
                                context_length
                                if isinstance(context_length, int)
                                and not isinstance(context_length, bool)
                                and 0 < context_length <= 10_000_000
                                else None
                            ),
                            "block_count": (
                                block_count
                                if isinstance(block_count, int)
                                and not isinstance(block_count, bool)
                                and 0 < block_count <= 100_000
                                else None
                            ),
                            "quantization_version": (
                                quantization_version
                                if isinstance(quantization_version, int)
                                and not isinstance(quantization_version, bool)
                                and quantization_version >= 0
                                else None
                            ),
                            "tokenizer_model": (
                                tokenizer_model[:80]
                                if isinstance(tokenizer_model, str) and tokenizer_model
                                else None
                            ),
                            "size_bytes": stat_result.st_size,
                            "state": (
                                "configured_runtime_model" if is_configured_runtime_model else "metadata_only"
                            ),
                        }
                    )
                except (OSError, ValueError, UnicodeError):
                    errors += 1
        runtime = None
        if runtime_model_id:
            runtime = {
                "provider": "llama.cpp",
                "model_id": runtime_model_id[:128],
                "configured_model_in_inventory": configured_model_seen,
            }
        return {
            "data": models,
            "scanned": scanned,
            "errors": errors,
            "truncated": truncated,
            "runtime": runtime,
        }

    def create_integrity_manifest(self) -> dict[str, Any]:
        """Hash listed model files on explicit request, without returning local paths."""
        if not self._manifest_lock.acquire(blocking=False):
            raise LocalModelCatalogError("a local model manifest is already being generated", status=409)
        try:
            inventory = self.list_models()
            models = inventory["data"]
            total_bytes = sum(model["size_bytes"] for model in models)
            if total_bytes > self.MAX_MANIFEST_BYTES:
                raise LocalModelCatalogError(
                    "model files exceed the 8 GiB per-manifest read limit", status=413
                )

            files = []
            for model in models:
                path = self._find_model_path(model["id"], model["filename"])
                digest, size = self._hash_file(path, model["size_bytes"])
                files.append(
                    {
                        "id": model["id"],
                        "filename": model["filename"],
                        "size_bytes": size,
                        "sha256": digest,
                    }
                )
            return {
                "schema": "zgpu.local-model-manifest.v1",
                "generated_at": datetime.now(UTC).isoformat(),
                "complete": not inventory["truncated"] and inventory["errors"] == 0,
                "scanned": inventory["scanned"],
                "errors": inventory["errors"],
                "truncated": inventory["truncated"],
                "files": files,
            }
        finally:
            self._manifest_lock.release()

    @staticmethod
    def _fingerprint(root_index: int, filename: str) -> str:
        return hashlib.sha256(f"{root_index}\0{filename}".encode()).hexdigest()[:20]

    def _find_model_path(self, model_id: str, filename: str) -> Path:
        for root_index, root in enumerate(self.roots):
            if f"zgpu-local-{self._fingerprint(root_index, filename)}" != model_id:
                continue
            path = root / filename
            try:
                info = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise LocalModelCatalogError(
                    "a listed model file is no longer available", status=409
                ) from exc
            if path.is_symlink() or not stat.S_ISREG(info.st_mode):
                raise LocalModelCatalogError(
                    "a listed model file changed type during manifest generation", status=409
                )
            return path
        raise LocalModelCatalogError("a listed model file could not be resolved", status=409)

    @classmethod
    def _hash_file(cls, path: Path, expected_size: int) -> tuple[str, int]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
                    raise LocalModelCatalogError(
                        "a listed model file changed before it could be hashed", status=409
                    )
                digest = hashlib.sha256()
                size = 0
                while block := stream.read(cls.HASH_BLOCK_BYTES):
                    digest.update(block)
                    size += len(block)
                after = os.fstat(stream.fileno())
                identity_before = (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                identity_after = (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
                if identity_before != identity_after or size != expected_size:
                    raise LocalModelCatalogError("a model file changed while it was being hashed", status=409)
                return digest.hexdigest(), size
        except OSError as exc:
            raise LocalModelCatalogError("a model file could not be hashed safely", status=409) from exc

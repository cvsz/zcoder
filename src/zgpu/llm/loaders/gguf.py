"""GGUF header parsing and basic tensor block dequantization helpers."""

from __future__ import annotations

import os
import stat
import struct
from pathlib import Path
from typing import Any, ClassVar


class GGUFLoader:
    """Parser and weight loader for GGUF model files."""

    GGUF_MAGIC = 0x46554747  # "GGUF"
    MAX_METADATA_ENTRIES = 100_000
    MAX_METADATA_STRING_BYTES = 16 * 1024 * 1024
    MAX_METADATA_ARRAY_ITEMS = 1_000_000
    MAX_TOTAL_METADATA_ARRAY_ITEMS = 2_000_000
    MAX_METADATA_TABLE_BYTES = 256 * 1024 * 1024
    _SCALAR_FORMATS: ClassVar[dict[int, str]] = {
        0: "<B",  # UINT8
        1: "<b",  # INT8
        2: "<H",  # UINT16
        3: "<h",  # INT16
        4: "<I",  # UINT32
        5: "<i",  # INT32
        6: "<f",  # FLOAT32
        7: "<B",  # BOOL (validated below)
        10: "<Q",  # UINT64
        11: "<q",  # INT64
        12: "<d",  # FLOAT64
    }
    _NUMERIC_METADATA_TYPES: ClassVar[set[int]] = {0, 1, 2, 3, 4, 5, 6, 10, 11, 12}

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.header: dict[str, Any] = {}
        self.tensors: dict[str, dict[str, Any]] = {}
        self.metadata: dict[str, Any] = {}
        self._metadata_array_items_remaining = self.MAX_TOTAL_METADATA_ARRAY_ITEMS

    def parse_header(self, raw_bytes: bytes) -> dict[str, Any]:
        """Parse GGUF magic, version, tensor count, and kv count."""
        if not isinstance(raw_bytes, bytes) or len(raw_bytes) < 24:
            raise ValueError("Invalid GGUF file: file too short")
        magic, version, tensor_count, kv_count = struct.unpack_from("<IIQQ", raw_bytes, 0)
        if magic != self.GGUF_MAGIC:
            raise ValueError(f"Invalid GGUF magic: 0x{magic:08x} (expected 0x46554747)")
        if version not in {1, 2, 3}:
            raise ValueError(f"Unsupported GGUF version: {version}")
        self.header = {
            "version": version,
            "tensor_count": tensor_count,
            "kv_count": kv_count,
        }
        return self.header

    def read_metadata(
        self,
        keys: set[str] | None = None,
        *,
        key_suffixes: set[str] | None = None,
    ) -> dict[str, Any]:
        """Read bounded GGUF key/value metadata without loading tensor weights.

        GGUF models can be several gigabytes, so inspection deliberately stops
        after the metadata table and never reads tensor payloads. ``keys`` may
        limit the returned values while all entries are still structurally
        validated.
        """
        path = Path(self.filepath)
        try:
            if path.is_symlink():
                raise ValueError("GGUF metadata file must not be a symbolic link")
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                file_info = os.fstat(stream.fileno())
                if not stat.S_ISREG(file_info.st_mode):
                    raise ValueError("GGUF metadata file must be a regular file")
                file_size = file_info.st_size
                header = stream.read(24)
                self.parse_header(header)
                if self.header["kv_count"] > self.MAX_METADATA_ENTRIES:
                    raise ValueError("GGUF metadata entry count exceeds supported limits")
                self.metadata = {}
                self._metadata_array_items_remaining = self.MAX_TOTAL_METADATA_ARRAY_ITEMS
                seen_keys = set()
                for _ in range(self.header["kv_count"]):
                    self._check_metadata_budget(stream)
                    key = self._read_string(stream, file_size)
                    self._check_metadata_budget(stream)
                    if not key or key in seen_keys:
                        raise ValueError("GGUF metadata keys must be non-empty and unique")
                    seen_keys.add(key)
                    value_type = self._read_u32(stream, file_size)
                    keep = (
                        keys is None
                        or key in keys
                        or (
                            key_suffixes is not None
                            and key.rsplit(".", 1)[-1] in key_suffixes
                            and value_type in self._NUMERIC_METADATA_TYPES
                        )
                    )
                    value = self._read_value(stream, file_size, value_type, keep=keep, depth=0)
                    if keep:
                        self.metadata[key] = value
                return dict(self.metadata)
        except OSError as exc:
            raise ValueError("Unable to read GGUF metadata file") from exc

    def _read_value(self, stream, file_size: int, value_type: int, *, keep: bool, depth: int):
        if depth > 8:
            raise ValueError("GGUF metadata array nesting exceeds supported limits")
        if value_type == 8:  # STRING
            value = self._read_string(stream, file_size)
            self._check_metadata_budget(stream)
            return value if keep else None
        if value_type == 9:  # ARRAY
            element_type = self._read_u32(stream, file_size)
            count = self._read_u64(stream, file_size)
            self._check_metadata_budget(stream)
            if count > self.MAX_METADATA_ARRAY_ITEMS or count > self._metadata_array_items_remaining:
                raise ValueError("GGUF metadata array exceeds supported limits")
            self._metadata_array_items_remaining -= count
            values = [] if keep else None
            for _ in range(count):
                item = self._read_value(stream, file_size, element_type, keep=keep, depth=depth + 1)
                if keep:
                    values.append(item)
                self._check_metadata_budget(stream)
            return values
        fmt = self._SCALAR_FORMATS.get(value_type)
        if fmt is None:
            raise ValueError(f"Unsupported GGUF metadata value type: {value_type}")
        raw = self._read_exact(stream, struct.calcsize(fmt), file_size)
        self._check_metadata_budget(stream)
        value = struct.unpack(fmt, raw)[0]
        if value_type == 7:
            if value not in (0, 1):
                raise ValueError("Invalid GGUF boolean metadata value")
            value = bool(value)
        return value if keep else None

    def _check_metadata_budget(self, stream) -> None:
        if stream.tell() - 24 > self.MAX_METADATA_TABLE_BYTES:
            raise ValueError("GGUF metadata table exceeds supported limits")

    @classmethod
    def _read_string(cls, stream, file_size: int) -> str:
        length = cls._read_u64(stream, file_size)
        if length > cls.MAX_METADATA_STRING_BYTES:
            raise ValueError("GGUF metadata string exceeds supported limits")
        raw = cls._read_exact(stream, length, file_size)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("GGUF metadata contains invalid UTF-8") from exc

    @classmethod
    def _read_u32(cls, stream, file_size: int) -> int:
        return struct.unpack("<I", cls._read_exact(stream, 4, file_size))[0]

    @classmethod
    def _read_u64(cls, stream, file_size: int) -> int:
        return struct.unpack("<Q", cls._read_exact(stream, 8, file_size))[0]

    @staticmethod
    def _read_exact(stream, size: int, file_size: int) -> bytes:
        if size < 0 or stream.tell() + size > file_size:
            raise ValueError("GGUF metadata is truncated")
        raw = stream.read(size)
        if len(raw) != size:
            raise ValueError("GGUF metadata is truncated")
        return raw

    @staticmethod
    def dequantize_q4_0(block_data: bytes, scale: float = 1.0) -> list[float]:
        """Decode GGUF Q4_0 blocks; ``scale`` is an optional outer multiplier."""
        if not isinstance(scale, (int, float)):
            raise ValueError("scale must be numeric")
        if len(block_data) % 18:
            raise ValueError("Q4_0 data length must be a multiple of 18 bytes")
        values = []
        for b_idx in range(0, len(block_data), 18):
            d = struct.unpack_from("<e", block_data, b_idx)[0] * scale
            quants = block_data[b_idx + 2 : b_idx + 18]
            values.extend(((byte & 0x0F) - 8) * d for byte in quants)
            values.extend(((byte >> 4) - 8) * d for byte in quants)
        return values

    @staticmethod
    def dequantize_q4_1(block_data: bytes) -> list[float]:
        """Dequantize Q4_1 block weights (scale + min + 32 nibbles)."""
        if len(block_data) % 20:
            raise ValueError("Q4_1 data length must be a multiple of 20 bytes")
        values = []
        for b_idx in range(0, len(block_data), 20):
            d, minimum = struct.unpack_from("<ee", block_data, b_idx)
            quants = block_data[b_idx + 4 : b_idx + 20]
            values.extend((byte & 0x0F) * d + minimum for byte in quants)
            values.extend((byte >> 4) * d + minimum for byte in quants)
        return values

    @staticmethod
    def dequantize_q8_0(block_data: bytes) -> list[float]:
        """Dequantize Q8_0 block weights (scale + 32 int8 values)."""
        if len(block_data) % 34:
            raise ValueError("Q8_0 data length must be a multiple of 34 bytes")
        values = []
        for b_idx in range(0, len(block_data), 34):
            scale = struct.unpack_from("<e", block_data, b_idx)[0]
            values.extend(value * scale for value in struct.unpack_from("<32b", block_data, b_idx + 2))
        return values

    @staticmethod
    def dequantize_f16(data: bytes) -> list[float]:
        """Convert float16 buffer to float32 values."""
        if len(data) % 2:
            raise ValueError("F16 data length must be a multiple of 2 bytes")
        count = len(data) // 2
        return [float(struct.unpack_from("<e", data, i * 2)[0]) for i in range(count)]

    @staticmethod
    def dequantize_f32(data: bytes) -> list[float]:
        """Decode a little-endian F32 tensor buffer."""
        if len(data) % 4:
            raise ValueError("F32 data length must be a multiple of 4 bytes")
        count = len(data) // 4
        return [float(struct.unpack_from("<f", data, i * 4)[0]) for i in range(count)]

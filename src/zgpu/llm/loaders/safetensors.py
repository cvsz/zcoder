"""Safetensors Weight Loader for zGPU.

Parses Safetensors header JSON metadata and extracts tensor buffers for device memory loading.
"""

from __future__ import annotations

import json
import math
import struct
from typing import Any, ClassVar


class SafetensorsLoader:
    """Parser and weight loader for Safetensors model files."""

    MAX_HEADER_BYTES = 100 * 1024 * 1024
    DTYPE_BYTES: ClassVar[dict[str, int]] = {
        "BOOL": 1,
        "U8": 1,
        "I8": 1,
        "F8_E4M3": 1,
        "F8_E4M3FN": 1,
        "F8_E5M2": 1,
        "I16": 2,
        "U16": 2,
        "F16": 2,
        "BF16": 2,
        "I32": 4,
        "U32": 4,
        "F32": 4,
        "I64": 8,
        "U64": 8,
        "F64": 8,
    }

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.header: dict[str, Any] = {}
        self.header_size = 0

    def parse_header(self, raw_bytes: bytes) -> dict[str, Any]:
        """Parse 8-byte little-endian header length followed by JSON header."""
        if not isinstance(raw_bytes, bytes) or len(raw_bytes) < 8:
            raise ValueError("Invalid Safetensors file: too short")
        header_len = struct.unpack_from("<Q", raw_bytes)[0]
        if header_len <= 0 or header_len > self.MAX_HEADER_BYTES:
            raise ValueError("Invalid Safetensors file: header size is outside supported limits")
        if header_len > len(raw_bytes) - 8:
            raise ValueError("Invalid Safetensors file: header length exceeds file size")
        header_size = 8 + header_len
        try:
            header_json = raw_bytes[8:header_size].decode("utf-8")
            header = json.loads(header_json, object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Invalid Safetensors file: header must contain unique-key UTF-8 JSON") from exc
        if not isinstance(header, dict):
            raise ValueError("Invalid Safetensors file: header must be a JSON object")

        payload_size = len(raw_bytes) - header_size
        ranges = []
        for name, info in header.items():
            if name == "__metadata__":
                if not isinstance(info, dict) or any(
                    not isinstance(key, str) or not isinstance(value, str) for key, value in info.items()
                ):
                    raise ValueError("Invalid Safetensors file: metadata must map strings to strings")
                continue
            self._validate_tensor_info(name, info, payload_size, ranges)
        ranges.sort()
        previous_end = 0
        for start, end in ranges:
            if start != previous_end:
                raise ValueError("Invalid Safetensors file: tensor data ranges overlap or contain gaps")
            previous_end = end
        if previous_end != payload_size:
            raise ValueError("Invalid Safetensors file: tensor offsets leave gaps or trailing data")

        self.header_size = header_size
        self.header = header
        return self.header

    @classmethod
    def _validate_tensor_info(
        cls, name: Any, info: Any, payload_size: int, ranges: list[tuple[int, int]]
    ) -> None:
        if not isinstance(name, str) or not name or not isinstance(info, dict):
            raise ValueError("Invalid Safetensors file: tensor entries must be named objects")
        dtype = info.get("dtype")
        shape = info.get("shape")
        offsets = info.get("data_offsets")
        if not isinstance(dtype, str) or dtype not in cls.DTYPE_BYTES:
            raise ValueError(f"Invalid Safetensors file: unsupported dtype for tensor {name}")
        if not isinstance(shape, list) or any(
            isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 0
            for dimension in shape
        ):
            raise ValueError(f"Invalid Safetensors file: invalid shape for tensor {name}")
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or any(isinstance(offset, bool) or not isinstance(offset, int) for offset in offsets)
        ):
            raise ValueError(f"Invalid Safetensors file: invalid offsets for tensor {name}")
        start, end = offsets
        expected_bytes = math.prod(shape) * cls.DTYPE_BYTES[dtype]
        if start < 0 or end < start or end > payload_size or end - start != expected_bytes:
            raise ValueError(f"Invalid Safetensors file: data range does not match tensor {name}")
        if start != end:
            ranges.append((start, end))

    def get_tensor_info(self, tensor_name: str) -> dict[str, Any]:
        """Retrieve dtype, shape, and byte offsets for a named tensor."""
        if (
            not isinstance(tensor_name, str)
            or tensor_name == "__metadata__"
            or tensor_name not in self.header
        ):
            raise KeyError(f"Tensor {tensor_name} not found in Safetensors header")
        return self.header[tensor_name]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

"""Golden-vector coverage for model file parsing primitives."""

from __future__ import annotations

import struct

import pytest

from zgpu.llm.loaders.gguf import GGUFLoader
from zgpu.llm.loaders.safetensors import SafetensorsLoader


def test_gguf_header_requires_complete_supported_fixed_header():
    loader = GGUFLoader("unused.gguf")
    header = struct.pack("<IIQQ", GGUFLoader.GGUF_MAGIC, 3, 12, 7)
    assert loader.parse_header(header) == {"version": 3, "tensor_count": 12, "kv_count": 7}
    for size in (0, 15, 16, 23):
        with pytest.raises(ValueError, match="too short"):
            loader.parse_header(header[:size])
    with pytest.raises(ValueError, match="Invalid GGUF magic"):
        loader.parse_header(struct.pack("<IIQQ", 0, 3, 0, 0))
    with pytest.raises(ValueError, match="Unsupported GGUF version"):
        loader.parse_header(struct.pack("<IIQQ", GGUFLoader.GGUF_MAGIC, 4, 0, 0))


def _gguf_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _gguf_fixture(*entries: tuple[str, int, bytes]) -> bytes:
    payload = bytearray(struct.pack("<IIQQ", GGUFLoader.GGUF_MAGIC, 3, 0, len(entries)))
    for key, value_type, value in entries:
        payload.extend(_gguf_string(key))
        payload.extend(struct.pack("<I", value_type))
        payload.extend(value)
    return bytes(payload)


def test_gguf_reads_architecture_and_selected_metadata_without_tensor_data(tmp_path):
    model = tmp_path / "metadata.gguf"
    model.write_bytes(
        _gguf_fixture(
            ("general.architecture", 8, _gguf_string("gemma")),
            ("general.name", 8, _gguf_string("Gemma fixture")),
            ("tokenizer.ggml.tokens", 9, struct.pack("<IQ", 8, 2) + _gguf_string("a") + _gguf_string("b")),
        )
    )
    loader = GGUFLoader(str(model))
    metadata = loader.read_metadata(keys={"general.architecture", "general.name"})
    assert metadata == {"general.architecture": "gemma", "general.name": "Gemma fixture"}
    assert loader.read_metadata(keys={"general.architecture"}) == {"general.architecture": "gemma"}


def test_gguf_reader_can_select_bounded_numeric_architecture_metadata(tmp_path):
    model = tmp_path / "architecture.gguf"
    model.write_bytes(
        _gguf_fixture(
            ("general.architecture", 8, _gguf_string("qwen2")),
            ("qwen2.context_length", 4, struct.pack("<I", 32768)),
            ("qwen2.block_count", 4, struct.pack("<I", 28)),
            ("untrusted.context_length", 9, struct.pack("<IQ", 0, 2) + b"ab"),
        )
    )
    metadata = GGUFLoader(str(model)).read_metadata(
        keys={"general.architecture"},
        key_suffixes={"context_length", "block_count"},
    )
    assert metadata == {
        "general.architecture": "qwen2",
        "qwen2.context_length": 32768,
        "qwen2.block_count": 28,
    }


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ((("general.architecture", 13, b""),), "Unsupported GGUF metadata value type"),
        ((("general.architecture", 8, struct.pack("<Q", 8) + b"x"),), "truncated"),
        ((("duplicate", 4, struct.pack("<I", 1)), ("duplicate", 4, struct.pack("<I", 2))), "unique"),
        ((("flag", 7, b"\x02"),), "boolean"),
    ],
)
def test_gguf_metadata_parser_rejects_malformed_tables(tmp_path, entries, message):
    model = tmp_path / "bad.gguf"
    model.write_bytes(_gguf_fixture(*entries))
    with pytest.raises(ValueError, match=message):
        GGUFLoader(str(model)).read_metadata()


def test_gguf_metadata_parser_enforces_total_array_and_byte_budgets(tmp_path, monkeypatch):
    model = tmp_path / "over-budget.gguf"
    array = struct.pack("<IQ", 0, 2) + b"ab"
    model.write_bytes(
        _gguf_fixture(
            ("first", 9, array),
            ("second", 9, struct.pack("<IQ", 0, 1) + b"c"),
        )
    )
    monkeypatch.setattr(GGUFLoader, "MAX_TOTAL_METADATA_ARRAY_ITEMS", 2)
    with pytest.raises(ValueError, match="array exceeds supported limits"):
        GGUFLoader(str(model)).read_metadata()

    monkeypatch.setattr(GGUFLoader, "MAX_TOTAL_METADATA_ARRAY_ITEMS", 2_000_000)
    monkeypatch.setattr(GGUFLoader, "MAX_METADATA_TABLE_BYTES", 1)
    with pytest.raises(ValueError, match="table exceeds supported limits"):
        GGUFLoader(str(model)).read_metadata()

    model.write_bytes(_gguf_fixture(("empty", 9, struct.pack("<IQ", 0, 0))))
    with pytest.raises(ValueError, match="table exceeds supported limits"):
        GGUFLoader(str(model)).read_metadata()


def test_gguf_metadata_parser_rejects_symbolic_link_input(tmp_path):
    target = tmp_path / "target.gguf"
    target.write_bytes(_gguf_fixture())
    link = tmp_path / "link.gguf"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        GGUFLoader(str(link)).read_metadata()


def test_gguf_q4_0_dequantization_matches_block_layout():
    block = struct.pack("<e", 0.5) + bytes(range(16))
    expected = [(value - 8) * 0.5 for value in range(16)] + [-4.0] * 16
    assert GGUFLoader.dequantize_q4_0(block) == expected
    assert GGUFLoader.dequantize_q4_0(block, scale=2.0) == [value * 2 for value in expected]


def test_gguf_q4_1_dequantization_uses_half_scale_and_minimum():
    block = struct.pack("<ee", 0.5, -1.0) + bytes([0x21]) * 16
    assert GGUFLoader.dequantize_q4_1(block) == [-0.5] * 16 + [0.0] * 16


def test_gguf_q8_0_dequantization_uses_half_scale_and_signed_bytes():
    block = struct.pack("<e", 0.25) + struct.pack("<32b", *range(-16, 16))
    assert GGUFLoader.dequantize_q8_0(block) == [value * 0.25 for value in range(-16, 16)]


@pytest.mark.parametrize(
    ("decoder", "data"),
    [
        (GGUFLoader.dequantize_q4_0, b"\0"),
        (GGUFLoader.dequantize_q4_1, b"\0"),
        (GGUFLoader.dequantize_q8_0, b"\0"),
        (GGUFLoader.dequantize_f16, b"\0"),
        (GGUFLoader.dequantize_f32, b"\0"),
    ],
)
def test_gguf_decoders_reject_incomplete_blocks(decoder, data):
    with pytest.raises(ValueError, match="length must be a multiple"):
        decoder(data)


def test_gguf_f16_and_f32_decode_little_endian_values():
    assert GGUFLoader.dequantize_f16(struct.pack("<2e", 1.5, -2.0)) == [1.5, -2.0]
    assert GGUFLoader.dequantize_f32(struct.pack("<2f", 1.25, -3.5)) == [1.25, -3.5]


def _safetensors_file(header: bytes, payload: bytes = b"") -> bytes:
    return struct.pack("<Q", len(header)) + header + payload


def test_safetensors_parser_validates_tensor_layout_and_metadata():
    header = (
        b'{"first":{"dtype":"F16","shape":[2],"data_offsets":[0,4]},'
        b'"second":{"dtype":"F32","shape":[1],"data_offsets":[4,8]},'
        b'"__metadata__":{"format":"pt"}}'
    )
    loader = SafetensorsLoader("unused.safetensors")
    parsed = loader.parse_header(_safetensors_file(header, b"12345678"))
    assert loader.header_size == 8 + len(header)
    assert parsed["__metadata__"] == {"format": "pt"}
    assert loader.get_tensor_info("first") == {"dtype": "F16", "shape": [2], "data_offsets": [0, 4]}
    with pytest.raises(KeyError):
        loader.get_tensor_info("__metadata__")


@pytest.mark.parametrize(
    ("header", "payload", "message"),
    [
        (b"[]", b"", "JSON object"),
        (b'{"x":{},"x":{}}', b"", "unique-key"),
        (b'{"x":{"dtype":"NOPE","shape":[],"data_offsets":[0,0]}}', b"", "unsupported dtype"),
        (b'{"x":{"dtype":"F32","shape":[true],"data_offsets":[0,4]}}', b"1234", "invalid shape"),
        (b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[0,8]}}', b"1234", "data range"),
        (b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[1,5]}}', b"123456", "gaps"),
        (b'{"x":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}', b"12345", "gaps"),
        (b'{"__metadata__":{"format":1}}', b"", "strings to strings"),
    ],
)
def test_safetensors_parser_rejects_invalid_headers(header, payload, message):
    with pytest.raises(ValueError, match=message):
        SafetensorsLoader("unused.safetensors").parse_header(_safetensors_file(header, payload))


def test_safetensors_parser_rejects_truncated_and_oversized_headers():
    loader = SafetensorsLoader("unused.safetensors")
    with pytest.raises(ValueError, match="too short"):
        loader.parse_header(b"\0" * 7)
    with pytest.raises(ValueError, match="exceeds file size"):
        loader.parse_header(struct.pack("<Q", 32) + b"{}")
    with pytest.raises(ValueError, match="supported limits"):
        loader.parse_header(struct.pack("<Q", loader.MAX_HEADER_BYTES + 1))

"""Upgrade-55 / parity workstream W4 — ``read_text_prefix`` fail-closed rules.

The code-agent Read tool and the registry example tool previously did
``path.read_text()`` directly: an oversized file was loaded wholesale
into memory behind a small ``[:8000]`` slice, binary blobs were decoded
into mojibake context, and reading a workspace FIFO blocked the agent
forever. These tests pin the hardened behavior.
"""

import os
import types

import pytest

from zcoder.core.exceptions import ValidationError
from zcoder.core.security import READ_PREFIX_BYTES_DEFAULT, read_text_prefix

# ---------------------------------------------------------------------------
# Unit rules of read_text_prefix
# ---------------------------------------------------------------------------


def test_plain_text_reads_unchanged(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("def add(a, b):\n    return a + b\n")
    assert read_text_prefix(f) == f.read_text()


def test_binary_extensions_refused(tmp_path):
    # .xlsm/.parquet/.epub/.heic mirror the claude-code fix; the rest are
    # the other container/media formats a workspace realistically holds.
    for suffix in (".xlsm", ".parquet", ".epub", ".heic", ".png", ".zip", ".sqlite"):
        f = tmp_path / f"blob{suffix}"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"junk")
        with pytest.raises(ValidationError, match="binary file"):
            read_text_prefix(f)


def test_nul_sniff_refuses_binary_content(tmp_path):
    # A binary payload behind a benign extension must not sneak through.
    f = tmp_path / "payload.dat"
    f.write_bytes(b"valid-text-prefix" + b"\x00" + b"binary-rest")
    with pytest.raises(ValidationError, match="binary content"):
        read_text_prefix(f)


def test_oversized_file_truncated_with_honest_marker(tmp_path):
    f = tmp_path / "big.txt"
    size = READ_PREFIX_BYTES_DEFAULT + 5
    f.write_bytes(b"A" * size)
    out = read_text_prefix(f, max_chars=8000)
    assert out.startswith("A" * 10)
    assert "[TRUNCATED — showing first" in out
    assert f"of {size}-byte file]" in out
    assert len(out) <= 8000  # marker is placed, not sliced away


def test_file_exactly_at_limit_not_truncated(tmp_path):
    f = tmp_path / "exact.txt"
    f.write_bytes(b"y" * READ_PREFIX_BYTES_DEFAULT)
    out = read_text_prefix(f)
    assert len(out) == READ_PREFIX_BYTES_DEFAULT
    assert "[TRUNCATED" not in out


def test_max_chars_cap_without_marker(tmp_path):
    f = tmp_path / "medium.txt"
    f.write_text("x" * 12000)
    out = read_text_prefix(f, max_chars=8000)
    assert len(out) == 8000
    assert "[TRUNCATED" not in out


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO semantics")
def test_fifo_refused_before_open(tmp_path):
    # The stat guard must fire before any descriptor is opened, so the
    # agent can never block forever on a workspace FIFO.
    fifo = tmp_path / "pipe.fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValidationError, match="non-regular file"):
        read_text_prefix(fifo)


def test_directory_refused(tmp_path):
    with pytest.raises(ValidationError, match="directory"):
        read_text_prefix(tmp_path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_text_prefix(tmp_path / "absent.txt")


def test_empty_file_returns_empty_text(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    assert read_text_prefix(f) == ""


def test_oversized_custom_limit(tmp_path):
    f = tmp_path / "small-big.txt"
    f.write_bytes(b"z" * 2048)
    out = read_text_prefix(f, max_bytes=1024)
    assert out.startswith("z" * 4)
    assert "of 2048-byte file]" in out
    assert len(out) <= 1024 + len("\n[TRUNCATED — showing first 1024 bytes of 2048-byte file]")


# ---------------------------------------------------------------------------
# Production wiring: every Read path must go through the guard
# ---------------------------------------------------------------------------


def test_registry_example_read_file_is_hardened(tmp_path):
    from zcoder.claude.tools.registry import build_code_tools_registry

    reg = build_code_tools_registry(cwd=str(tmp_path))
    binary = tmp_path / "dump.xlsm"
    binary.write_bytes(b"\x00\x01\x02binary")
    result = reg.execute("read_file", {"path": "dump.xlsm"})
    assert "[ERROR]" in result and "binary" in result

    plain = tmp_path / "code.py"
    plain.write_text("print('hi')\n")
    assert "print('hi')" in reg.execute("read_file", {"path": "code.py"})


def test_code_agent_read_tool_is_hardened(tmp_path):
    from zcoder.claude.capabilities.code import CodeAgent

    agent = CodeAgent(api_key="test-key")
    session = types.SimpleNamespace(cwd=str(tmp_path))

    binary = tmp_path / "dump.xlsm"
    binary.write_bytes(b"\x00\x01\x02binary")
    result = agent._run_tool("Read", {"path": "dump.xlsm"}, session)
    assert "binary" in result

    plain = tmp_path / "code.py"
    plain.write_text("print('hi')\n")
    assert "print('hi')" in agent._run_tool("Read", {"path": "code.py"}, session)

    fifo = tmp_path / "pipe.fifo"
    if hasattr(os, "mkfifo"):
        os.mkfifo(fifo)
        blocked = agent._run_tool("Read", {"path": "pipe.fifo"}, session)
        assert "Refusing" in blocked

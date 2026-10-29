"""Tests for authorized local-only discovery and conservative model ranking."""

import hashlib
import json

import pytest

from zgpu.cluster.hardware_discovery import _rank, collect, rank_files


def sample(node_id="node-a", ram=64, gpus=None):
    return {
        "schema": "zgpu.hardware.v1",
        "node_id": node_id,
        "observed_at": "2026-10-22T00:00:00+00:00",
        "authorized": True,
        "source": "local-opt-in",
        "os": "Linux",
        "arch": "x86_64",
        "cpu": {"name": "CPU", "logical_cores": 8},
        "ram_gib": ram,
        "gpus": gpus or [],
        "benchmark": None,
    }


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_requires_explicit_host_authorization():
    with pytest.raises(ValueError, match="authorized-host"):
        collect("node-a", False)


def test_invalid_node_id_rejected():
    with pytest.raises(ValueError):
        collect("../etc/passwd", True)


def test_rank_sorted_by_feasibility_and_capacity(tmp_path):
    small = write(tmp_path, "small.json", sample("small", 16))
    large = write(tmp_path, "large.json", sample("large", 96))
    result = rank_files([small, large], "70b-q4")
    assert [n["node_id"] for n in result["nodes"]] == ["large", "small"]
    assert result["nodes"][0]["single_node_candidate"]
    assert not result["nodes"][1]["single_node_candidate"]
    assert result["nodes"][0]["status"] == "capacity-estimate-only"


def test_rejects_unapproved_duplicated_and_malformed(tmp_path):
    good = write(tmp_path, "good.json", sample())
    denied = sample("denied")
    denied["authorized"] = False
    bad = write(tmp_path, "bad.json", denied)
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{oops", encoding="utf-8")
    result = rank_files([good, good, bad, str(corrupt)], "32b-q4")
    assert len(result["nodes"]) == 1
    assert len(result["rejected"]) == 3


def test_unknown_gpu_not_counted_as_usable_cuda(tmp_path):
    path = write(
        tmp_path, "gpu.json", sample("unknown", 8, [{"name": "GPU", "vram_gib": 80, "backend": "unknown"}])
    )
    result = rank_files([path], "70b-q4")
    assert not result["nodes"][0]["single_node_candidate"]


def test_integrity_hash_matches_raw_inventory(tmp_path):
    path = write(tmp_path, "hash.json", sample())
    result = rank_files([path], "32b-q4")
    assert (
        result["nodes"][0]["inventory_sha256"]
        == hashlib.sha256((tmp_path / "hash.json").read_bytes()).hexdigest()
    )


def test_score_does_not_use_benchmark_without_hash():
    node = sample()
    node["benchmark"] = {"verified": True, "tokens_per_second": 1000}
    assert _rank(node, "32b-q4")["benchmark_evidence"] == "missing"


def test_zero_and_negative_ram_are_rejected(tmp_path):
    for value in (0, -1, True):
        path = write(tmp_path, "ram.json", sample(ram=value))
        assert rank_files([path], "32b-q4")["rejected"]

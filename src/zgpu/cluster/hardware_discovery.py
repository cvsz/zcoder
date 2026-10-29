"""Opt-in, local-only hardware inventory and evidence-based model placement.

No network probing, remote command execution or automatic enrollment.
Run on each authorized host and transfer the resulting JSON through an approved channel.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

SCHEMA = "zgpu.hardware.v1"
MODELS = {"32b-q4": 24, "70b-q4": 52}  # Planning budgets in GiB, NOT measured model footprints.


def _command(argv: list[str], timeout: int = 3) -> str:
    if not shutil.which(argv[0]):
        return ""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout[:32768] if result.returncode == 0 else ""


def _memory_gib() -> float | None:
    if os.path.isfile("/proc/meminfo"):
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1048576, 2)
    if os.name == "nt":
        raw = _command(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ]
        )
        try:
            return round(int(raw.strip()) / 1073741824, 2)
        except ValueError:
            pass
    return None


def _linux_gpus() -> list[dict]:
    devices = []
    raw = _command(
        ["nvidia-smi", "--query-gpu=name,memory.total,uuid", "--format=csv,noheader,nounits"], timeout=5
    )
    for line in raw.splitlines():
        parts = [v.strip() for v in line.split(",")]
        if len(parts) == 3:
            try:
                memory = round(float(parts[1]) / 1024, 2)
            except ValueError:
                memory = None
            devices.append({"name": parts[0], "vram_gib": memory, "backend": "cuda", "device_id": parts[2]})
    if not devices:
        # PCI listings do not establish usable VRAM or driver support.
        raw = _command(["lspci", "-nn"])
        for line in raw.splitlines():
            if re.search(r"VGA compatible controller|3D controller|Display controller", line, re.I):
                devices.append(
                    {
                        "name": line.split(": ", 1)[-1][:180],
                        "vram_gib": None,
                        "backend": "unknown",
                        "device_id": None,
                    }
                )
    return devices[:32]


def collect(node_id: str, approved: bool) -> dict:
    if not approved:
        raise ValueError("Explicit --authorized-host confirmation is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", node_id):
        raise ValueError("Invalid node ID")
    cpu = platform.processor() or platform.machine()
    cores = os.cpu_count()
    raw_cpu = _command(["lscpu"])
    for line in raw_cpu.splitlines():
        if line.startswith("Model name:"):
            cpu = line.partition(":")[2].strip()
            break
    record = {
        "schema": SCHEMA,
        "node_id": node_id,
        "observed_at": dt.datetime.now(dt.UTC).isoformat(),
        "authorized": True,
        "source": "local-opt-in",
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu": {"name": cpu, "logical_cores": cores},
        "ram_gib": _memory_gib(),
        "gpus": _linux_gpus() if os.name != "nt" else [],
        "benchmark": None,
    }
    return record


def _valid(record: dict) -> bool:
    try:
        if record["schema"] != SCHEMA or record["authorized"] is not True:
            return False
        if record["source"] != "local-opt-in":
            return False
        dt.datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", record["node_id"]):
            return False
        ram = record["ram_gib"]
        if ram is not None and (
            not isinstance(ram, (int, float)) or isinstance(ram, bool) or not 0 < ram < 8192
        ):
            return False
        if not isinstance(record["gpus"], list) or len(record["gpus"]) > 32:
            return False
        for gpu in record["gpus"]:
            vram = gpu["vram_gib"]
            if vram is not None and (
                not isinstance(vram, (int, float)) or isinstance(vram, bool) or not 0 < vram < 1024
            ):
                return False
        return True
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def _rank(record: dict, model: str) -> dict:
    # Do not count RAM and VRAM as an additive pool: unified memory / offload
    # suitability depends on backend support. Ranking is planning-only.
    ram = record.get("ram_gib") or 0
    vram = max((g.get("vram_gib") or 0 for g in record["gpus"] if g.get("backend") == "cuda"), default=0)
    usable_ram = max(0.0, ram - max(4.0, ram * 0.2))
    usable_vram = max(0.0, vram - 2.0)
    required = MODELS[model]
    feasible = usable_ram >= required or usable_vram >= required
    capacity = max(usable_ram, usable_vram)
    bench = record.get("benchmark")
    verified_bench = (
        isinstance(bench, dict)
        and bench.get("verified") is True
        and isinstance(bench.get("tokens_per_second"), (int, float))
        and not isinstance(bench.get("tokens_per_second"), bool)
        and 0 < bench["tokens_per_second"] < 100000
        and isinstance(bench.get("evidence_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", bench["evidence_sha256"])
    )
    # Explicitly prioritize feasibility over heuristic score. Do not infer
    # acceleration from PCI presence or unverified claimed benchmarks.
    score = round(
        min(capacity / required, 2) * 50
        + (min(bench["tokens_per_second"], 100) / 2 if verified_bench else 0),
        2,
    )
    return {
        "node_id": record["node_id"],
        "model": model,
        "single_node_candidate": feasible,
        "usable_ram_gib_estimate": round(usable_ram, 2),
        "usable_cuda_vram_gib_estimate": round(usable_vram, 2),
        "benchmark_evidence": "reported-with-hash" if verified_bench else "missing",
        "score": score,
        "status": "capacity-estimate-only",
    }


def rank_files(paths: list[str], model: str) -> dict:
    if model not in MODELS:
        raise ValueError("Unsupported model planning profile")
    seen = set()
    results = []
    rejected = []
    for path in paths:
        try:
            if Path(path).stat().st_size > 131072:
                raise ValueError("inventory exceeds size limit")
            raw = Path(path).read_bytes()
            record = json.loads(raw)
            if not isinstance(record, dict) or not _valid(record):
                raise ValueError("invalid or unauthorized inventory")
            node_id = record["node_id"]
            if node_id in seen:
                raise ValueError("duplicate node ID")
            seen.add(node_id)
            entry = _rank(record, model)
            entry["inventory_sha256"] = hashlib.sha256(raw).hexdigest()
            results.append(entry)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"file": Path(path).name, "reason": str(exc)})
    results.sort(key=lambda x: (not x["single_node_candidate"], -x["score"], x["node_id"]))
    return {
        "schema": "zgpu.ranking.v1",
        "model": model,
        "planning_weight_budget_gib": MODELS[model],
        "nodes": results,
        "rejected": rejected,
        "warning": "Offline self-reported inventory; hashes are integrity markers, not attestations. "
        "No real-model load, GPU capability, LAN speed or distributed sharding has been verified.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in hardware discovery; no network scanning")
    sub = parser.add_subparsers(dest="action", required=True)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--node-id", required=True)
    inventory.add_argument("--authorized-host", action="store_true")
    inventory.add_argument("--output", required=True)
    ranking = sub.add_parser("rank")
    ranking.add_argument("--model", choices=tuple(MODELS), required=True)
    ranking.add_argument("inventories", nargs="+")
    args = parser.parse_args(argv)
    if args.action == "inventory":
        record = collect(args.node_id, args.authorized_host)
        output = Path(args.output)
        if output.exists():
            parser.error("output already exists; refusing overwrite")
        output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Inventory written to {output} (review before sharing)")
    else:
        print(json.dumps(rank_files(args.inventories, args.model), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

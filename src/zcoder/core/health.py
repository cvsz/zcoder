"""
health.py — Liveness/readiness checks for container orchestration

Exposed via `--health-check` (main.py) and used as the Docker HEALTHCHECK
command (see Dockerfile). The lightweight check verifies runtime basics;
the optional deep check sends one prompt to the configured local model.

For a true end-to-end check against the live API, use `--health-check --deep`
sparingly (e.g. a startup probe run once, not a liveness probe run every 5s).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field

from zcoder.config.settings import CONFIG_PATH


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HealthReport:
    checks: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def healthy(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "status": "healthy" if self.healthy else "unhealthy",
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks],
        }


def _check_local_provider() -> CheckResult:
    provider = os.getenv("ZCODER_PROVIDER", "llama_cpp").strip().lower()
    ok = provider in {"llama_cpp", "local"}
    detail = "local inference; no API key required" if ok else "remote providers are disabled"
    return CheckResult("local_provider_configured", ok, detail)


def _check_config_writable() -> CheckResult:
    try:
        directory = os.path.dirname(CONFIG_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".zcoder_health_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return CheckResult("config_dir_writable", True)
    except Exception as e:
        return CheckResult("config_dir_writable", False, str(e))


def _check_python_version() -> CheckResult:
    ok = sys.version_info >= (3, 10)
    return CheckResult(
        "python_version", ok, f"{sys.version.split()[0]} ({'ok' if ok else 'requires >= 3.10'})"
    )


def _check_local_inference(model: str = "zcoder-qwen2.5-coder-7b") -> CheckResult:
    """Deep check — makes one minimal loopback model call. Only run explicitly."""
    try:
        from zcoder.services.coder import Coder

        c = Coder(model=model, max_tokens=8)
        result = c.generate("Reply with the single word: ok")
        ok = not str(result).startswith("[ERROR]")
        return CheckResult("local_inference", ok, str(result)[:200])
    except Exception as e:
        return CheckResult("local_inference", False, str(e))


def run_health_check(deep: bool = False) -> HealthReport:
    report = HealthReport()
    report.checks.append(_check_python_version())
    report.checks.append(_check_config_writable())
    report.checks.append(_check_local_provider())
    if deep:
        report.checks.append(_check_local_inference())

    return report

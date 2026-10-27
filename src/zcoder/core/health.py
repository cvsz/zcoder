"""Liveness/readiness checks for the local model client and CLI runtime."""

from __future__ import annotations

import os
import sys
import time
import urllib.parse
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


def _check_model_config() -> CheckResult:
    base_url = os.getenv("ZCODER_BASE_URL", "http://127.0.0.1:8080/v1").strip()
    model = os.getenv("ZCODER_MODEL", "zqwen2.5-coder-7b-instruct-q4_k_m").strip()
    parsed = urllib.parse.urlsplit(base_url)
    valid_url = (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    if not valid_url:
        return CheckResult("local_model_configured", False, "ZCODER_BASE_URL must use loopback HTTP")
    if not model:
        return CheckResult("local_model_configured", False, "ZCODER_MODEL must not be empty")
    return CheckResult("local_model_configured", True)


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
    ok = sys.version_info >= (3, 12)
    return CheckResult(
        "python_version", ok, f"{sys.version.split()[0]} ({'ok' if ok else 'requires >= 3.12'})"
    )


def _check_live_model(model: str = "zqwen2.5-coder-7b-instruct-q4_k_m") -> CheckResult:
    """Deep check — make one minimal request to the configured local model."""
    try:
        from zcoder.services.coder import Coder

        c = Coder(model=model, max_tokens=8)
        result = c.generate("Reply with the single word: ok")
        ok = not str(result).startswith("[ERROR]") and not str(result).startswith("[API ERROR")
        return CheckResult("local_model_call", ok, str(result)[:200])
    except Exception as e:
        return CheckResult("local_model_call", False, str(e))


def run_health_check(deep: bool = False) -> HealthReport:
    report = HealthReport()
    report.checks.append(_check_python_version())
    report.checks.append(_check_config_writable())
    model_check = _check_model_config()
    report.checks.append(model_check)

    if deep and model_check.ok:
        model = os.getenv("ZCODER_MODEL", "zqwen2.5-coder-7b-instruct-q4_k_m")
        report.checks.append(_check_live_model(model))

    return report

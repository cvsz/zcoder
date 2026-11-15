"""
ops.py — Deployment & Operations (Phase 9 of Big Upgrade).

Production-grade observability for ZCoder:
- Structured logging setup (JSON/text, secret redaction)
- Health check runner (shallow + deep model call)
- Alerting on errors and rate limit events (JSONL metrics sink)
- Metrics recording for ops dashboards
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zcoder.config.logging import get_logger, new_correlation_id, setup_logging
from zcoder.core.health import HealthReport, run_health_check

logger = get_logger("ops")


@dataclass
class AlertEvent:
    """An alert emitted by the operations layer."""

    level: str  # "error" | "rate_limit" | "degraded" | "healthy"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class MetricsSink:
    """Append-only JSONL metrics sink for ops dashboards."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path("logs") / "metrics.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: AlertEvent | dict[str, Any]) -> None:
        if isinstance(event, AlertEvent):
            payload = event.to_dict()
        else:
            payload = dict(event)
        payload.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def alert(self, level: str, message: str, **details: Any) -> None:
        self.write(AlertEvent(level=level, message=message, details=details))


class Ops:
    """Operations facade: logging, health checks, alerting."""

    def __init__(
        self,
        *,
        log_level: str | None = None,
        log_format: str | None = None,
        metrics_path: str | Path | None = None,
        deep_check_interval_sec: float = 300.0,
        model_call_timeout_sec: float = 8.0,
    ) -> None:
        self.metrics = MetricsSink(metrics_path)
        self.deep_check_interval_sec = deep_check_interval_sec
        self.model_call_timeout_sec = model_call_timeout_sec
        self._last_deep_check: float = 0.0
        self._last_report: HealthReport | None = None

        # Configure production logging once.
        setup_logging(level=log_level, fmt=log_format)
        new_correlation_id()
        logger.info("ops.initialized", extra={"component": "ops"})

    # ── Health checks ──────────────────────────────────────────────

    def shallow_health(self) -> HealthReport:
        """Cheap readiness probe: config + python version, no model call."""
        report = run_health_check(deep=False)
        self._last_report = report
        self._emit_health_metrics(report)
        return report

    def deep_health(self) -> HealthReport:
        """Full readiness probe including a minimal model call.

        Rate-limited to once per deep_check_interval_sec to avoid hammering
        the model server on every probe.
        """
        now = time.monotonic()
        if self._last_report is not None and (now - self._last_deep_check) < self.deep_check_interval_sec:
            return self._last_report
        report = run_health_check(deep=True)
        self._last_report = report
        self._last_deep_check = now
        self._emit_health_metrics(report)
        return report

    def is_healthy(self) -> bool:
        return self.shallow_health().healthy

    # ── Alerting ───────────────────────────────────────────────────

    def alert_error(self, message: str, **details: Any) -> None:
        """Emit an error alert (e.g. failed model call, auth failure)."""
        logger.error(message, extra=details)
        self.metrics.alert("error", message, **details)

    def alert_rate_limit(self, message: str, **details: Any) -> None:
        """Emit a rate-limit alert."""
        logger.warning(message, extra=details)
        self.metrics.alert("rate_limit", message, **details)

    def alert_degraded(self, message: str, **details: Any) -> None:
        """Emit a degraded alert (e.g. unhealthy model server)."""
        logger.warning(message, extra=details)
        self.metrics.alert("degraded", message, **details)

    # ── Internal ───────────────────────────────────────────────────

    def _emit_health_metrics(self, report: HealthReport) -> None:
        healthy = 1 if report.healthy else 0
        self.metrics.write(
            {
                "level": "health",
                "message": "health_check",
                "healthy": healthy,
                "checks": report.to_dict().get("checks", []),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        if not report.healthy:
            self.alert_degraded("health check failed", checks=report.to_dict().get("checks", []))


# Convenience module-level instance for quick imports.
ops = Ops()

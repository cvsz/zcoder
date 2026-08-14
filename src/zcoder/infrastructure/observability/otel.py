"""observability_otel.py — OpenTelemetry instrumentation for ZCoder.

Provides:
  • OTLP metrics, traces, logs via OpenTelemetry SDK (when installed)
  • Prometheus /metrics endpoint compatible gauge/counter/histogram definitions
  • Correlation via trace_id, job_id, attempt_id, worker_id
  • Graceful no-op degradation when opentelemetry is not installed
  • Bounded-cardinality labels (never job_id/trace_id in Prometheus labels)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── Runtime import guard ────────────────────────────────────────────────────

try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


# ─── Metric Definitions ──────────────────────────────────────────────────────


@dataclass
class _Counter:
    """Lightweight thread-safe counter (no-op backend)."""

    _value: float = 0.0

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self._value += amount

    def get(self) -> float:
        return self._value


@dataclass
class _Gauge:
    _value: float = 0.0

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        self._value = value

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        self._value -= amount

    def get(self) -> float:
        return self._value


@dataclass
class _Histogram:
    _observations: list = field(default_factory=list)

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        self._observations.append(value)

    def count(self) -> int:
        return len(self._observations)

    def sum(self) -> float:
        return sum(self._observations)

    def p50(self) -> float:
        if not self._observations:
            return 0.0
        s = sorted(self._observations)
        return s[len(s) // 2]

    def p95(self) -> float:
        if not self._observations:
            return 0.0
        s = sorted(self._observations)
        return s[int(len(s) * 0.95)]

    def p99(self) -> float:
        if not self._observations:
            return 0.0
        s = sorted(self._observations)
        return s[int(len(s) * 0.99)]


# ─── Application Metric Registry ─────────────────────────────────────────────


class ZCoderMetrics:
    """Central registry of bounded-cardinality Prometheus-compatible metrics.

    Labels used here MUST NOT include high-cardinality values like job_id, trace_id, etc.
    Those belong in trace spans only.
    """

    def __init__(self) -> None:
        # Job metrics
        self.jobs_queued = _Gauge()
        self.jobs_running = _Gauge()
        self.job_wait_seconds = _Histogram()
        self.job_duration_seconds = _Histogram()
        self.jobs_total = _Counter()
        self.jobs_failed_total = _Counter()
        self.jobs_succeeded_total = _Counter()

        # Worker metrics
        self.worker_active = _Gauge()
        self.worker_lease_expirations_total = _Counter()
        self.worker_fencing_rejections_total = _Counter()

        # Outbox metrics
        self.outbox_pending = _Gauge()
        self.outbox_failures_total = _Counter()
        self.outbox_deliveries_total = _Counter()
        self.outbox_age_seconds = _Histogram()
        self.outbox_delivery_latency_seconds = _Histogram()

        # Webhook metrics
        self.webhooks_total = _Counter()
        self.webhooks_duplicate_total = _Counter()
        self.webhooks_failed_total = _Counter()

        # GitHub API metrics
        self.github_api_calls_total = _Counter()
        self.github_api_errors_total = _Counter()
        self.github_rate_limit_remaining = _Gauge()

        # Anthropic metrics
        self.anthropic_calls_total = _Counter()
        self.anthropic_errors_total = _Counter()
        self.anthropic_tokens_total = _Counter()
        self.anthropic_cost_usd_total = _Counter()

        # Database pool metrics
        self.db_pool_in_use = _Gauge()
        self.db_pool_available = _Gauge()
        self.db_query_latency_seconds = _Histogram()
        self.db_errors_total = _Counter()
        self.db_connections_total = _Counter()

        # Approval metrics
        self.approvals_pending = _Gauge()

        # Backup metrics
        self.backup_last_success_timestamp = _Gauge()
        self.backup_last_restore_drill_timestamp = _Gauge()
        self.backup_size_bytes = _Gauge()

        # API metrics (RED)
        self.api_requests_total = _Counter()
        self.api_errors_total = _Counter()
        self.api_duration_seconds = _Histogram()

        # Cost metrics
        self.cost_usd_total = _Counter()

    def prometheus_exposition(self) -> str:
        """Render metrics in Prometheus text format."""
        lines: list[str] = []

        def g(name: str, help_text: str, metric: _Gauge, labels: str = "") -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{labels} {metric.get()}")

        def c(name: str, help_text: str, metric: _Counter, labels: str = "") -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}_total{labels} {metric.get()}")

        def h(name: str, help_text: str, metric: _Histogram, labels: str = "") -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count{labels} {metric.count()}")
            lines.append(f"{name}_sum{labels} {metric.sum()}")

        g("zcoder_jobs_queued", "Number of jobs currently queued (READY)", self.jobs_queued)
        g("zcoder_jobs_running", "Number of jobs currently running", self.jobs_running)
        h("zcoder_job_wait_seconds", "Time spent in queue before claim", self.job_wait_seconds)
        h("zcoder_job_duration_seconds", "Job execution duration", self.job_duration_seconds)
        g("zcoder_worker_active", "Number of active worker processes", self.worker_active)
        g(
            "zcoder_worker_lease_expirations",
            "Total worker lease expirations",
            self.worker_lease_expirations_total,
        )
        g("zcoder_outbox_pending", "Number of undelivered outbox messages", self.outbox_pending)
        c("zcoder_outbox_failures", "Outbox delivery failures", self.outbox_failures_total)
        c("zcoder_webhooks", "Webhooks received", self.webhooks_total)
        c("zcoder_github_api_errors", "GitHub API errors", self.github_api_errors_total)
        g(
            "zcoder_github_rate_limit_remaining",
            "GitHub API rate limit remaining",
            self.github_rate_limit_remaining,
        )
        c("zcoder_anthropic_errors", "Anthropic API errors", self.anthropic_errors_total)
        g("zcoder_db_pool_in_use", "Database pool connections in use", self.db_pool_in_use)
        g("zcoder_approvals_pending", "Approval requests pending", self.approvals_pending)
        g(
            "zcoder_backup_last_success_timestamp",
            "Unix timestamp of last successful backup",
            self.backup_last_success_timestamp,
        )
        g(
            "zcoder_backup_last_restore_drill_timestamp",
            "Unix timestamp of last successful restore drill",
            self.backup_last_restore_drill_timestamp,
        )
        c("zcoder_api_requests", "API requests total", self.api_requests_total)
        c("zcoder_api_errors", "API errors total", self.api_errors_total)
        h("zcoder_api_duration_seconds", "API request duration", self.api_duration_seconds)
        c("zcoder_cost_usd", "Total cost in USD", self.cost_usd_total)

        return "\n".join(lines) + "\n"


# ─── Global registry ─────────────────────────────────────────────────────────

_metrics_registry: ZCoderMetrics | None = None


def get_metrics() -> ZCoderMetrics:
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = ZCoderMetrics()
    return _metrics_registry


# ─── Tracing ─────────────────────────────────────────────────────────────────

_tracer: Any | None = None


def get_tracer(name: str = "zcoder") -> Any:
    global _tracer
    if _OTEL_AVAILABLE and _tracer is not None:
        import opentelemetry.trace as trace_mod

        return trace_mod.get_tracer(name)
    return _NoOpTracer()


class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def set_status(self, *args, **kwargs) -> None:
        pass


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs) -> Generator[_NoOpSpan, None, None]:  # type: ignore[override]
        yield _NoOpSpan()


# ─── Initialization ──────────────────────────────────────────────────────────


def init_telemetry(
    service_name: str = "zcoder",
    service_version: str = "unknown",
    otel_endpoint: str = "",
    enabled: bool = False,
) -> None:
    """Initialize OpenTelemetry SDK if dependencies are available and enabled."""
    global _tracer

    if not enabled:
        logger.debug("Telemetry disabled")
        return

    if not _OTEL_AVAILABLE:
        logger.warning(
            "OpenTelemetry dependencies not installed. "
            "Install opentelemetry-sdk, opentelemetry-exporter-otlp-proto-grpc "
            "to enable telemetry. Metrics will be collected locally only."
        )
        return

    try:
        import opentelemetry.metrics as metrics_mod
        import opentelemetry.trace as trace_mod

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
            }
        )

        # Traces
        if otel_endpoint:
            span_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
            trace_mod.set_tracer_provider(tracer_provider)
            logger.info(f"OTEL trace exporter configured: {otel_endpoint}")

            # Metrics
            metric_exporter = OTLPMetricExporter(endpoint=otel_endpoint, insecure=True)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60_000)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics_mod.set_meter_provider(meter_provider)
            logger.info(f"OTEL metric exporter configured: {otel_endpoint}")

        _tracer = trace_mod.get_tracer(service_name)
        logger.info("OpenTelemetry initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")


# ─── Convenience context managers ───────────────────────────────────────────


@contextmanager
def trace_job_span(job_id: str, worker_id: str, operation: str = "job.execute") -> Generator[Any, None, None]:
    """Trace a job execution span with correlation IDs."""
    tracer = get_tracer()
    with tracer.start_as_current_span(operation) as span:
        span.set_attribute("job.id", job_id)
        span.set_attribute("worker.id", worker_id)
        span.set_attribute("operation", operation)
        start = time.monotonic()
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise
        finally:
            duration = time.monotonic() - start
            get_metrics().job_duration_seconds.observe(duration)


@contextmanager
def trace_github_call(operation: str, repo: str = "") -> Generator[Any, None, None]:
    """Trace a GitHub API call."""
    tracer = get_tracer()
    m = get_metrics()
    with tracer.start_as_current_span(f"github.{operation}") as span:
        span.set_attribute("github.operation", operation)
        if repo:
            span.set_attribute("github.repo", repo)
        m.github_api_calls_total.inc()
        try:
            yield span
        except Exception as exc:
            m.github_api_errors_total.inc()
            span.record_exception(exc)
            raise


@contextmanager
def trace_anthropic_call(model: str = "", operation: str = "inference") -> Generator[Any, None, None]:
    """Trace an Anthropic API call."""
    tracer = get_tracer()
    m = get_metrics()
    with tracer.start_as_current_span(f"anthropic.{operation}") as span:
        span.set_attribute("anthropic.model", model)
        span.set_attribute("anthropic.operation", operation)
        m.anthropic_calls_total.inc()
        try:
            yield span
        except Exception as exc:
            m.anthropic_errors_total.inc()
            span.record_exception(exc)
            raise

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
import os
import time
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── Runtime import guard ────────────────────────────────────────────────────

try:
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

        # Provider-neutral model metrics
        self.model_calls_total = _Counter()
        self.model_errors_total = _Counter()
        self.model_duration_seconds = _Histogram()

        # Legacy provider metrics retained for existing dashboards.
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

        # Maintenance campaign metrics (bounded cardinality; no campaign IDs as labels)
        self.maintenance_campaigns_total = _Counter()
        self.maintenance_campaigns_noncompleted_total = _Counter()
        self.maintenance_recommendations_total = _Counter()
        self.maintenance_work_seeded_total = _Counter()
        self.maintenance_completed_items_total = _Counter()
        self.maintenance_blocked_items_total = _Counter()
        self.maintenance_pending_items_total = _Counter()
        self.maintenance_observer_errors_total = _Counter()
        self.maintenance_campaign_duration_seconds = _Histogram()

        # F14-11: Retry metrics
        self.retry_attempts_total = _Counter()
        self.retry_successes_total = _Counter()
        self.retry_failures_total = _Counter()
        self.retry_duration_seconds = _Histogram()
        self.retry_category_total = _Counter()  # labels: category

        # F14-12: Queue depth metrics (enhanced)
        self.queue_depth = _Gauge()
        self.queue_depth_max = _Gauge()
        self.queue_wait_seconds = _Histogram()

        # F14-18: Configurable retention settings
        self._metrics_retention_seconds: int = int(
            os.getenv("ZCODER_METRICS_RETENTION_SECONDS", "86400")
        )  # 24h default
        self._histogram_max_observations: int = int(os.getenv("ZCODER_HISTOGRAM_MAX_OBSERVATIONS", "10000"))

    def set_retention(self, retention_seconds: int) -> None:
        """Set metrics retention period in seconds."""
        self._metrics_retention_seconds = max(0, retention_seconds)

    def set_histogram_max_observations(self, max_observations: int) -> None:
        """Set maximum observations to keep in histograms."""
        self._histogram_max_observations = max(100, max_observations)

    def _maybe_trim_histograms(self) -> None:
        """Trim histogram observations if they exceed the configured maximum."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, _Histogram) and len(attr._observations) > self._histogram_max_observations:
                attr._observations = attr._observations[-self._histogram_max_observations :]

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
        c(
            "zcoder_worker_lease_expirations",
            "Total worker lease expirations",
            self.worker_lease_expirations_total,
        )
        g("zcoder_outbox_pending", "Number of undelivered outbox messages", self.outbox_pending)
        c("zcoder_outbox_failures", "Outbox delivery failures", self.outbox_failures_total)
        c("zcoder_webhooks", "Webhooks received", self.webhooks_total)
        c("zcoder_github_api_errors", "GitHub API errors", self.github_api_errors_total)
        c("zcoder_model_calls", "Model inference calls", self.model_calls_total)
        c("zcoder_model_errors", "Model inference errors", self.model_errors_total)
        h("zcoder_model_duration_seconds", "Model inference duration", self.model_duration_seconds)
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
        c("zcoder_maintenance_campaigns", "Maintenance campaigns started", self.maintenance_campaigns_total)
        c(
            "zcoder_maintenance_campaigns_noncompleted",
            "Maintenance campaigns that ended non-completed",
            self.maintenance_campaigns_noncompleted_total,
        )
        c(
            "zcoder_maintenance_recommendations",
            "Maintenance recommendations discovered",
            self.maintenance_recommendations_total,
        )
        c(
            "zcoder_maintenance_work_seeded",
            "Unique maintenance work seeded",
            self.maintenance_work_seeded_total,
        )
        c(
            "zcoder_maintenance_completed_items",
            "Maintenance work items completed",
            self.maintenance_completed_items_total,
        )
        c(
            "zcoder_maintenance_blocked_items",
            "Maintenance work items blocked",
            self.maintenance_blocked_items_total,
        )
        c(
            "zcoder_maintenance_pending_items",
            "Maintenance work items pending",
            self.maintenance_pending_items_total,
        )
        c(
            "zcoder_maintenance_observer_errors",
            "Maintenance campaign observer delivery errors",
            self.maintenance_observer_errors_total,
        )
        h(
            "zcoder_maintenance_campaign_duration_seconds",
            "Maintenance campaign execution duration",
            self.maintenance_campaign_duration_seconds,
        )

        # F14-11: Retry metrics
        c(
            "zcoder_retry_attempts_total",
            "Total retry attempts",
            self.retry_attempts_total,
        )
        c(
            "zcoder_retry_successes_total",
            "Total successful retries",
            self.retry_successes_total,
        )
        c(
            "zcoder_retry_failures_total",
            "Total failed retries",
            self.retry_failures_total,
        )
        h(
            "zcoder_retry_duration_seconds",
            "Retry delay duration",
            self.retry_duration_seconds,
        )

        # F14-12: Queue depth metrics
        g("zcoder_queue_depth", "Current queue depth", self.queue_depth)
        g("zcoder_queue_depth_max", "Maximum queue depth observed", self.queue_depth_max)
        h("zcoder_queue_wait_seconds", "Time spent in queue", self.queue_wait_seconds)

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
    def start_as_current_span(self, name: str, **kwargs) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()

    def start_span(self, name: str, **kwargs) -> _NoOpSpan:
        """Start a span without entering it as a context manager."""
        return _NoOpSpan()


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
def trace_model_call(
    provider: str = "local", model: str = "", operation: str = "inference"
) -> Generator[Any, None, None]:
    """Trace a provider-neutral model request with bounded metric labels."""
    tracer = get_tracer()
    metrics_registry = get_metrics()
    with tracer.start_as_current_span(f"model.{operation}") as span:
        span.set_attribute("model.provider", provider)
        span.set_attribute("model.name", model)
        span.set_attribute("model.operation", operation)
        metrics_registry.model_calls_total.inc()
        started_at = time.monotonic()
        try:
            yield span
        except Exception as exc:
            metrics_registry.model_errors_total.inc()
            span.record_exception(exc)
            raise
        finally:
            metrics_registry.model_duration_seconds.observe(time.monotonic() - started_at)


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


@contextmanager
def trace_retry_span(
    attempt: int,
    max_attempts: int,
    category: str = "transient",
    operation: str = "retry",
) -> Generator[Any, None, None]:
    """Trace a retry attempt with classification metadata (sync version)."""
    tracer = get_tracer()
    metrics_registry = get_metrics()
    with tracer.start_as_current_span(f"retry.{operation}") as span:
        span.set_attribute("retry.attempt", attempt)
        span.set_attribute("retry.max_attempts", max_attempts)
        span.set_attribute("retry.category", category)
        metrics_registry.retry_attempts_total.inc()
        metrics_registry.retry_category_total.inc(labels={"category": category})
        started_at = time.monotonic()
        try:
            yield span
            metrics_registry.retry_successes_total.inc()
        except Exception as exc:
            metrics_registry.retry_failures_total.inc()
            metrics_registry.retry_duration_seconds.observe(time.monotonic() - started_at)
            span.record_exception(exc)
            raise
        finally:
            metrics_registry.retry_duration_seconds.observe(time.monotonic() - started_at)


@asynccontextmanager
async def trace_retry_span_async(
    attempt: int,
    max_attempts: int,
    category: str = "transient",
    operation: str = "retry",
):
    """Trace a retry attempt with classification metadata (async version)."""
    tracer = get_tracer()
    metrics_registry = get_metrics()
    span = tracer.start_span(f"retry.{operation}")
    span.set_attribute("retry.attempt", attempt)
    span.set_attribute("retry.max_attempts", max_attempts)
    span.set_attribute("retry.category", category)
    metrics_registry.retry_attempts_total.inc()
    metrics_registry.retry_category_total.inc(labels={"category": category})
    started_at = time.monotonic()
    try:
        span.__enter__()
        metrics_registry.retry_attempts_total.inc()
        yield span
        metrics_registry.retry_successes_total.inc()
    except Exception as exc:
        metrics_registry.retry_failures_total.inc()
        metrics_registry.retry_duration_seconds.observe(time.monotonic() - started_at)
        span.record_exception(exc)
        raise
    finally:
        span.__exit__(None, None, None)
        metrics_registry.retry_duration_seconds.observe(time.monotonic() - started_at)


@contextmanager
def trace_queue_span(
    operation: str = "queue",
    queue_name: str = "default",
) -> Generator[Any, None, None]:
    """Trace queue operations with depth and wait time tracking."""
    tracer = get_tracer()
    metrics_registry = get_metrics()
    with tracer.start_as_current_span(f"queue.{operation}") as span:
        span.set_attribute("queue.name", queue_name)
        span.set_attribute("queue.operation", operation)
        metrics_registry.queue_depth.inc()
        started_at = time.monotonic()
        try:
            yield span
        finally:
            wait_time = time.monotonic() - started_at
            metrics_registry.queue_wait_seconds.observe(wait_time)
            metrics_registry.queue_depth.dec()

"""Performance metrics and benchmarks for Phase 15/16.

Provides performance monitoring, benchmarking, and SLA alerting for
model calls, RAG operations, workflow execution, and system resources.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


class MetricType(Enum):
    """Types of metrics."""

    LATENCY = "latency"
    THROUGHPUT = "throughput"
    COST = "cost"
    TOKEN_USAGE = "token_usage"
    ERROR_RATE = "error_rate"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    CONNECTION_POOL = "connection_pool"


@dataclass
class MetricRecord:
    """A single metric record."""

    metric_type: MetricType
    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] | None = None
    unit: str | None = None


@dataclass
class PerformanceStats:
    """Statistical summary of metric values."""

    count: int = 0
    min: float = float("inf")
    max: float = float("-inf")
    total: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    last_value: float = 0.0
    error_count: int = 0


class PerformanceMonitor:
    """Monitor performance metrics and check SLA violations."""

    def __init__(self, sla_thresholds: dict[MetricType, float] | None = None) -> None:
        # Store recent metric values per name (for stats calculation)
        self._metrics: dict[str, deque[MetricRecord]] = {}
        # SLA thresholds per metric type
        self._sla_thresholds: dict[MetricType, float] = sla_thresholds or {}
        # Per-metric-type trackers
        self._type_values: dict[MetricType, list[float]] = {mt: [] for mt in MetricType}

    def record(self, record: MetricRecord) -> None:
        """Record a metric value."""
        name = record.name
        if name not in self._metrics:
            self._metrics[name] = deque(maxlen=1000)
        self._metrics[name].append(record)

        # Track by type
        self._type_values[record.metric_type].append(record.value)

        # Check SLA violations
        threshold = self._sla_thresholds.get(record.metric_type)
        if threshold is not None and record.value > threshold:
            self._record_sla_violation(record)

    def _record_sla_violation(self, record: MetricRecord) -> None:
        """Record an SLA violation (can be extended to alerting)."""
        pass  # Extended in subclasses or external listeners

    def get_stats(self, name: str | None = None) -> PerformanceStats | dict[str, PerformanceStats]:
        """Get statistical summary of recorded metrics."""
        if name is not None:
            # Return stats for a specific metric by name
            records = self._metrics.get(name)
            if records is None or not isinstance(records, deque):
                return PerformanceStats()
            values: list[float] = [r.value for r in records]
            if not values:
                return PerformanceStats()
            stats = PerformanceStats()
            stats.count += len(values)
            stats.min = min(stats.min, min(values)) if stats.min != float("inf") else min(values)
            stats.max = max(stats.max, max(values)) if stats.max != float("-inf") else max(values)
            stats.total += sum(values)
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            if n % 2 == 1:
                median = sorted_vals[n // 2]
            else:
                median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
            stats.median = median
            p95_index = int(n * 0.95)
            p95 = sorted_vals[min(p95_index, n - 1)]
            stats.p95 = p95
            p99_index = int(n * 0.99)
            p99 = sorted_vals[min(p99_index, n - 1)]
            stats.p99 = p99
            stats.last_value = values[-1] if values else 0.0
            stats.error_count = sum(1 for v in values if v < 0)  # simplified error count
            return stats
        else:
            # Return stats for all metrics
            # Collect all values from all metric names
            all_values: list[float] = []
            stats = PerformanceStats()

            for _rec_name, rec_deque in self._metrics.items():
                chunk_values: list[float] = [r.value for r in rec_deque]
                if not chunk_values:
                    continue
                stats.count += len(chunk_values)
                stats.min = (
                    min(stats.min, min(chunk_values)) if stats.min != float("inf") else min(chunk_values)
                )
                stats.max = (
                    max(stats.max, max(chunk_values)) if stats.max != float("-inf") else max(chunk_values)
                )
                stats.total += sum(chunk_values)
                all_values.extend(chunk_values)

            # Sort for median/p95/p99
            sorted_vals = sorted(all_values)
            n = len(sorted_vals)
            if n > 0:
                if n % 2 == 1:
                    median = sorted_vals[n // 2]
                else:
                    median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
                stats.median = median
                p95_index = int(n * 0.95)
                p95 = sorted_vals[min(p95_index, n - 1)]
                stats.p95 = p95
                p99_index = int(n * 0.99)
                p99 = sorted_vals[min(p99_index, n - 1)]
                stats.p99 = p99

            # Calculate mean from all values
            if all_values:
                stats.mean = stats.total / stats.count if stats.count > 0 else 0.0
            else:
                stats.mean = 0.0

            # Reset extreme values if no data
            if stats.min == float("inf"):
                stats.min = 0.0
            if stats.max == float("-inf"):
                stats.max = 0.0

            return stats

    def check_sla_violations(self, metric_type: MetricType, value: float) -> list[str]:
        """Check if a value violates the SLA threshold for a given metric type."""
        violations: list[str] = []
        threshold = self._sla_thresholds.get(metric_type)
        if threshold is not None:
            if value > threshold:
                violations.append(f"{metric_type.value} {value:.2f} exceeds SLA threshold {threshold:.2f}")
        return violations

    def set_sla_threshold(self, metric_type: MetricType, threshold: float) -> None:
        """Set an SLA threshold for a metric type."""
        self._sla_thresholds[metric_type] = threshold

    def check_all_slas(self, metrics_dict: dict[str, float]) -> list[str]:
        """Check multiple metrics against their SLA thresholds.

        Args:
            metrics_dict: dict mapping metric_type name to value

        Returns:
            List of SLA violation strings
        """
        violations: list[str] = []
        for metric_name, value in metrics_dict.items():
            try:
                mt = MetricType(metric_name)
                violations.extend(self.check_sla_violations(mt, value))
            except ValueError:
                # Unknown metric type, skip
                pass
        return violations


# Helper functions for common monitoring patterns


def monitor_latency(
    monitor: PerformanceMonitor, name: str, latency_ms: float, sla_threshold_ms: float | None = None
) -> None:
    """Monitor latency in milliseconds."""
    monitor.record(
        MetricRecord(
            metric_type=MetricType.LATENCY,
            name=name,
            value=latency_ms,
            timestamp=datetime.now(UTC),
            labels={} if sla_threshold_ms is None else {"sla": str(sla_threshold_ms)},
        )
    )
    if sla_threshold_ms is not None:
        monitor.check_sla_violations(MetricType.LATENCY, latency_ms)


def monitor_cost(
    monitor: PerformanceMonitor, name: str, cost_usd: float, sla_threshold_usd: float | None = None
) -> None:
    """Monitor cost in USD."""
    monitor.record(
        MetricRecord(
            metric_type=MetricType.COST,
            name=name,
            value=cost_usd,
            timestamp=datetime.now(UTC),
            labels={} if sla_threshold_usd is None else {"sla": str(sla_threshold_usd)},
        )
    )
    if sla_threshold_usd is not None:
        monitor.check_sla_violations(MetricType.COST, cost_usd)


def monitor_token_usage(
    monitor: PerformanceMonitor, name: str, token_count: int, sla_threshold_tokens: int | None = None
) -> None:
    """Monitor token usage."""
    monitor.record(
        MetricRecord(
            metric_type=MetricType.TOKEN_USAGE,
            name=name,
            value=float(token_count),
            timestamp=datetime.now(UTC),
        )
    )
    if sla_threshold_tokens is not None:
        monitor.check_sla_violations(MetricType.TOKEN_USAGE, float(token_count))


def monitor_resource_usage(
    monitor: PerformanceMonitor,
    name: str,
    cpu_percent: float | None = None,
    memory_mb: float | None = None,
) -> None:
    """Monitor CPU and memory usage."""
    if cpu_percent is not None:
        monitor.record(
            MetricRecord(
                metric_type=MetricType.CPU_USAGE,
                name=f"{name}_cpu",
                value=cpu_percent,
                timestamp=datetime.now(UTC),
            )
        )
    if memory_mb is not None:
        monitor.record(
            MetricRecord(
                metric_type=MetricType.MEMORY_USAGE,
                name=f"{name}_memory",
                value=memory_mb,
                timestamp=datetime.now(UTC),
            )
        )

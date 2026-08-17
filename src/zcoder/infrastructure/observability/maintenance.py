"""Concrete OpenTelemetry adapter for maintenance campaign lifecycle events."""

from __future__ import annotations

from zcoder.infrastructure.observability.otel import ZCoderMetrics, get_metrics, get_tracer
from zcoder.services.maintenance_observability import (
    MaintenanceCampaignEvent,
    MaintenanceCampaignEventType,
)


class OtelMaintenanceCampaignEventSink:
    """Record maintenance campaign events in the bounded metric registry.

    Campaign IDs are attached only to traces, never metric labels. This preserves
    the repository's bounded-cardinality Prometheus policy.
    """

    def __init__(self, metrics: ZCoderMetrics | None = None) -> None:
        self.metrics = metrics or get_metrics()

    def emit(self, event: MaintenanceCampaignEvent) -> None:
        metrics = self.metrics
        tracer = get_tracer("zcoder.maintenance")
        with tracer.start_as_current_span(event.event_type.value) as span:
            span.set_attribute("maintenance.campaign_id", event.campaign_id)
            span.set_attribute("maintenance.event_type", event.event_type.value)
            if event.state:
                span.set_attribute("maintenance.state", event.state)
            span.set_attribute("maintenance.recommendations_discovered", event.recommendations_discovered)
            span.set_attribute("maintenance.work_seeded", event.work_seeded)
            span.set_attribute("maintenance.iterations", event.iterations)
            span.set_attribute("maintenance.completed_count", event.completed_count)
            span.set_attribute("maintenance.blocked_count", event.blocked_count)
            span.set_attribute("maintenance.pending_count", event.pending_count)
            span.set_attribute("maintenance.observer_error_count", event.observer_error_count)

            if event.event_type == MaintenanceCampaignEventType.STARTED:
                metrics.maintenance_campaigns_total.inc()
                return

            if event.event_type == MaintenanceCampaignEventType.RECOMMENDATIONS_DISCOVERED:
                metrics.maintenance_recommendations_total.inc(float(event.recommendations_discovered))
                metrics.maintenance_work_seeded_total.inc(float(event.work_seeded))
                return

            metrics.maintenance_campaign_duration_seconds.observe(event.duration_seconds)
            metrics.maintenance_completed_items_total.inc(float(event.completed_count))
            metrics.maintenance_blocked_items_total.inc(float(event.blocked_count))
            metrics.maintenance_pending_items_total.inc(float(event.pending_count))
            metrics.maintenance_observer_errors_total.inc(float(event.observer_error_count))
            if event.event_type == MaintenanceCampaignEventType.HALTED:
                metrics.maintenance_campaigns_noncompleted_total.inc()

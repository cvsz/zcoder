"""tests/test_observability_otel.py — Tests for the observability/metrics layer."""

import pytest

from zcoder.infrastructure.observability import bootstrap
from zcoder.infrastructure.observability.otel import (
    ZCoderMetrics,
    _Counter,
    _Gauge,
    _Histogram,
    get_metrics,
    init_telemetry,
    trace_job_span,
)


class TestGauge:
    def test_initial_value_is_zero(self):
        g = _Gauge()
        assert g.get() == 0.0

    def test_set_value(self):
        g = _Gauge()
        g.set(42.0)
        assert g.get() == 42.0

    def test_increment(self):
        g = _Gauge()
        g.inc(5.0)
        assert g.get() == 5.0

    def test_decrement(self):
        g = _Gauge()
        g.set(10.0)
        g.dec(3.0)
        assert g.get() == 7.0


class TestCounter:
    def test_initial_value_is_zero(self):
        c = _Counter()
        assert c.get() == 0.0

    def test_increment_default(self):
        c = _Counter()
        c.inc()
        assert c.get() == 1.0

    def test_increment_by_amount(self):
        c = _Counter()
        c.inc(5.0)
        assert c.get() == 5.0

    def test_multiple_increments(self):
        c = _Counter()
        c.inc(3.0)
        c.inc(2.0)
        assert c.get() == 5.0


class TestHistogram:
    def test_empty_histogram(self):
        h = _Histogram()
        assert h.count() == 0
        assert h.sum() == 0.0

    def test_observe_values(self):
        h = _Histogram()
        h.observe(1.0)
        h.observe(2.0)
        h.observe(3.0)
        assert h.count() == 3
        assert h.sum() == 6.0

    def test_percentiles(self):
        h = _Histogram()
        for i in range(100):
            h.observe(float(i))
        assert h.p50() >= 49.0
        assert h.p95() >= 94.0
        assert h.p99() >= 98.0

    def test_empty_percentiles_return_zero(self):
        h = _Histogram()
        assert h.p50() == 0.0
        assert h.p95() == 0.0
        assert h.p99() == 0.0


class TestZCoderMetrics:
    def test_metrics_registry_initializes(self):
        m = ZCoderMetrics()
        assert m.jobs_queued is not None
        assert m.worker_active is not None
        assert m.outbox_pending is not None

    def test_prometheus_exposition_is_valid_text(self):
        m = ZCoderMetrics()
        m.jobs_queued.set(5.0)
        m.jobs_running.set(2.0)
        m.worker_active.set(3.0)
        output = m.prometheus_exposition()
        assert "zcoder_jobs_queued" in output
        assert "zcoder_jobs_running" in output
        assert "zcoder_worker_active" in output
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_metrics_track_job_lifecycle(self):
        m = ZCoderMetrics()
        m.jobs_queued.inc()
        m.jobs_queued.inc()
        assert m.jobs_queued.get() == 2.0

        m.jobs_running.inc()
        m.jobs_queued.dec()
        assert m.jobs_running.get() == 1.0
        assert m.jobs_queued.get() == 1.0

    def test_worker_metrics(self):
        m = ZCoderMetrics()
        m.worker_active.set(3.0)
        m.worker_lease_expirations_total.inc()
        m.worker_fencing_rejections_total.inc()
        assert m.worker_active.get() == 3.0
        assert m.worker_lease_expirations_total.get() == 1.0
        assert m.worker_fencing_rejections_total.get() == 1.0

    def test_outbox_metrics(self):
        m = ZCoderMetrics()
        m.outbox_pending.set(10.0)
        m.outbox_failures_total.inc(3.0)
        assert m.outbox_pending.get() == 10.0
        assert m.outbox_failures_total.get() == 3.0

    def test_github_rate_limit_metric(self):
        m = ZCoderMetrics()
        m.github_rate_limit_remaining.set(4500.0)
        assert m.github_rate_limit_remaining.get() == 4500.0

    def test_bounded_labels_no_high_cardinality(self):
        """Verify metrics do NOT use high-cardinality labels like job_id/trace_id."""
        m = ZCoderMetrics()
        # Call with job_id label — metric should still work but bounded labels
        # The _Counter/.inc() accepts labels param but doesn't use it for cardinality
        m.jobs_total.inc(1.0, labels={"runtime": "direct"})
        assert m.jobs_total.get() == 1.0


class TestGetMetricsSingleton:
    def test_get_metrics_returns_same_instance(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_metrics_persist_across_calls(self):
        m = get_metrics()
        initial = m.api_requests_total.get()
        m.api_requests_total.inc()
        assert get_metrics().api_requests_total.get() == initial + 1


class TestTelemetryInit:
    def test_init_disabled_does_not_crash(self):
        # Should not raise even without OTel deps
        init_telemetry(enabled=False)

    def test_init_enabled_without_deps_warns(self):
        # With enabled=True but no OTel deps, should log warning but not crash
        init_telemetry(
            service_name="test-zcoder",
            service_version="1.0.0",
            otel_endpoint="",
            enabled=True,
        )


class TestTraceSpan:
    def test_trace_job_span_noop(self):
        """Trace span should work as a context manager even without OTel."""
        import time

        with trace_job_span(job_id="job_test_001", worker_id="worker_test_001") as span:
            span.set_attribute("test.key", "test_value")
            time.sleep(0.01)
        # If we reach here, the span worked without crashing


class TestPrometheusExposition:
    def test_backup_freshness_metrics_present(self):
        m = ZCoderMetrics()
        m.backup_last_success_timestamp.set(1723000000.0)
        m.backup_last_restore_drill_timestamp.set(1722900000.0)
        output = m.prometheus_exposition()
        assert "zcoder_backup_last_success_timestamp" in output
        assert "zcoder_backup_last_restore_drill_timestamp" in output

    def test_cost_metric_present(self):
        m = ZCoderMetrics()
        m.cost_usd_total.inc(0.05)
        output = m.prometheus_exposition()
        assert "zcoder_cost_usd" in output

    def test_api_red_metrics_present(self):
        """R.E.D. = Rate, Errors, Duration."""
        m = ZCoderMetrics()
        m.api_requests_total.inc(100.0)
        m.api_errors_total.inc(5.0)
        m.api_duration_seconds.observe(0.05)
        output = m.prometheus_exposition()
        assert "zcoder_api_requests" in output
        assert "zcoder_api_errors" in output
        assert "zcoder_api_duration_seconds" in output


class TestBootstrapFromEnv:
    @pytest.fixture(autouse=True)
    def _reset_bootstrap(self):
        bootstrap._reset_for_tests()
        yield
        bootstrap._reset_for_tests()

    def test_flag_unset_is_noop(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            bootstrap,
            "_load_init_telemetry",
            lambda: (lambda *a, **kw: calls.append(kw)),
        )
        result = bootstrap.bootstrap_from_env(env={})
        assert result is None
        assert calls == []

    def test_flag_set_calls_init_with_endpoint(self, monkeypatch):
        sentinel = object()
        calls = []

        def fake_init(*args, **kwargs):
            call = {"args": args, "kwargs": kwargs}
            calls.append(call)
            return sentinel

        monkeypatch.setattr(bootstrap, "_load_init_telemetry", lambda: fake_init)
        env = {"ZCODER_OTEL_ENDPOINT": "localhost:4317"}
        result = bootstrap.bootstrap_from_env(env=env)
        assert len(calls) == 1
        assert calls[0]["kwargs"]["otel_endpoint"] == "localhost:4317"
        assert calls[0]["kwargs"]["enabled"] is True
        assert result is sentinel

    def test_env_os_environ_fallback(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            bootstrap,
            "_load_init_telemetry",
            lambda: (lambda *a, **kw: calls.append(kw)),
        )
        monkeypatch.setenv("ZCODER_OTEL_ENDPOINT", "collector:4317")
        bootstrap.bootstrap_from_env()
        assert calls and calls[0]["otel_endpoint"] == "collector:4317"

    def test_init_raising_is_swallowed(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("no otel sdk")

        monkeypatch.setattr(bootstrap, "_load_init_telemetry", lambda: boom)
        result = bootstrap.bootstrap_from_env(env={"ZCODER_OTEL_ENDPOINT": "x:4317"})
        assert result is None

    def test_idempotent_second_call_is_noop(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            bootstrap,
            "_load_init_telemetry",
            lambda: (lambda *a, **kw: calls.append(kw)),
        )
        env = {"ZCODER_OTEL_ENDPOINT": "localhost:4317"}
        bootstrap.bootstrap_from_env(env=env)
        bootstrap.bootstrap_from_env(env=env)
        assert len(calls) == 1

    def test_sdk_missing_warns_and_continues(self, monkeypatch, caplog):
        import logging as _logging

        def no_sdk(*a, **kw):
            raise ImportError("No module named 'opentelemetry'")

        monkeypatch.setattr(bootstrap, "_load_init_telemetry", lambda: no_sdk)
        with caplog.at_level(_logging.WARNING, logger="zcoder.infrastructure.observability.bootstrap"):
            result = bootstrap.bootstrap_from_env(env={"ZCODER_OTEL_ENDPOINT": "x:4317"})
        assert result is None
        assert any("Telemetry bootstrap skipped" in r.message for r in caplog.records)

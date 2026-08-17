"""Regression coverage for maintenance CLI dependency composition."""

from zcoder.interfaces.cli import maintenance_campaign


def test_cli_composes_one_otel_sink_into_service_main(monkeypatch):
    sink = object()
    calls = []

    monkeypatch.setattr(
        maintenance_campaign,
        "OtelMaintenanceCampaignEventSink",
        lambda: sink,
    )

    def fake_service_main(argv, *, event_sink=None):
        calls.append((argv, event_sink))
        return 7

    monkeypatch.setattr(maintenance_campaign, "run_maintenance_campaign_cli", fake_service_main)

    argv = ["--repository", "/tmp/repo"]
    result = maintenance_campaign.main(argv)

    assert result == 7
    assert calls == [(argv, sink)]

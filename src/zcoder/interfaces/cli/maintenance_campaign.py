"""CLI composition root for one observable bounded maintenance campaign."""

from __future__ import annotations

from collections.abc import Sequence

from zcoder.infrastructure.observability.maintenance import OtelMaintenanceCampaignEventSink
from zcoder.services.maintenance_campaign import main as run_maintenance_campaign_cli


def main(argv: Sequence[str] | None = None) -> int:
    """Compose infrastructure observability around the service-level CLI."""

    try:
        from zcoder.infrastructure.observability.bootstrap import bootstrap_from_env

        bootstrap_from_env()
    except Exception:
        pass

    return run_maintenance_campaign_cli(
        argv,
        event_sink=OtelMaintenanceCampaignEventSink(),
    )


if __name__ == "__main__":
    raise SystemExit(main())

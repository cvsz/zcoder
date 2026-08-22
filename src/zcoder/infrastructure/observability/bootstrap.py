"""bootstrap.py — OTel entrypoint wiring behind the ZCODER_OTEL_ENDPOINT env flag.

Zero behavior change when the flag is unset; best-effort initialization when
set (never raises). Safe to call multiple times — only the first call acts.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_OTEL_ENDPOINT_ENV = "ZCODER_OTEL_ENDPOINT"

_bootstrapped = False


def _reset_for_tests() -> None:
    global _bootstrapped
    _bootstrapped = False


def _load_init_telemetry() -> Any:
    """Import and return ``init_telemetry``; raises if otel.py is unavailable."""
    from zcoder.infrastructure.observability.otel import init_telemetry

    return init_telemetry


def bootstrap_from_env(env: dict[str, str] | None = None) -> Any:
    """Initialize OpenTelemetry from the environment, best-effort and idempotent.

    Returns whatever ``init_telemetry`` returns when the endpoint flag is set,
    otherwise ``None``. Never raises.
    """
    global _bootstrapped

    source = env if env is not None else os.environ
    endpoint = source.get(_OTEL_ENDPOINT_ENV)

    if not endpoint:
        logger.debug("%s not set; telemetry stays disabled", _OTEL_ENDPOINT_ENV)
        return None

    if _bootstrapped:
        return None

    try:
        result = _load_init_telemetry()(
            service_name="zcoder",
            otel_endpoint=endpoint,
            enabled=True,
        )
        _bootstrapped = True
        logger.info("OpenTelemetry bootstrapped from %s", _OTEL_ENDPOINT_ENV)
        return result
    except Exception as exc:
        logger.warning("Telemetry bootstrap skipped (%s); continuing without it", exc)
        return None

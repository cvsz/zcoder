"""Network bind policies for unauthenticated local development services."""

from __future__ import annotations

import ipaddress


def validate_worker_token(token: str | None) -> None:
    """Validate optional bearer credentials without including them in errors."""
    if token is not None and (
        not isinstance(token, str)
        or not 32 <= len(token) <= 512
        or any(not 33 <= ord(char) <= 126 for char in token)
    ):
        raise ValueError("worker token must contain 32 to 512 printable ASCII characters without spaces")


def require_loopback_host(host: str, service_name: str) -> None:
    """Reject network-wide binds until the service has authenticated access control."""
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
        loopback = address.version == 4 and address.is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ValueError(f"{service_name} currently binds to loopback only")

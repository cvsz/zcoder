"""Security boundary for caller-supplied outbound HTTP(S) URLs.

This module is intentionally separate from ``resilience.safe_urlopen`` because
that helper is also used by explicitly local model gateways.  Callers handling
untrusted external URLs should use this stricter boundary instead.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from typing import Any


def _require_global_address(address: str, *, hostname: str) -> None:
    ip = ipaddress.ip_address(address)
    if not ip.is_global:
        raise ValueError(f"Outbound URL host '{hostname}' resolves to a non-public address")


def validate_external_http_url(url: str) -> None:
    """Fail closed unless ``url`` resolves exclusively to public HTTP(S) IPs.

    The check rejects local/private/link-local/reserved/multicast/unspecified
    address space for both IP literals and DNS names.  Userinfo is rejected to
    avoid hostname-confusion forms such as ``public.example@127.0.0.1``.
    """

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for external request: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise ValueError("External URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("External URL must not contain userinfo")

    hostname = parsed.hostname.rstrip(".")
    if not hostname:
        raise ValueError("External URL must include a hostname")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        _require_global_address(str(literal), hostname=hostname)
        return

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"External URL hostname could not be resolved: {hostname}") from exc
    if not answers:
        raise ValueError(f"External URL hostname could not be resolved: {hostname}")

    resolved: set[str] = set()
    for answer in answers:
        sockaddr: Any = answer[4]
        if sockaddr:
            resolved.add(str(sockaddr[0]))
    if not resolved:
        raise ValueError(f"External URL hostname could not be resolved: {hostname}")
    for address in resolved:
        _require_global_address(address, hostname=hostname)


class _ExternalRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target before urllib follows it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_external_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_external_urlopen(req: urllib.request.Request, timeout: float):
    """Open one caller-supplied external URL with SSRF-aware validation.

    Initial and redirect targets are checked.  This is a userspace guard; a
    production deployment should still enforce egress policy at the network
    boundary to protect against DNS rebinding between validation and connect.
    """

    validate_external_http_url(req.full_url)
    opener = urllib.request.build_opener(_ExternalRedirectHandler())
    return opener.open(req, timeout=timeout)

"""Loopback-only transport guard for the desktop inference client."""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from typing import Any
from urllib.parse import urlsplit


def validate_local_base_url(value: str) -> str:
    """Require a valid HTTP(S) URL that resolves exclusively to loopback."""
    if not value or value != value.strip():
        raise ValueError("ZCODER_BASE_URL must be a non-empty loopback HTTP(S) URL")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("ZCODER_BASE_URL must be a valid loopback HTTP(S) URL") from exc

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "ZCODER_BASE_URL must use HTTP(S), target loopback, and omit credentials, query, and fragment"
        )

    if hostname == "localhost":
        try:
            answers = socket.getaddrinfo(
                hostname,
                port if port is not None else (443 if scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ValueError("ZCODER_BASE_URL localhost did not resolve to loopback") from exc

        addresses = {
            ipaddress.ip_address(str(answer[4][0]))
            for answer in answers
            if answer[4]
        }
        if not addresses or any(not address.is_loopback for address in addresses):
            raise ValueError("ZCODER_BASE_URL localhost must resolve exclusively to loopback")
    else:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise ValueError("ZCODER_BASE_URL must target a loopback IP or localhost") from exc
        if not address.is_loopback:
            raise ValueError("ZCODER_BASE_URL must target a loopback IP or localhost")

    return value.rstrip("/")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent a local inference endpoint from redirecting requests off-host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_local_request(request: urllib.request.Request, *, timeout: float) -> Any:
    """Open a validated loopback request without proxies or HTTP redirects."""
    validate_local_base_url(request.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    return opener.open(request, timeout=timeout)

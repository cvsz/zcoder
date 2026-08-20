"""Security boundary for caller-supplied outbound HTTP(S) URLs.

This module is intentionally separate from ``resilience.safe_urlopen`` because
that helper is also used by explicitly local model gateways. Callers handling
untrusted external URLs should use this stricter boundary instead.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.parse
import urllib.request
from typing import Any


def _require_global_address(address: str, *, hostname: str) -> None:
    ip = ipaddress.ip_address(address)
    if not ip.is_global:
        raise ValueError(f"Outbound URL host '{hostname}' resolves to a non-public address")


def _resolve_external_http_target(url: str) -> tuple[str, int, tuple[str, ...]]:
    """Validate an external HTTP(S) URL and return its approved connection target."""

    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for external request: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise ValueError("External URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("External URL must not contain userinfo")

    hostname = parsed.hostname.rstrip(".")
    if not hostname:
        raise ValueError("External URL must include a hostname")

    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        address = str(literal)
        _require_global_address(address, hostname=hostname)
        return hostname, port, (address,)

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

    return hostname, port, tuple(sorted(resolved))


def validate_external_http_url(url: str) -> None:
    """Fail closed unless ``url`` resolves exclusively to public HTTP(S) IPs.

    The check rejects local/private/link-local/reserved/multicast/unspecified
    address space for both IP literals and DNS names. Userinfo is rejected to
    avoid hostname-confusion forms such as ``public.example@127.0.0.1``.
    """

    _resolve_external_http_target(url)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that dials the already-validated IP, not DNS again."""

    def __init__(self, host: str, *, pinned_address: str, **kwargs: Any) -> None:
        self._pinned_address = pinned_address
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an approved IP while preserving hostname TLS."""

    def __init__(self, host: str, *, pinned_address: str, **kwargs: Any) -> None:
        self._pinned_address = pinned_address
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        server_hostname = self.host
        if self._tunnel_host:
            self._tunnel()
            server_hostname = self._tunnel_host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    """Resolve, validate, and pin each plain-HTTP request immediately before connect."""

    def http_open(self, req):  # type: ignore[no-untyped-def]
        hostname, port, addresses = _resolve_external_http_target(req.full_url)
        pinned_address = addresses[0]

        def connection_factory(_host, **kwargs):  # type: ignore[no-untyped-def]
            return _PinnedHTTPConnection(
                hostname,
                pinned_address=pinned_address,
                port=port,
                **kwargs,
            )

        return self.do_open(connection_factory, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """Resolve, validate, and pin each HTTPS request while retaining TLS SNI."""

    def https_open(self, req):  # type: ignore[no-untyped-def]
        hostname, port, addresses = _resolve_external_http_target(req.full_url)
        pinned_address = addresses[0]

        def connection_factory(_host, **kwargs):  # type: ignore[no-untyped-def]
            return _PinnedHTTPSConnection(
                hostname,
                pinned_address=pinned_address,
                port=port,
                **kwargs,
            )

        return self.do_open(
            connection_factory,
            req,
            context=self._context,
            check_hostname=self._check_hostname,
        )


class _ExternalRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target before urllib follows it."""

    max_repeats = 3
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_external_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_external_urlopen(req: urllib.request.Request, timeout: float):
    """Open one caller-supplied external URL with SSRF-aware validation.

    Initial and redirect targets are checked. The connection is pinned to an
    address from the validated DNS answer so hostname rebinding cannot swap in
    a private destination between validation and connect. HTTPS still uses the
    original hostname for TLS SNI/certificate verification. Environment proxy
    discovery is disabled so inherited proxy settings cannot bypass policy.
    """

    validate_external_http_url(req.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
        _ExternalRedirectHandler(),
    )
    return opener.open(req, timeout=timeout)

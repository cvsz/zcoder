"""Security regression for DeepResearchAgent caller-supplied source URLs (SEC-001).

SEC-001: Deep Research SSRF
- Untrusted source: model-supplied or user-supplied `source_urls` in `DeepResearchAgent.run()`
- Privileged sink: outbound HTTP(S) request via `urllib.request.urlopen` in `_fetch_retrying`
- Control: `safe_external_urlopen()` enforces:
  1. Scheme allowlist (HTTP/HTTPS only)
  2. Hostname required, no userinfo
  3. IP literal → global address check (rejects loopback, private, link-local, multicast, reserved)
  4. Hostname → DNS resolution → ALL resolved IPs must be global
  5. Redirect re-validation via `_ExternalRedirectHandler`
  6. Proxy discovery disabled (`ProxyHandler({})`) to prevent proxy-based SSRF
  7. Timeout enforcement (15s)

Evidence tier: UNIT_TESTED (these tests) + SOURCE_VERIFIED (code trace below)
"""

import socket

import pytest

from zcoder.agent.rag.research import DeepResearchAgent
from zcoder.core.outbound_security import validate_external_http_url


class TestSEC001DeepResearchSSRF:
    """SEC-001 revalidation: Deep Research SSRF protection."""

    # =========================================================================
    # Trace: untrusted source → DeepResearchAgent.gather() → _fetch() →
    # _fetch_retrying() → safe_external_urlopen() → urllib.urlopen (sink)
    # =========================================================================

    def test_source_sink_trace_loopback_ipv4_literal(self):
        """Loopback IPv4 literal rejected at validation boundary."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("http://127.0.0.1:8080/private")

    def test_source_sink_trace_loopback_ipv6_literal(self):
        """Loopback IPv6 literal rejected at validation boundary."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("http://[::1]/private")

    def test_source_sink_trace_ipv4_mapped_ipv6_loopback(self):
        """IPv4-mapped IPv6 loopback rejected."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("http://[::ffff:127.0.0.1]/private")

    def test_source_sink_trace_cloud_metadata_endpoint(self):
        """Cloud metadata endpoint (169.254.169.254) rejected as link-local."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("http://169.254.169.254/latest/meta-data/")

    def test_source_sink_trace_private_rfc1918_dns(self, monkeypatch):
        """Private RFC1918 address from DNS rejected."""

        def fake_getaddrinfo(host, port, *, type):
            assert host == "internal.example"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("https://internal.example/data")

    def test_source_sink_trace_private_rfc1918_class_b(self, monkeypatch):
        """Private 172.16-31.x range rejected."""

        def fake_getaddrinfo(host, port, *, type):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("https://private-b.example/data")

    def test_source_sink_trace_private_rfc1918_class_c(self, monkeypatch):
        """Private 192.168.x range rejected."""

        def fake_getaddrinfo(host, port, *, type):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("https://private-c.example/data")

    def test_source_sink_trace_link_local_dns(self, monkeypatch):
        """Link-local 169.254.x range from DNS rejected."""

        def fake_getaddrinfo(host, port, *, type):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.10.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("https://linklocal.example/data")

    def test_source_sink_trace_mixed_public_private_dns(self, monkeypatch):
        """Mixed public/private DNS resolution fails closed (all IPs must be global)."""

        def fake_getaddrinfo(host, port, *, type):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),  # public
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),  # private
            ]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="non-public"):
            agent._fetch_retrying("https://mixed.example/data")

    def test_source_sink_trace_userinfo_confusion(self):
        """Userinfo hostname confusion (public@127.0.0.1) rejected."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="userinfo"):
            agent._fetch_retrying("https://public.example@127.0.0.1/internal")

    def test_source_sink_trace_missing_hostname(self):
        """URL without hostname rejected."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="hostname"):
            agent._fetch_retrying("http:///path")

    def test_source_sink_trace_unsupported_scheme(self):
        """Non-HTTP(S) scheme rejected."""
        agent = DeepResearchAgent.__new__(DeepResearchAgent)
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            agent._fetch_retrying("file:///etc/passwd")

    # =========================================================================
    # Transport-level guards (safe_external_urlopen)
    # =========================================================================

    def test_transport_proxy_disabled(self, monkeypatch):
        """Environment proxies are disabled; explicit empty ProxyHandler used."""
        import urllib.request

        import zcoder.core.outbound_security as outbound_security

        captured_handlers: list = []

        class FakeOpener:
            def open(self, req, timeout):
                assert req.full_url == "https://public.example/data"
                assert timeout == 3

                # Return a mock response
                class MockResp:
                    def read(self):
                        return b"ok"

                    @property
                    def headers(self):
                        return {}

                return MockResp()

        def fake_build_opener(*handlers):
            captured_handlers.extend(handlers)
            return FakeOpener()

        def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setenv("HTTPS_PROXY", "http://evil-proxy:8888")
        monkeypatch.setattr(outbound_security, "validate_external_http_url", lambda _url: None)
        monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)

        req = urllib.request.Request("https://public.example/data")
        outbound_security.safe_external_urlopen(req, timeout=3)

        proxy_handlers = [h for h in captured_handlers if isinstance(h, urllib.request.ProxyHandler)]
        assert len(proxy_handlers) == 1
        assert proxy_handlers[0].proxies == {}

    def test_transport_redirect_revalidation(self):
        """Redirect target re-validated via _ExternalRedirectHandler."""
        from zcoder.core.outbound_security import _ExternalRedirectHandler

        handler = _ExternalRedirectHandler()
        req = __import__("urllib.request").request.Request("https://public.example/start")

        with pytest.raises(ValueError, match="non-public"):
            handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/internal")

    def test_transport_redirect_to_public_allowed(self):
        """Redirect to public URL allowed."""
        from zcoder.core.outbound_security import _ExternalRedirectHandler

        handler = _ExternalRedirectHandler()
        req = __import__("urllib.request").request.Request("https://public.example/start")

        # Should not raise for public redirect
        result = handler.redirect_request(req, None, 302, "Found", {}, "https://example.com/new")
        assert result is not None


class TestSEC001ValidationBoundary:
    """Direct validation boundary tests (source: validate_external_http_url)."""

    def test_validation_rejects_loopback_ipv4(self):
        with pytest.raises(ValueError, match="non-public"):
            validate_external_http_url("http://127.0.0.1:8080/internal")

    def test_validation_rejects_loopback_ipv6(self):
        with pytest.raises(ValueError, match="non-public"):
            validate_external_http_url("http://[::1]/internal")

    def test_validation_rejects_ipv4_mapped_ipv6(self):
        with pytest.raises(ValueError, match="non-public"):
            validate_external_http_url("http://[::ffff:127.0.0.1]/internal")

    def test_validation_rejects_userinfo_confusion(self):
        with pytest.raises(ValueError, match="userinfo"):
            validate_external_http_url("https://public.example@127.0.0.1/internal")

    def test_validation_rejects_private_dns(self, monkeypatch):
        def fake_getaddrinfo(host, port, *, type):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(ValueError, match="non-public"):
            validate_external_http_url("https://private.example/data")

    def test_validation_rejects_mixed_dns(self, monkeypatch):
        def fake_getaddrinfo(host, port, *, type):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", port)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(ValueError, match="non-public"):
            validate_external_http_url("https://mixed.example/data")

    def test_validation_accepts_public_dns(self, monkeypatch):
        def fake_getaddrinfo(host, port, *, type):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        assert validate_external_http_url("https://public.example/data") is None

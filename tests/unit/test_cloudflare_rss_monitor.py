"""Regression tests for scripts/cloudflare_rss_monitor.py fetch_feed redirect hardening (F-01).

F-01: Bandit B310 Medium — urllib.request.urlopen follows HTTP redirects, so a
user/model-controlled https feed URL could redirect to a non-https scheme
(file:///ftp://) after the initial scheme check. After the fix, fetch_feed
re-validates resp.geturl() scheme remains https and rejects the feed.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cloudflare_rss_monitor.py"


def _load_module():
    spec = spec_from_file_location("cloudflare_rss_monitor_test", SCRIPT)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, final_url: str, body: bytes = b"<rss><channel><item><t>x</t></item></channel></rss>"):
        self._final_url = final_url
        self._body = body

    def geturl(self) -> str:
        return self._final_url

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _TrackingResponse(_FakeResponse):
    """Response that records whether read() was invoked."""

    def __init__(self, final_url: str, body: bytes = b"<rss><channel></channel></rss>"):
        super().__init__(final_url, body)
        self.read_called = False

    def read(self) -> bytes:
        self.read_called = True
        return super().read()


def test_fetch_feed_rejects_https_to_http_redirect():
    """F-01: an https feed redirecting to http must be rejected (no scheme escape)."""
    mod = _load_module()
    with patch.object(mod, "urlopen", return_value=_FakeResponse("http://example.com/feed.xml")):
        assert mod.fetch_feed("https://example.com/feed.xml") is None


def test_fetch_feed_rejects_https_to_file_redirect():
    """F-01: an https feed redirecting to file:// must be rejected (B310 urlopen)."""
    mod = _load_module()
    with patch.object(mod, "urlopen", return_value=_FakeResponse("file:///etc/passwd")):
        assert mod.fetch_feed("https://example.com/feed.xml") is None


def test_fetch_feed_accepts_stays_https():
    """F-01: an https feed that stays https is parsed normally."""
    mod = _load_module()
    with patch.object(mod, "urlopen", return_value=_FakeResponse("https://example.com/feed.xml")):
        result = mod.fetch_feed("https://example.com/feed.xml")
    assert result is not None


def test_fetch_feed_rejects_https_to_ftp_redirect():
    """F-01: an https feed redirecting to ftp:// must be rejected (scheme escape)."""
    mod = _load_module()
    with patch.object(mod, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _TrackingResponse("ftp://example.com/feed.xml")
        assert mod.fetch_feed("https://example.com/feed.xml") is None
    # Validation occurs before reading response bytes; read() must not run.
    assert mock_urlopen.return_value.read_called is False


def test_fetch_feed_rejects_initial_non_https_schemes():
    """F-01: http://, ftp://, file:// and scheme-less URLs are rejected up front."""
    mod = _load_module()
    for url in (
        "http://example.com/feed.xml",
        "ftp://example.com/feed.xml",
        "file:///etc/passwd",
        "",
        "not-a-url",
    ):
        assert mod.fetch_feed(url) is None


def test_fetch_feed_read_only_after_https_validation():
    """F-01: resp.read() must not run when the final URL leaves https."""
    mod = _load_module()
    with patch.object(mod, "urlopen") as mock_urlopen:
        mock_urlopen.return_value = _TrackingResponse("http://example.com/feed.xml")
        assert mod.fetch_feed("https://example.com/feed.xml") is None
    assert mock_urlopen.return_value.read_called is False


def test_fetch_feed_network_error_is_handled():
    """F-01: urlopen network failures (URLError) yield None instead of crashing."""
    mod = _load_module()
    with patch.object(mod, "urlopen", side_effect=URLError("network down")):
        assert mod.fetch_feed("https://example.com/feed.xml") is None


def test_fetch_feed_timeout_is_handled():
    """F-01: urlopen timeouts (TimeoutError/OSError) yield None instead of crashing."""
    mod = _load_module()
    with patch.object(mod, "urlopen", side_effect=TimeoutError("timed out")):
        assert mod.fetch_feed("https://example.com/feed.xml") is None


def test_fetch_feed_redirect_loop_is_handled():
    """F-01: a redirect loop surfacing as urlopen failure is handled gracefully."""
    mod = _load_module()
    # urllib exhausts its redirect budget and raises URLError; fetch_feed must not leak it.
    with patch.object(mod, "urlopen", side_effect=URLError("too many redirects")):
        assert mod.fetch_feed("https://example.com/feed.xml") is None

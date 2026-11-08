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

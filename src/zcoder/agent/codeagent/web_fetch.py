"""Web fetch tool — mirrors deepseek-harness @deepseek-ai/dsh-tool-web fetch.

Provides model-facing `web_fetch` tool that fetches a URL and returns its
content as text. Follows deepseek-harness patterns:
- URL validation and loopback protection
- Content-type checking
- Text extraction from HTML
- Size limits
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

# Maximum bytes to fetch from a URL
WEB_FETCH_MAX_BYTES = 1_000_000  # 1 MB

# Maximum number of redirects to follow
WEB_FETCH_MAX_REDIRECTS = 5

# Allowed content types for text extraction
WEB_FETCH_TEXT_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/markdown",
        "application/xhtml+xml",
    }
)


@dataclass
class WebFetchResult:
    """Result of fetching a URL."""

    url: str
    title: str | None
    content: str
    content_type: str | None
    status_code: int
    size_bytes: int


class WebFetchArgsError(Exception):
    """Validation error for web_fetch arguments."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_fetch_args(args: dict[str, Any]) -> str:
    """Validate web_fetch arguments. Returns the URL string."""
    url = args.get("url")
    if not url or not isinstance(url, str):
        raise WebFetchArgsError("url is required and must be a string")

    url = url.strip()
    if not url:
        raise WebFetchArgsError("url must not be empty")

    # Validate URL scheme
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebFetchArgsError(f"url scheme must be http or https, got {parsed.scheme!r}")

    # Block loopback/private addresses for security
    hostname = parsed.hostname or ""
    if hostname in ("127.0.0.1", "::1", "localhost"):
        raise WebFetchArgsError("loopback addresses are not allowed")
    if hostname.startswith("10.") or hostname.startswith("172.16.") or hostname.startswith("192.168."):
        raise WebFetchArgsError("private network addresses are not allowed")

    return url


def extract_title(html_content: str) -> str | None:
    """Extract page title from HTML content."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.DOTALL | re.IGNORECASE)
    if match:
        title = re.sub(r"<[^>]+>", "", match.group(1))
        return html.unescape(title).strip() or None
    return None


def extract_text(html_content: str) -> str:
    """Extract readable text from HTML content."""
    # Remove script and style elements
    text = re.sub(r"<script(?:\s+[^>]*)?>.*?</script\s*>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style(?:\s+[^>]*)?>.*?</style\s*>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode HTML entities
    text = html.unescape(text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def fetch_url(url: str, max_bytes: int = WEB_FETCH_MAX_BYTES) -> WebFetchResult:
    """Fetch a URL and return its content as text.

    Mirrors deepseek-harness web fetch provider: fetches URL with redirects,
    validates content type, extracts text from HTML, enforces size limits.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        },
    )

    redirects = 0
    current_url = url

    while redirects < WEB_FETCH_MAX_REDIRECTS:
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
                content_type = resp.headers.get("Content-Type", "")
                # Extract media type without charset
                media_type = content_type.split(";")[0].strip().lower() if content_type else ""
                status_code = resp.status

                # Read content with size limit
                raw = resp.read(max_bytes + 1)
                size_bytes = len(raw)

                if size_bytes > max_bytes:
                    raw = raw[:max_bytes]

                # Decode content
                charset = "utf-8"
                if "charset=" in content_type:
                    try:
                        charset = content_type.split("charset=")[1].split(";")[0].strip().strip("\"'")
                    except Exception:
                        pass  # Default charset remains utf-8

                try:
                    content = raw.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    content = raw.decode("utf-8", errors="replace")

                # Extract title and text for HTML
                title = None
                if media_type in WEB_FETCH_TEXT_TYPES or media_type == "text/html":
                    title = extract_title(content)
                    text_content = extract_text(content)
                else:
                    text_content = content

                # Truncate if too large
                if len(text_content) > max_bytes:
                    text_content = text_content[:max_bytes]

                return WebFetchResult(
                    url=current_url,
                    title=title,
                    content=text_content,
                    content_type=media_type or None,
                    status_code=status_code,
                    size_bytes=size_bytes,
                )

        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and redirects < WEB_FETCH_MAX_REDIRECTS:
                redirect_url = exc.headers.get("Location")
                if redirect_url:
                    current_url = urllib.parse.urljoin(current_url, redirect_url)
                    req = urllib.request.Request(
                        current_url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/120.0.0.0 Safari/537.36"
                            ),
                        },
                    )
                    redirects += 1
                    continue
            raise
        except (urllib.error.URLError, OSError) as exc:
            raise WebFetchArgsError(f"Failed to fetch {url}: {exc}") from exc

    raise WebFetchArgsError(f"Too many redirects for {url}")


__all__ = [
    "WEB_FETCH_MAX_BYTES",
    "WEB_FETCH_MAX_REDIRECTS",
    "WebFetchResult",
    "WebFetchArgsError",
    "parse_fetch_args",
    "extract_title",
    "extract_text",
    "fetch_url",
]

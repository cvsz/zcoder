"""Web search tool — mirrors deepseek-harness @deepseek-ai/dsh-tool-web.

Provides model-facing `web_search` tool that discovers current information on
the web through DuckDuckGo HTML scraping. Follows deepseek-harness patterns:
- Schema validation with query count bounds
- Source projection with summaries
- Replayable meta payload for session log persistence
- Trust/external content notices
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

# Maximum number of search results returned per call
WEB_SEARCH_MAX_RESULTS = 10

# Maximum number of concurrent queries in one tool call
WEB_SEARCH_MAX_QUERIES = 10

# Default cap on one source summary, in characters
WEB_SEARCH_SUMMARY_MAX_CHARS = 800

SUMMARY_ELLIPSIS = '…'

EXTERNAL_WEB_CONTENT_NOTICE = (
    'External web content may be incomplete, outdated, or inaccurate. '
    'Verify important claims from primary sources.'
)


@dataclass
class WebSearchSource:
    """One search result source."""

    url: str
    title: str | None = None
    snippet: str | None = None
    published_at: str | None = None
    summary: str | None = None


@dataclass
class WebSearchResult:
    """Search result from the web search provider."""

    sources: list[WebSearchSource]
    content: str | None = None
    truncated: bool = False


@dataclass
class WebSearchMeta:
    """Replayable meta payload for session log persistence."""

    sources: list[dict[str, Any]]
    truncated: bool
    answer: str | None = None


class WebSearchArgsError(Exception):
    """Validation error for web_search arguments."""

    def __init__(self, messages: list[str]):
        super().__init__('; '.join(messages))
        self.messages = messages


def parse_search_args(args: dict[str, Any], max_queries: int = WEB_SEARCH_MAX_QUERIES) -> list[str]:
    """Validate web_search arguments.

    Mirrors deepseek-harness parseSearchArgs: queries must be non-empty,
    contain only non-blank strings, and fit within max_queries bound.
    Exact duplicate strings are collapsed after the bound check.
    """
    queries = args.get('queries', [])
    if not isinstance(queries, list):
        raise WebSearchArgsError(['queries must be a list'])
    if len(queries) == 0:
        raise WebSearchArgsError(['queries must contain at least one query'])
    if len(queries) > max_queries:
        noun = 'query' if max_queries == 1 else 'queries'
        raise WebSearchArgsError([f'queries must contain at most {max_queries} {noun}'])
    if any(not isinstance(q, str) or not q.strip() for q in queries):
        raise WebSearchArgsError(['each query must be a non-empty string'])
    # Collapse exact duplicates, preserving first-occurrence order
    seen: set[str] = set()
    result: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            result.append(q)
    return result


def source_label(url: str, title: str | None) -> str:
    """Display label for a source: its title, else its hostname."""
    if title and title.strip():
        return title
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname or url
    except Exception:
        return url


def truncate_without_splitting_surrogate_pair(text: str, max_chars: int) -> str:
    """Truncate text without splitting UTF-16 surrogate pairs."""
    if len(text) <= max_chars:
        return text
    # Simple approach: truncate at max_chars, adjusting for surrogate pairs
    encoded = text.encode('utf-16-le')
    if len(encoded) <= max_chars * 2:
        return text
    truncated = encoded[:max_chars * 2]
    # Ensure we don't split a surrogate pair (high surrogate 0xD800-0xDBFF,
    # low surrogate 0xDC00-0xDFFF)
    if len(truncated) >= 2:
        last_word = int.from_bytes(truncated[-2:], 'little')
        if 0xD800 <= last_word <= 0xDBFF:
            truncated = truncated[:-2]
    return truncated.decode('utf-16-le', errors='ignore')


def project_source(source: WebSearchSource) -> dict[str, Any]:
    """Project one source into display fields dict."""
    result: dict[str, Any] = {'url': source.url}
    if source.title is not None:
        result['title'] = source.title
    if source.snippet is not None:
        result['snippet'] = source.snippet
    if source.published_at is not None:
        result['published_at'] = source.published_at
    return result


def model_source(source: WebSearchSource, summary_max_chars: int = WEB_SEARCH_SUMMARY_MAX_CHARS) -> dict[str, Any]:
    """Project one source into model-facing output with bounded summary."""
    result = project_source(source)
    if source.summary:
        summary = re.sub(r'\s+', ' ', source.summary).strip()
        if summary:
            if len(summary) <= summary_max_chars:
                result['summary'] = summary
            else:
                bounded = truncate_without_splitting_surrogate_pair(
                    summary, summary_max_chars - len(SUMMARY_ELLIPSIS)
                )
                result['summary'] = bounded + SUMMARY_ELLIPSIS
    return result


def search_meta_from_value(result: WebSearchResult) -> dict[str, Any]:
    """Project WebSearchResult into replayable meta payload."""
    meta: dict[str, Any] = {
        'sources': [project_source(s) for s in result.sources],
        'truncated': result.truncated,
    }
    if result.content is not None:
        meta['answer'] = result.content
    return meta


def format_search_output(result: WebSearchResult) -> str:
    """Format search result as model-facing text block.

    Mirrors deepseek-harness formatSearchOutput: provider answer, markdown
    source list with summaries/snippets and dates, truncation note, and
    citation instruction.
    """
    parts: list[str] = [EXTERNAL_WEB_CONTENT_NOTICE]
    if result.content and result.content.strip():
        parts.append(result.content)

    if result.sources:
        lines: list[str] = []
        for source in result.sources:
            label = source_label(source.url, source.title)
            meta_parts: list[str] = []
            excerpt = source.summary or source.snippet
            if excerpt:
                meta_parts.append(excerpt)
            if source.published_at:
                meta_parts.append(f'({source.published_at})')
            suffix = f' — {" ".join(meta_parts)}' if meta_parts else ''
            lines.append(f'- [{label}]({source.url}){suffix}')
        parts.append('Sources:\n' + '\n'.join(lines))
    elif not result.content:
        parts.append('No results found.')

    if result.truncated:
        parts.append(
            f'(Showing the first {len(result.sources)} sources. '
            'Refine the query for more.)'
        )
    parts.append('Cite the relevant URLs above as markdown links in your answer.')
    return '\n\n'.join(parts)


def present_search_call(queries: list[str]) -> dict[str, Any]:
    """Pending-call presentation: a search card titled by the query list."""
    title = ', '.join(queries)
    return {
        'card': 'generic',
        'title': title,
        'kind': 'search',
        'raw_input': title,
    }


def duckduckgo_search(queries: list[str], max_results: int = WEB_SEARCH_MAX_RESULTS) -> WebSearchResult:
    """Perform DuckDuckGo HTML scraping search.

    Mirrors deepseek-harness web search provider: scrapes DuckDuckGo HTML
    results page, extracts sources with title, URL, snippet, and date.
    """
    sources: list[WebSearchSource] = []
    seen_urls: set[str] = set()

    for query in queries:
        if len(sources) >= max_results:
            break
        try:
            encoded_query = urllib.parse.quote(query)
            url = f'https://html.duckduckgo.com/html/?q={encoded_query}'
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                    'Accept': 'text/html,application/xhtml+xml',
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html_content = resp.read().decode('utf-8', errors='replace')

            # Simple regex-based extraction of DuckDuckGo results
            # Each result is in a <div class="result"> block
            result_blocks = re.findall(
                r'<div class="result results_links.*?</div>\s*</div>\s*</div>',
                html_content,
                re.DOTALL,
            )
            for block in result_blocks:
                if len(sources) >= max_results:
                    break
                # Extract URL
                url_match = re.search(
                    r'<a rel="nofollow" class="result__a" href="([^"]+)"',
                    block,
                )
                if not url_match:
                    continue
                result_url = url_match.group(1)
                # DuckDuckGo uses redirect URLs; extract the actual URL
                if result_url.startswith('//duckduckgo.com/l/?'):
                    parsed = urllib.parse.urlparse(result_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    if 'uddg' in params:
                        result_url = params['uddg'][0]

                if result_url in seen_urls:
                    continue
                seen_urls.add(result_url)

                # Extract title
                title_match = re.search(
                    r'class="result__a"[^>]*>(.*?)</a>',
                    block,
                    re.DOTALL,
                )
                title = None
                if title_match:
                    title = re.sub(r'<[^>]+>', '', title_match.group(1))
                    title = html.unescape(title).strip()

                # Extract snippet
                snippet_match = re.search(
                    r'<a class="result__snippet".*?>(.*?)</a>',
                    block,
                    re.DOTALL,
                )
                snippet = None
                if snippet_match:
                    snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1))
                    snippet = html.unescape(snippet).strip()

                sources.append(WebSearchSource(
                    url=result_url,
                    title=title,
                    snippet=snippet,
                ))

        except (urllib.error.URLError, urllib.error.HTTPError, OSError, Exception):
            # Continue to next query on failure
            continue

    truncated = len(sources) >= max_results and len(queries) > 0
    return WebSearchResult(
        sources=sources[:max_results],
        truncated=truncated,
    )


__all__ = [
    'WEB_SEARCH_MAX_RESULTS',
    'WEB_SEARCH_MAX_QUERIES',
    'WEB_SEARCH_SUMMARY_MAX_CHARS',
    'WebSearchSource',
    'WebSearchResult',
    'WebSearchMeta',
    'WebSearchArgsError',
    'parse_search_args',
    'source_label',
    'project_source',
    'model_source',
    'search_meta_from_value',
    'format_search_output',
    'present_search_call',
    'duckduckgo_search',
]

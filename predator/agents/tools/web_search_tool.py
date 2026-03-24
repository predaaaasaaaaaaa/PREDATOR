"""Web search and fetch tools — agent-facing OSINT research utilities.

Two tools:
- WebSearchTool: Search the web via DuckDuckGo (no API key required).
- WebFetchReadableTool: Fetch a URL and return readable text (HTML stripped).
"""

from __future__ import annotations

import html
import re
from typing import Any, Callable, Optional
from urllib.parse import quote_plus, unquote

import httpx

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.web_search")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_duckduckgo_lite(html_text: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo Lite HTML response into structured results.

    The lite page renders results as table rows.  Each result link lives
    inside an ``<a class="result-link">`` (or simply the first ``<a>``
    inside a ``<td>`` with class ``result-link``).  The snippet follows
    in a subsequent ``<td class="result-snippet">``.
    """
    results: list[dict[str, str]] = []

    # Strategy: pull all <a> tags that look like result links and nearby snippets.
    # DuckDuckGo Lite wraps each result in a table row structure:
    #   <a class="result-link" href="...">Title</a>
    #   <td class="result-snippet">Snippet text</td>

    # Extract result links — class="result-link"
    link_pattern = re.compile(
        r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>',
        re.IGNORECASE | re.DOTALL,
    )

    links = link_pattern.findall(html_text)
    snippets = snippet_pattern.findall(html_text)

    # Fallback: if the class-based patterns find nothing, try a broader approach
    if not links:
        # DuckDuckGo Lite sometimes uses simpler markup
        link_pattern_alt = re.compile(
            r'<a[^>]+rel="nofollow"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        links = link_pattern_alt.findall(html_text)

    if not links:
        # Very broad fallback — grab links that look like external results
        link_pattern_broad = re.compile(
            r'<a[^>]+href="(https?://(?!duckduckgo)[^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        links = link_pattern_broad.findall(html_text)

    for i, (url, title_html) in enumerate(links):
        if i >= max_results:
            break

        # Clean title
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        title = html.unescape(title)

        # Clean URL (DuckDuckGo may wrap in a redirect)
        if "uddg=" in url:
            match = re.search(r"uddg=([^&]+)", url)
            if match:
                url = unquote(match.group(1))

        # Get corresponding snippet if available
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            snippet = html.unescape(snippet)

        if url and title:
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


def _strip_html(raw_html: str) -> str:
    """Strip HTML tags and collapse whitespace to produce readable text."""
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Replace block-level tags with newlines
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title(raw_html: str) -> str:
    """Extract the <title> from an HTML document."""
    match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if match:
        return html.unescape(match.group(1)).strip()
    return ""


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------

class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo — no API key required.

    Useful for OSINT research: finding information about targets, domains,
    organisations, people, vulnerabilities, and more.
    """

    name = "web_search"
    description = (
        "Search the web using DuckDuckGo. Returns a list of results with "
        "title, URL, and snippet. Useful for OSINT reconnaissance and "
        "general research — no API key needed."
    )
    category = ToolCategory.WEB

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
                "num_results": {
                    "type": "number",
                    "description": "Maximum number of results to return (default 10).",
                },
                "region": {
                    "type": "string",
                    "description": (
                        "Region/locale code for localised results "
                        "(e.g. 'us-en', 'uk-en', 'de-de'). Optional."
                    ),
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        query = arguments.get("query", "").strip()
        if not query:
            return ToolResult(output="Missing required parameter: query", is_error=True)

        num_results = int(arguments.get("num_results", 10))
        region = arguments.get("region", "")

        url = "https://lite.duckduckgo.com/lite/"
        params: dict[str, str] = {"q": query}
        if region:
            params["kl"] = region

        log.info(f"Searching DuckDuckGo for: {query!r}")

        try:
            async with httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                timeout=20.0,
                follow_redirects=True,
            ) as client:
                resp = await client.post(url, data=params)
                resp.raise_for_status()
                html_text = resp.text
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                output=f"DuckDuckGo returned HTTP {exc.response.status_code}",
                is_error=True,
            )
        except httpx.RequestError as exc:
            return ToolResult(
                output=f"Network error querying DuckDuckGo: {exc}",
                is_error=True,
            )

        results = _parse_duckduckgo_lite(html_text, max_results=num_results)

        if not results:
            return ToolResult(
                output=f"No results found for query: {query}",
                metadata={"query": query, "result_count": 0},
            )

        # Format output
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
            lines.append("")

        return ToolResult(
            output="\n".join(lines),
            metadata={
                "query": query,
                "result_count": len(results),
                "results": results,
            },
        )


# ---------------------------------------------------------------------------
# WebFetchReadableTool
# ---------------------------------------------------------------------------

class WebFetchReadableTool(BaseTool):
    """Fetch a URL and return its content as readable plain text.

    Strips all HTML to produce clean, readable text — useful for reading
    web pages, documentation, articles, and other web content.
    """

    name = "web_fetch_readable"
    description = (
        "Fetch a URL and return its content as readable plain text. "
        "HTML tags are stripped, leaving only the textual content. "
        "Useful for reading web pages discovered via web_search."
    )
    category = ToolCategory.WEB

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "max_length": {
                    "type": "number",
                    "description": (
                        "Maximum number of characters to return (default 10000). "
                        "Content is truncated beyond this limit."
                    ),
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        url = arguments.get("url", "").strip()
        if not url:
            return ToolResult(output="Missing required parameter: url", is_error=True)

        max_length = int(arguments.get("max_length", 10000))

        log.info(f"Fetching URL: {url}")

        try:
            async with httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                timeout=30.0,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                output=f"HTTP error {exc.response.status_code} fetching {url}",
                is_error=True,
            )
        except httpx.RequestError as exc:
            return ToolResult(
                output=f"Network error fetching {url}: {exc}",
                is_error=True,
            )

        content_type = resp.headers.get("content-type", "")

        # If not HTML, return raw text (e.g. JSON, plain text)
        if "html" not in content_type.lower():
            text = resp.text[:max_length]
            truncated = len(resp.text) > max_length
            suffix = "\n\n[... truncated]" if truncated else ""
            return ToolResult(
                output=f"Content-Type: {content_type}\n\n{text}{suffix}",
                metadata={"url": url, "content_type": content_type, "truncated": truncated},
            )

        raw_html = resp.text
        title = _extract_title(raw_html)
        readable = _strip_html(raw_html)

        truncated = len(readable) > max_length
        readable = readable[:max_length]
        if truncated:
            readable += "\n\n[... truncated]"

        header = f"Title: {title}\nURL: {url}\n\n" if title else f"URL: {url}\n\n"

        return ToolResult(
            output=header + readable,
            metadata={
                "url": url,
                "title": title,
                "content_type": content_type,
                "truncated": truncated,
                "length": len(readable),
            },
        )

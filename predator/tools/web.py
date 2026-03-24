"""Web tools — mirrors OpenClaw's web fetch/search capabilities.

Provides HTTP requests and web search for OSINT data gathering.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("tools.web")


class WebFetchTool(BaseTool):
    """Fetch web page content."""

    name = "web_fetch"
    description = (
        "Fetch the content of a web page or API endpoint. "
        "Returns the response body as text. Useful for OSINT data gathering, "
        "API queries, and web reconnaissance."
    )
    category = ToolCategory.WEB

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "method": {
                    "type": "string",
                    "description": "HTTP method (default: GET)",
                    "enum": ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers",
                },
                "body": {
                    "type": "string",
                    "description": "Request body (for POST/PUT)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds (default: 30)",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        import httpx

        url = arguments["url"]
        method = arguments.get("method", "GET")
        headers = arguments.get("headers", {})
        body = arguments.get("body")
        timeout = int(arguments.get("timeout", 30))

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                verify=False,  # OSINT may need to access self-signed certs
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                )

                content = response.text
                # Truncate if too large
                max_size = 100_000
                if len(content) > max_size:
                    content = content[:max_size] + f"\n\n[TRUNCATED — {len(content)} chars total]"

                return ToolResult(
                    output=content,
                    metadata={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "url": str(response.url),
                    },
                )
        except Exception as e:
            return ToolResult(output=f"Fetch error: {e}", is_error=True)


class WebSearchTool(BaseTool):
    """Web search for OSINT intelligence gathering."""

    name = "web_search"
    description = (
        "Search the web for information. Uses command-line search utilities. "
        "Essential for OSINT: finding exposed data, leaked credentials, "
        "social media profiles, domain info, and more."
    )
    category = ToolCategory.WEB

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "number",
                    "description": "Maximum results (default: 10)",
                },
                "engine": {
                    "type": "string",
                    "description": "Search method: 'google_dork' for Google dorking, 'default' for standard search",
                    "enum": ["default", "google_dork"],
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.process.executor import ExecOptions, execute as exec_cmd

        query = arguments["query"]
        max_results = int(arguments.get("max_results", 10))
        engine = arguments.get("engine", "default")

        # Use curl with search APIs or lynx/w3m for text-based browsing
        # This is a practical approach that works on any Linux system
        escaped_query = query.replace("'", "'\\''")

        if engine == "google_dork":
            # Google dorking via curl
            cmd = (
                f"curl -sL -A 'Mozilla/5.0' "
                f"'https://www.google.com/search?q={escaped_query}&num={max_results}' "
                f"2>/dev/null | python3 -c \""
                f"import sys,re; html=sys.stdin.read(); "
                f"urls=re.findall(r'href=\\\"(https?://[^\\\"&]+)', html); "
                f"[print(u) for u in urls[:{max_results}] if 'google' not in u]\""
            )
        else:
            cmd = (
                f"curl -sL -A 'Mozilla/5.0' "
                f"'https://html.duckduckgo.com/html/?q={escaped_query}' "
                f"2>/dev/null | python3 -c \""
                f"import sys,re,html as h; content=sys.stdin.read(); "
                f"results=re.findall(r'class=\\\"result__a\\\"[^>]*href=\\\"([^\\\"]+)\\\"[^>]*>([^<]+)', content); "
                f"[print(f'{{h.unescape(t).strip()}}\\n  {{u}}\\n') for u,t in results[:{max_results}]]\""
            )

        result = await exec_cmd(ExecOptions(command=cmd, timeout=30))

        if result.stdout.strip():
            return ToolResult(
                output=result.stdout,
                metadata={"query": query, "engine": engine},
            )
        else:
            return ToolResult(
                output=f"No results found for: {query}",
                metadata={"query": query, "engine": engine},
            )

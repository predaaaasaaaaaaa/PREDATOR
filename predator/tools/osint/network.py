"""Network OSINT tools — Shodan, Censys for internet-wide device/service search."""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class ShodanTool(BaseTool):
    """Search engine for internet-connected devices."""

    name = "shodan"
    description = (
        "Search Shodan for internet-connected devices, servers, IoT devices, "
        "SCADA systems, webcams, and more. Can search by IP, query banners, "
        "find specific services, and identify vulnerable systems. "
        "Requires SHODAN_API_KEY environment variable."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "Shodan command: search, host, info, count, scan, stats"
                    ),
                    "enum": ["search", "host", "info", "count", "scan", "stats"],
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search query or IP address. For search: Shodan query syntax "
                        "(e.g., 'apache country:US port:443'). For host: IP address."
                    ),
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional shodan CLI arguments",
                },
            },
            "required": ["command", "query"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        shodan_cmd = arguments["command"]
        query = arguments["query"]
        extra_args = arguments.get("extra_args", "")

        cmd = f"shodan {shodan_cmd} '{query}' {extra_args}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "shodan_command": shodan_cmd,
                "query": query,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )


class CensysTool(BaseTool):
    """Search engine for hosts, certificates, and networks."""

    name = "censys"
    description = (
        "Search Censys for hosts, certificates, and network data. "
        "Find servers by service, protocol, certificate attributes, "
        "or ASN. Requires CENSYS_API_ID and CENSYS_API_SECRET."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search_type": {
                    "type": "string",
                    "description": "Search type: hosts, certificates",
                    "enum": ["hosts", "certificates"],
                },
                "query": {
                    "type": "string",
                    "description": "Censys search query",
                },
                "max_results": {
                    "type": "number",
                    "description": "Maximum results (default: 25)",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        search_type = arguments.get("search_type", "hosts")
        query = arguments["query"]
        max_results = int(arguments.get("max_results", 25))

        cmd = f"censys search '{query}' --index-type={search_type} --max-records={max_results}"

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "search_type": search_type,
                "query": query,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )

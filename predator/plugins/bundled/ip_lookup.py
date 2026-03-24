"""IP Lookup plugin — bundled PREDATOR plugin.

Demonstrates the plugin SDK by providing a simple ``ip_lookup`` tool that
queries the free ip-api.com geolocation API.

Usage::

    # The plugin is auto-discovered from the bundled directory.
    # Or load manually:
    from predator.plugins.bundled.ip_lookup import Plugin
    plugin = Plugin()
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from predator.plugins.sdk import PluginBase
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class IPLookupTool(BaseTool):
    """Tool that performs IP geolocation lookups via ip-api.com."""

    name = "ip_lookup"
    description = (
        "Look up geolocation and network information for an IP address "
        "using the free ip-api.com service. Returns country, city, ISP, "
        "AS number, and coordinates."
    )
    category = ToolCategory.OSINT
    requires_approval = False

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ip": {
                    "type": "string",
                    "description": (
                        "The IP address to look up. "
                        "Omit or pass empty string for your own public IP."
                    ),
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "Comma-separated list of fields to return. "
                        "Defaults to all standard fields."
                    ),
                },
            },
            "required": [],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        ip = arguments.get("ip", "").strip()
        fields_param = arguments.get("fields", "")

        url = f"http://ip-api.com/json/{ip}"
        if fields_param:
            url += f"?fields={fields_param}"

        try:
            req = Request(url, headers={"User-Agent": "PREDATOR/1.0"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if data.get("status") == "fail":
                return ToolResult(
                    output=f"Lookup failed: {data.get('message', 'unknown error')}",
                    is_error=True,
                )

            # Format a human-readable summary
            lines = []
            key_order = [
                "query", "status", "country", "regionName", "city",
                "zip", "lat", "lon", "timezone", "isp", "org", "as",
            ]
            for key in key_order:
                if key in data:
                    lines.append(f"{key:>12}: {data[key]}")
            # Include any extra fields not in key_order
            for key, val in data.items():
                if key not in key_order:
                    lines.append(f"{key:>12}: {val}")

            summary = "\n".join(lines)
            return ToolResult(
                output=summary,
                metadata=data,
            )

        except URLError as e:
            return ToolResult(
                output=f"Network error during IP lookup: {e}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                output=f"IP lookup error: {type(e).__name__}: {e}",
                is_error=True,
            )


class Plugin(PluginBase):
    """Built-in IP geolocation lookup plugin."""

    id = "predator.bundled.ip_lookup"
    name = "IP Lookup"
    version = "1.0.0"
    description = "Geolocation lookup for IP addresses via ip-api.com"
    author = "PREDATOR"

    @property
    def tools(self) -> list[BaseTool]:
        return [IPLookupTool()]

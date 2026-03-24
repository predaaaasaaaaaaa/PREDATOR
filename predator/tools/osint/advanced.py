"""Advanced OSINT tools — subdomain enumeration, URL harvesting, web crawling.

The tools that separate script kiddies from real OSINT operators.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.tools.auto_installer import auto_installer
from predator.process.executor import ExecOptions, execute


class SubfinderTool(BaseTool):
    """Fast passive subdomain discovery."""

    name = "subfinder"
    description = (
        "Fast passive subdomain enumeration using multiple sources: "
        "crt.sh, Shodan, VirusTotal, SecurityTrails, etc."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "recursive": {"type": "boolean", "description": "Enable recursive enumeration"},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["domain"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("subfinder")
        domain = arguments["domain"]
        extra = arguments.get("extra_args", "")
        cmd = f"subfinder -d {domain} -silent"
        if arguments.get("recursive"):
            cmd += " -recursive"
        cmd += f" {extra}"
        opts = ExecOptions(command=cmd, timeout=300)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class AmassTool(BaseTool):
    """OWASP Amass — deep subdomain enumeration and attack surface mapping."""

    name = "amass"
    description = (
        "OWASP Amass — in-depth subdomain enumeration using DNS, scraping, "
        "certificate transparency, APIs. Passive and active modes."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "mode": {"type": "string", "description": "passive or active", "enum": ["passive", "active"]},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["domain"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("amass")
        domain = arguments["domain"]
        mode = arguments.get("mode", "passive")
        extra = arguments.get("extra_args", "")
        flag = "-passive" if mode == "passive" else "-active"
        cmd = f"amass enum {flag} -d {domain} {extra}"
        opts = ExecOptions(command=cmd, timeout=600)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class WaybackUrlsTool(BaseTool):
    """Fetch URLs from the Wayback Machine."""

    name = "waybackurls"
    description = "Fetch all URLs for a domain from the Wayback Machine archive."
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["domain"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("waybackurls")
        domain = arguments["domain"]
        extra = arguments.get("extra_args", "")
        cmd = f"echo {domain} | waybackurls {extra}"
        opts = ExecOptions(command=cmd, timeout=300)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class GauTool(BaseTool):
    """Get All URLs — fetch URLs from multiple sources."""

    name = "gau"
    description = (
        "Get All URLs (gau) — fetches known URLs from AlienVault OTX, "
        "Wayback Machine, Common Crawl, and URLScan."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["domain"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("gau")
        domain = arguments["domain"]
        extra = arguments.get("extra_args", "")
        cmd = f"echo {domain} | gau {extra}"
        opts = ExecOptions(command=cmd, timeout=300)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class KatanaTool(BaseTool):
    """Next-generation web crawler."""

    name = "katana"
    description = (
        "Katana — next-generation web crawling framework by ProjectDiscovery. "
        "JavaScript rendering, headless mode, scope control."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL"},
                "depth": {"type": "number", "description": "Crawl depth (default: 3)"},
                "js_crawl": {"type": "boolean", "description": "Enable JavaScript rendering"},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["url"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("katana")
        url = arguments["url"]
        depth = arguments.get("depth", 3)
        extra = arguments.get("extra_args", "")
        cmd = f"katana -u {url} -d {depth} -silent"
        if arguments.get("js_crawl"):
            cmd += " -js-crawl"
        cmd += f" {extra}"
        opts = ExecOptions(command=cmd, timeout=600)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class HttpxTool(BaseTool):
    """Fast HTTP toolkit for probing and tech detection."""

    name = "httpx"
    description = (
        "httpx — fast multi-purpose HTTP toolkit. Probes for live hosts, "
        "detects technologies, extracts titles, status codes, response sizes."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL/domain/IP or file with targets"},
                "tech_detect": {"type": "boolean", "description": "Enable technology detection"},
                "extra_args": {"type": "string", "description": "Additional arguments"},
            },
            "required": ["target"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        await auto_installer.ensure_tool("httpx")
        target = arguments["target"]
        extra = arguments.get("extra_args", "")

        if target.startswith("/") or target.startswith("."):
            cmd = f"httpx -l {target} -silent -title -status-code -content-length"
        else:
            cmd = f"echo {target} | httpx -silent -title -status-code -content-length"

        if arguments.get("tech_detect"):
            cmd += " -tech-detect"
        cmd += f" {extra}"

        opts = ExecOptions(command=cmd, timeout=300)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )


class CrtshTool(BaseTool):
    """Certificate Transparency log search via crt.sh."""

    name = "crtsh"
    description = (
        "Search certificate transparency logs (crt.sh) for subdomains. "
        "No installation needed — uses the public API."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
            },
            "required": ["domain"],
        }

    async def execute(self, tool_call_id: str, arguments: dict[str, Any],
                      on_update: Optional[Callable[[str], None]] = None) -> ToolResult:
        domain = arguments["domain"]
        cmd = f"curl -s 'https://crt.sh/?q=%25.{domain}&output=json' | jq -r '.[].name_value' | sort -u"
        opts = ExecOptions(command=cmd, timeout=60)
        result = await execute(opts, on_output=on_update)
        return ToolResult(
            output=result.stdout or result.stderr or "No certificates found",
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"exit_code": result.exit_code},
        )

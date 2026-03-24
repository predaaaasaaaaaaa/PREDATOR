"""Domain and Web OSINT tools — WHOIS, theHarvester, subdomain enumeration, DNS recon.

Core tools for the reconnaissance phase of any engagement.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class WhoisTool(BaseTool):
    """WHOIS lookup for domain registration data."""

    name = "whois"
    description = (
        "Perform WHOIS lookup on a domain or IP address to retrieve "
        "registration data: registrant, registrar, creation/expiry dates, "
        "name servers, and contact information."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Domain name or IP address to look up",
                },
            },
            "required": ["target"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        target = arguments["target"]
        result = await execute(
            ExecOptions(command=f"whois {target}", timeout=30, tool_call_id=tool_call_id),
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"target": target, "elapsed": round(result.elapsed, 2)},
        )


class TheHarvesterTool(BaseTool):
    """Email, subdomain, host, and name harvesting from public sources."""

    name = "theharvester"
    description = (
        "Run theHarvester to collect emails, subdomains, hosts, employee names, "
        "and open ports from public sources (Google, Bing, LinkedIn, Shodan, etc.). "
        "Essential passive reconnaissance tool."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Target domain (e.g., 'example.com')",
                },
                "source": {
                    "type": "string",
                    "description": (
                        "Data source(s): google, bing, linkedin, shodan, "
                        "dnsdumpster, virustotal, netcraft, all"
                    ),
                },
                "limit": {
                    "type": "number",
                    "description": "Limit results per source (default: 500)",
                },
                "start": {
                    "type": "number",
                    "description": "Start result number (default: 0)",
                },
            },
            "required": ["domain"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        domain = arguments["domain"]
        source = arguments.get("source", "all")
        limit = int(arguments.get("limit", 500))
        start = int(arguments.get("start", 0))

        cmd = (
            f"theHarvester -d {domain} -b {source} "
            f"-l {limit} -S {start}"
        )

        result = await execute(
            ExecOptions(command=cmd, timeout=300, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "domain": domain,
                "source": source,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )


class SubdomainEnumTool(BaseTool):
    """Subdomain enumeration using multiple tools."""

    name = "subdomain_enum"
    description = (
        "Enumerate subdomains of a target domain using tools like "
        "Sublist3r, Amass, or Subfinder. Discovers attack surface by "
        "finding all subdomains associated with a target."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Target domain (e.g., 'example.com')",
                },
                "tool": {
                    "type": "string",
                    "description": "Tool to use: sublist3r, amass, subfinder",
                    "enum": ["sublist3r", "amass", "subfinder"],
                },
                "bruteforce": {
                    "type": "boolean",
                    "description": "Enable brute-force enumeration (active scanning)",
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional arguments for the chosen tool",
                },
            },
            "required": ["domain"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        domain = arguments["domain"]
        tool = arguments.get("tool", "sublist3r")
        bruteforce = arguments.get("bruteforce", False)
        extra_args = arguments.get("extra_args", "")

        if tool == "amass":
            mode = "enum" if not bruteforce else "enum -brute"
            cmd = f"amass {mode} -d {domain} {extra_args}"
        elif tool == "subfinder":
            cmd = f"subfinder -d {domain} -silent {extra_args}"
        else:
            bf_flag = "-b" if bruteforce else ""
            cmd = f"sublist3r -d {domain} {bf_flag} {extra_args}"

        result = await execute(
            ExecOptions(command=cmd, timeout=600, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "domain": domain,
                "tool": tool,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )


class DnsReconTool(BaseTool):
    """DNS reconnaissance — zone transfers, record enumeration, reverse lookups."""

    name = "dnsrecon"
    description = (
        "Perform DNS reconnaissance: zone transfers, DNS record enumeration, "
        "reverse lookups, SRV record enumeration, subdomain brute-forcing, "
        "and cache snooping. Uses dnsrecon or dig."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Target domain",
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Recon type: std (standard), axfr (zone transfer), "
                        "rvl (reverse), brt (brute-force), srv (SRV records)"
                    ),
                    "enum": ["std", "axfr", "rvl", "brt", "srv"],
                },
                "nameserver": {
                    "type": "string",
                    "description": "Specific nameserver to query",
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional arguments",
                },
            },
            "required": ["domain"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        domain = arguments["domain"]
        recon_type = arguments.get("type", "std")
        nameserver = arguments.get("nameserver", "")
        extra_args = arguments.get("extra_args", "")

        ns_flag = f"-n {nameserver}" if nameserver else ""
        cmd = f"dnsrecon -d {domain} -t {recon_type} {ns_flag} {extra_args}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "domain": domain,
                "type": recon_type,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )

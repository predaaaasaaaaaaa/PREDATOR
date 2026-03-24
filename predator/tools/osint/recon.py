"""Reconnaissance tools — Nmap, Masscan for network discovery and scanning.

These are the primary tools ethical hackers use for the reconnaissance phase.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class NmapTool(BaseTool):
    """Network scanner — port scanning, service detection, OS fingerprinting."""

    name = "nmap"
    description = (
        "Run Nmap network scanner for port scanning, service detection, "
        "OS fingerprinting, and vulnerability scanning using NSE scripts. "
        "Supports all Nmap scan types: -sS (SYN), -sT (TCP connect), "
        "-sU (UDP), -sV (version), -O (OS detection), -A (aggressive), "
        "--script (NSE scripts). Requires authorization for active scanning."
    )
    category = ToolCategory.OSINT
    requires_approval = True

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target IP, hostname, CIDR range, or file (-iL)",
                },
                "scan_type": {
                    "type": "string",
                    "description": "Scan type: syn, tcp, udp, version, os, aggressive, ping",
                    "enum": ["syn", "tcp", "udp", "version", "os", "aggressive", "ping"],
                },
                "ports": {
                    "type": "string",
                    "description": "Port specification (e.g., '22,80,443', '1-1000', '-' for all)",
                },
                "scripts": {
                    "type": "string",
                    "description": "NSE script(s) to run (e.g., 'vuln', 'http-enum', 'default')",
                },
                "timing": {
                    "type": "string",
                    "description": "Timing template: T0-T5 (paranoid to insane)",
                    "enum": ["T0", "T1", "T2", "T3", "T4", "T5"],
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional nmap arguments",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format: normal, xml, grep",
                    "enum": ["normal", "xml", "grep"],
                },
            },
            "required": ["target"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        target = arguments["target"]
        scan_type = arguments.get("scan_type", "syn")
        ports = arguments.get("ports")
        scripts = arguments.get("scripts")
        timing = arguments.get("timing", "T3")
        extra_args = arguments.get("extra_args", "")
        output_format = arguments.get("output_format", "normal")

        # Build nmap command
        scan_flags = {
            "syn": "-sS",
            "tcp": "-sT",
            "udp": "-sU",
            "version": "-sV",
            "os": "-O",
            "aggressive": "-A",
            "ping": "-sn",
        }

        cmd_parts = ["nmap", scan_flags.get(scan_type, "-sS")]
        cmd_parts.append(f"-{timing}")

        if ports:
            cmd_parts.append(f"-p {ports}")

        if scripts:
            cmd_parts.append(f"--script={scripts}")

        output_flags = {"normal": "-oN -", "xml": "-oX -", "grep": "-oG -"}
        cmd_parts.append(output_flags.get(output_format, "-oN -"))

        if extra_args:
            cmd_parts.append(extra_args)

        cmd_parts.append(target)
        cmd = " ".join(cmd_parts)

        result = await execute(
            ExecOptions(command=cmd, timeout=1800, tool_call_id=tool_call_id),
            on_output=on_update,
        )

        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "command": cmd,
                "exit_code": result.exit_code,
                "elapsed": round(result.elapsed, 2),
                "target": target,
                "scan_type": scan_type,
            },
        )


class MasscanTool(BaseTool):
    """High-speed port scanner — scans large networks quickly."""

    name = "masscan"
    description = (
        "Run Masscan for high-speed port scanning of large networks. "
        "Can scan the entire internet in minutes. Best for quickly "
        "identifying open ports across large IP ranges. "
        "Requires root/elevated privileges."
    )
    category = ToolCategory.OSINT
    requires_approval = True

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target IP range (CIDR notation, e.g., '10.0.0.0/24')",
                },
                "ports": {
                    "type": "string",
                    "description": "Port(s) to scan (e.g., '80,443', '0-65535')",
                },
                "rate": {
                    "type": "number",
                    "description": "Packets per second (default: 1000)",
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional masscan arguments",
                },
            },
            "required": ["target", "ports"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        target = arguments["target"]
        ports = arguments["ports"]
        rate = int(arguments.get("rate", 1000))
        extra_args = arguments.get("extra_args", "")

        cmd = f"masscan {target} -p{ports} --rate={rate} {extra_args}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=600, elevated=True, tool_call_id=tool_call_id),
            on_output=on_update,
        )

        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "command": cmd,
                "exit_code": result.exit_code,
                "elapsed": round(result.elapsed, 2),
            },
        )

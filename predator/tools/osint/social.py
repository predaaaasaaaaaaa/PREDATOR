"""Social media OSINT tools — Sherlock, social-analyzer for username/profile hunting."""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class SherlockTool(BaseTool):
    """Username search across 400+ social networks."""

    name = "sherlock"
    description = (
        "Search for a username across 400+ social media platforms and websites. "
        "Identifies which platforms a person has accounts on. "
        "Essential for OSINT profiling and social media reconnaissance."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Username to search for",
                },
                "sites": {
                    "type": "string",
                    "description": "Specific sites to check (comma-separated, optional)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout per site in seconds (default: 60)",
                },
                "print_found": {
                    "type": "boolean",
                    "description": "Only show found results (default: true)",
                },
            },
            "required": ["username"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        username = arguments["username"]
        sites = arguments.get("sites", "")
        timeout = int(arguments.get("timeout", 60))
        print_found = arguments.get("print_found", True)

        cmd_parts = ["sherlock", username, f"--timeout {timeout}"]
        if print_found:
            cmd_parts.append("--print-found")
        if sites:
            for site in sites.split(","):
                cmd_parts.append(f"--site {site.strip()}")

        cmd = " ".join(cmd_parts)

        result = await execute(
            ExecOptions(command=cmd, timeout=300, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "username": username,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )


class SocialAnalyzerTool(BaseTool):
    """Social media profile analysis across multiple platforms."""

    name = "social_analyzer"
    description = (
        "Analyze social media profiles for a given username or name. "
        "Searches across multiple platforms and provides detailed profile "
        "information including account age, activity, and connections."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Username or full name to search",
                },
                "mode": {
                    "type": "string",
                    "description": "Search mode: fast, slow (thorough)",
                    "enum": ["fast", "slow"],
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional arguments",
                },
            },
            "required": ["username"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        username = arguments["username"]
        mode = arguments.get("mode", "fast")
        extra_args = arguments.get("extra_args", "")

        cmd = f"social-analyzer --username '{username}' --mode {mode} {extra_args}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=300, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={
                "username": username,
                "command": cmd,
                "elapsed": round(result.elapsed, 2),
            },
        )

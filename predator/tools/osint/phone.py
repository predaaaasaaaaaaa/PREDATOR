"""Phone OSINT tools — PhoneInfoga for phone number intelligence."""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class PhoneInfoTool(BaseTool):
    """Phone number intelligence gathering."""

    name = "phone_info"
    description = (
        "Gather intelligence on a phone number using PhoneInfoga. "
        "Identifies carrier, line type, country, and searches across "
        "Google, social media, and reputation services for associated data."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "number": {
                    "type": "string",
                    "description": "Phone number in international format (e.g., '+1234567890')",
                },
                "scanner": {
                    "type": "string",
                    "description": "Scanner to use: local, numverify, googlesearch, ovh",
                    "enum": ["local", "numverify", "googlesearch", "ovh"],
                },
            },
            "required": ["number"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        number = arguments["number"]
        scanner = arguments.get("scanner", "local")

        cmd = f"phoneinfoga scan -n '{number}' -s {scanner}"

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"number": number, "command": cmd, "elapsed": round(result.elapsed, 2)},
        )

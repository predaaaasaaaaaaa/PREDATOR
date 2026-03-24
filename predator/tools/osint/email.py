"""Email OSINT tools — h8mail for breach hunting, Holehe for account discovery."""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class EmailHunterTool(BaseTool):
    """Email breach hunting and reconnaissance."""

    name = "email_hunter"
    description = (
        "Hunt for email addresses in breach databases and public sources. "
        "Uses h8mail to check if an email has been compromised in data breaches, "
        "and gathers related intelligence (passwords, associated accounts)."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email address to investigate",
                },
                "chase": {
                    "type": "boolean",
                    "description": "Chase related emails found in breaches",
                },
                "extra_args": {
                    "type": "string",
                    "description": "Additional h8mail arguments",
                },
            },
            "required": ["email"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        email = arguments["email"]
        chase = arguments.get("chase", False)
        extra_args = arguments.get("extra_args", "")

        chase_flag = "--chase" if chase else ""
        cmd = f"h8mail -t {email} {chase_flag} {extra_args}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"email": email, "command": cmd, "elapsed": round(result.elapsed, 2)},
        )


class BreachCheckTool(BaseTool):
    """Check which websites an email is registered on."""

    name = "breach_check"
    description = (
        "Check which websites and services an email address is registered on. "
        "Uses Holehe to enumerate account registrations across popular platforms "
        "(Twitter, Instagram, Facebook, LinkedIn, etc.) without alerting the target."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email address to check",
                },
                "only_used": {
                    "type": "boolean",
                    "description": "Only show services where email is registered (default: true)",
                },
            },
            "required": ["email"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        email = arguments["email"]
        only_used = arguments.get("only_used", True)

        only_flag = "--only-used" if only_used else ""
        cmd = f"holehe {email} {only_flag}".strip()

        result = await execute(
            ExecOptions(command=cmd, timeout=120, tool_call_id=tool_call_id),
            on_output=on_update,
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"email": email, "command": cmd, "elapsed": round(result.elapsed, 2)},
        )

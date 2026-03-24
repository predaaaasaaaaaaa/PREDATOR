"""Bash execution tool — mirrors OpenClaw's bash-tools.exec.ts.

The most important tool: gives the agent direct access to the Linux
shell and all installed tools (nmap, theHarvester, metasploit, etc.).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, ExecResult, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("tools.bash")


class BashTool(BaseTool):
    """Execute shell commands on the Linux system.

    Mirrors OpenClaw's exec tool — the core tool that gives the agent
    access to the entire system. On Kali Linux, this means access to
    all installed security tools (nmap, metasploit, burpsuite, etc.).
    """

    name = "bash"
    description = (
        "Execute a shell command on the Linux system. "
        "You have full access to all installed tools and utilities. "
        "On Kali Linux, this includes all pre-installed security tools "
        "(nmap, metasploit, theHarvester, sqlmap, etc.). "
        "Use this for any command-line operation: running tools, "
        "installing packages, managing files, networking, and more. "
        "Commands run as the current user. Use 'elevated: true' for sudo."
    )
    category = ToolCategory.SYSTEM
    requires_approval = False

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command (optional)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 1800)",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run in background and return immediately (default: false)",
                },
                "pty": {
                    "type": "boolean",
                    "description": (
                        "Run in pseudo-terminal for interactive tools (default: false)"
                    ),
                },
                "elevated": {
                    "type": "boolean",
                    "description": "Run with sudo (default: false)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        command = arguments["command"]
        log.info(f"Executing: {command[:100]}...")

        opts = ExecOptions(
            command=command,
            workdir=arguments.get("workdir"),
            timeout=int(arguments.get("timeout", 1800)),
            background=arguments.get("background", False),
            pty=arguments.get("pty", False),
            elevated=arguments.get("elevated", False),
            tool_call_id=tool_call_id,
        )

        result: ExecResult = await execute(opts, on_output=on_update)

        # Build output
        output_parts: list[str] = []

        if result.stdout:
            output_parts.append(result.stdout)

        if result.stderr:
            output_parts.append(f"\n[STDERR]\n{result.stderr}")

        if result.timed_out:
            output_parts.append(f"\n[TIMED OUT after {result.elapsed:.1f}s]")

        if not output_parts:
            output_parts.append(
                f"Command completed with exit code {result.exit_code} (no output)"
            )

        output = "".join(output_parts)

        # Truncate if too long
        max_output = 200_000  # 200KB
        if len(output) > max_output:
            output = output[:max_output] + f"\n\n[OUTPUT TRUNCATED — {len(output)} chars total]"

        return ToolResult(
            output=output,
            is_error=result.exit_code != 0,
            metadata={
                "exit_code": result.exit_code,
                "pid": result.pid,
                "elapsed": round(result.elapsed, 2),
                "timed_out": result.timed_out,
                "command": command,
            },
        )

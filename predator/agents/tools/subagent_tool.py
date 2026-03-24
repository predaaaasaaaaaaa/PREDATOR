"""Subagent orchestration tools — LLM-callable tools for multi-agent operations.

Mirrors OpenClaw's sessions-spawn-tool.ts and subagents-tool.ts:
- spawn_subagent: Launch an autonomous subagent for a subtask
- subagents: Introspection — list, kill, steer, wait, info
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult


class SubagentSpawnTool(BaseTool):
    """Spawn an autonomous subagent to handle a subtask.

    The subagent runs independently in an isolated session with its own
    tools and context. Results are auto-announced back to the parent.
    """

    name = "spawn_subagent"
    description = (
        "Spawn a background subagent to handle a subtask autonomously. "
        "The subagent runs in an isolated session and automatically "
        "reports results back when done. Use this when you need parallel "
        "execution or want to delegate a focused task (e.g., 'scan ports "
        "on target X' while you do other work). Returns immediately — "
        "does NOT wait for completion."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The task for the subagent to perform. Be specific — "
                        "this is the subagent's entire instruction."
                    ),
                },
                "label": {
                    "type": "string",
                    "description": "Short human-readable label (e.g., 'port-scan', 'osint-recon')",
                },
                "model": {
                    "type": "string",
                    "description": "Model override (optional, defaults to parent's model)",
                },
                "thinking": {
                    "type": "string",
                    "enum": ["off", "low", "medium", "high"],
                    "description": "Thinking level for the subagent (default: low)",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Max runtime in seconds (default: 600)",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.agents.subagent import SpawnParams, get_spawner

        spawner = get_spawner()
        parent_key = arguments.pop("_parent_session_key", "agent:default:main")

        params = SpawnParams(
            task=arguments.get("task", ""),
            label=arguments.get("label", ""),
            model=arguments.get("model", ""),
            thinking_level=arguments.get("thinking", "low"),
            timeout_seconds=int(arguments.get("timeout_seconds", 600)),
        )

        record = await spawner.spawn(params, parent_key)

        if record.state.value == "failed":
            return ToolResult(
                output=f"Spawn failed: {record.error}",
                is_error=True,
            )

        return ToolResult(
            output=(
                f"Subagent spawned successfully.\n"
                f"  Run ID:   {record.run_id}\n"
                f"  Label:    {record.label}\n"
                f"  Session:  {record.session_key}\n"
                f"  Depth:    {record.spawn_depth}\n"
                f"  Task:     {record.task[:300]}\n\n"
                f"The subagent is running in the background. "
                f"Results will be auto-announced when it finishes.\n"
                f"Use list_subagents to check status, or wait_subagent to block until done."
            ),
        )


class SubagentListTool(BaseTool):
    """List all spawned subagents and their status."""

    name = "list_subagents"
    description = (
        "List all subagents spawned by this agent, showing their current "
        "state (running/completed/failed), elapsed time, and results."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["all", "active", "completed", "failed"],
                    "description": "Filter by state (default: all)",
                },
            },
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.agents.subagent import get_spawner

        spawner = get_spawner()
        parent_key = arguments.pop("_parent_session_key", "agent:default:main")
        state_filter = arguments.get("filter", "all")

        children = spawner.get_children(parent_key)

        if state_filter == "active":
            children = [c for c in children if not c.is_done]
        elif state_filter == "completed":
            children = [c for c in children if c.state.value == "completed"]
        elif state_filter == "failed":
            children = [c for c in children if c.state.value in ("failed", "timeout", "cancelled")]

        if not children:
            return ToolResult(output=f"No subagents found (filter: {state_filter}).")

        lines = [f"Subagents ({len(children)}):\n"]
        for r in children:
            state_icon = {
                "pending": "...",
                "running": ">>>",
                "completed": "[+]",
                "failed": "[x]",
                "cancelled": "[-]",
                "timeout": "[!]",
            }.get(r.state.value, "???")

            elapsed = f"{r.elapsed:.1f}s"
            lines.append(
                f"  {state_icon} {r.label} "
                f"(ID: {r.run_id}) [{r.state.value.upper()}] {elapsed}"
            )
            lines.append(f"      Task: {r.task[:150]}")

            if r.result_text:
                preview = r.result_text[:300].replace("\n", " ")
                lines.append(f"      Result: {preview}")
            if r.error:
                lines.append(f"      Error: {r.error}")
            if r.total_tokens > 0:
                lines.append(f"      Tokens: {r.total_tokens} | Turns: {r.turns}")
            lines.append("")

        return ToolResult(output="\n".join(lines))


class SubagentWaitTool(BaseTool):
    """Wait for a specific subagent to complete and return its result."""

    name = "wait_subagent"
    description = (
        "Wait for a specific subagent to finish and return its result. "
        "Blocks until the subagent completes, fails, or times out."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The run ID of the subagent to wait for",
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": "Max time to wait in seconds (default: 300)",
                },
            },
            "required": ["run_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.agents.subagent import get_spawner

        spawner = get_spawner()
        run_id = arguments.get("run_id", "")
        timeout = float(arguments.get("timeout_seconds", 300))

        if on_update:
            on_update(f"Waiting for subagent {run_id}...")

        record = await spawner.wait(run_id, timeout=timeout)

        if not record:
            return ToolResult(
                output=f"Subagent {run_id} not found.",
                is_error=True,
            )

        if not record.is_done:
            return ToolResult(
                output=(
                    f"Subagent {run_id} still running after {timeout}s wait.\n"
                    f"State: {record.state.value}\n"
                    f"Elapsed: {record.elapsed:.1f}s"
                ),
            )

        return ToolResult(
            output=(
                f"Subagent {record.label} [{record.state.value.upper()}]\n"
                f"Run ID: {record.run_id}\n"
                f"Turns: {record.turns} | Tokens: {record.total_tokens} | "
                f"Time: {record.elapsed:.1f}s\n\n"
                f"{'Result' if record.state.value == 'completed' else 'Error'}:\n"
                f"{record.result_text or record.error or '(no output)'}"
            ),
        )


class SubagentKillTool(BaseTool):
    """Kill a running subagent."""

    name = "kill_subagent"
    description = (
        "Terminate a running subagent. Use when a subagent is stuck, "
        "taking too long, or no longer needed."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The run ID of the subagent to kill",
                },
            },
            "required": ["run_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.agents.subagent import get_spawner

        spawner = get_spawner()
        run_id = arguments.get("run_id", "")

        killed = await spawner.kill(run_id)

        if killed:
            return ToolResult(output=f"Subagent {run_id} terminated.")
        else:
            record = spawner.registry.get(run_id)
            if not record:
                return ToolResult(output=f"Subagent {run_id} not found.", is_error=True)
            return ToolResult(
                output=f"Cannot kill subagent {run_id} — state: {record.state.value}",
                is_error=True,
            )


class SubagentSteerTool(BaseTool):
    """Send a steering message to redirect a running subagent."""

    name = "steer_subagent"
    description = (
        "Send a steering message to a running subagent to redirect its work. "
        "The message will be injected into the subagent's next turn. "
        "Use when you want to refine, narrow, or change a subagent's task mid-execution."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The run ID of the subagent to steer",
                },
                "message": {
                    "type": "string",
                    "description": "The steering instruction to send",
                },
            },
            "required": ["run_id", "message"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        from predator.agents.subagent import get_spawner

        spawner = get_spawner()
        run_id = arguments.get("run_id", "")
        message = arguments.get("message", "")

        steered = await spawner.steer(run_id, message)

        if steered:
            return ToolResult(
                output=f"Steering message sent to subagent {run_id}:\n  {message[:200]}"
            )
        else:
            return ToolResult(
                output=f"Cannot steer subagent {run_id} — it may be finished or not found.",
                is_error=True,
            )

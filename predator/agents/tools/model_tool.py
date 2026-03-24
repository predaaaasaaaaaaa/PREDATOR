"""Model switching tools — allows the agent to switch LLM providers/models at runtime.

Two tools:
- SwitchModelTool: Switch to a different provider and/or model mid-conversation.
- ListModelsTool: List all configured providers and their available models.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.model_tool")


class SwitchModelTool(BaseTool):
    """Switch the active LLM provider and/or model at runtime.

    The agent (or user) can invoke this tool to change which LLM is
    handling subsequent turns without restarting the session.
    """

    name = "switch_model"
    description = (
        "Switch the active LLM provider and/or model. Use this to change which "
        "AI model handles subsequent messages. For example, switch to a cheaper "
        "model for simple tasks, or to a more powerful model for complex reasoning."
    )
    category = ToolCategory.SESSION

    def __init__(self, router: Any = None, runtime: Any = None) -> None:
        """
        Args:
            router: A ProviderRouter instance for performing the switch.
            runtime: An AgentRuntime instance (alternative — uses its switch_provider).
        """
        self._router = router
        self._runtime = runtime

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": (
                        "Name of the provider profile to switch to "
                        "(e.g. 'anthropic', 'openai', 'ollama', 'openrouter')."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Specific model identifier to use (e.g. 'claude-opus-4-20250514', "
                        "'gpt-4o', 'llama3'). If omitted, uses the provider's default model."
                    ),
                },
            },
            "required": ["provider"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        provider_name = arguments.get("provider", "")
        model = arguments.get("model")

        if not provider_name:
            return ToolResult(output="Missing required parameter: provider", is_error=True)

        # Try switching via the router first, then fall back to runtime
        router = self._router
        if router is None and self._runtime is not None:
            router = getattr(self._runtime, "_router", None)

        if router is not None:
            try:
                router.switch(provider_name, model=model)
                # Also update the runtime's active provider reference if possible
                if self._runtime is not None:
                    self._runtime.switch_provider(router.current)
            except ValueError as exc:
                return ToolResult(output=str(exc), is_error=True)

            model_info = f" with model '{model}'" if model else ""
            log.info(f"Switched to provider '{provider_name}'{model_info}")
            return ToolResult(
                output=(
                    f"Switched to provider '{provider_name}'{model_info}. "
                    f"All subsequent messages will use this provider."
                ),
                metadata={
                    "provider": provider_name,
                    "model": model or router.current_model,
                },
            )

        return ToolResult(
            output="Provider router is not available. Cannot switch models.",
            is_error=True,
        )


class ListModelsTool(BaseTool):
    """List all configured LLM providers and their available models.

    Useful for the agent to discover what providers/models are available
    before deciding whether to switch.
    """

    name = "list_models"
    description = (
        "List all configured LLM providers and their available models. "
        "Shows which provider is currently active and what alternatives exist."
    )
    category = ToolCategory.SESSION

    def __init__(self, router: Any = None, runtime: Any = None) -> None:
        """
        Args:
            router: A ProviderRouter instance to query.
            runtime: An AgentRuntime instance (alternative).
        """
        self._router = router
        self._runtime = runtime

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": (
                        "Optional: query models for a specific provider only. "
                        "If omitted, lists all configured providers."
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
        router = self._router
        if router is None and self._runtime is not None:
            router = getattr(self._runtime, "_router", None)

        if router is None:
            return ToolResult(
                output="Provider router is not available. Cannot list models.",
                is_error=True,
            )

        specific_provider = arguments.get("provider")

        # If a specific provider is requested, list its models
        if specific_provider:
            try:
                models = await router.list_models(specific_provider)
                return ToolResult(
                    output=(
                        f"Models for '{specific_provider}':\n"
                        + "\n".join(f"  - {m}" for m in models)
                    ),
                    metadata={"provider": specific_provider, "models": models},
                )
            except ValueError as exc:
                return ToolResult(output=str(exc), is_error=True)
            except Exception as exc:
                return ToolResult(
                    output=f"Error listing models for '{specific_provider}': {exc}",
                    is_error=True,
                )

        # List all configured providers
        providers = router.list_available()
        if not providers:
            return ToolResult(output="No providers configured.")

        lines = ["Configured LLM providers:\n"]
        for info in providers:
            active_marker = " [ACTIVE]" if info.is_active else ""
            configured_marker = "" if info.is_configured else " (not configured)"
            model_str = f", model: {info.default_model}" if info.default_model else ""
            lines.append(
                f"  - {info.name} (type: {info.provider_type}{model_str})"
                f"{active_marker}{configured_marker}"
            )

        return ToolResult(
            output="\n".join(lines),
            metadata={
                "providers": [
                    {
                        "name": p.name,
                        "type": p.provider_type,
                        "active": p.is_active,
                        "configured": p.is_configured,
                        "model": p.default_model,
                    }
                    for p in providers
                ],
            },
        )

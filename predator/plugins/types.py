"""Plugin API types — mirrors OpenClaw's plugins/types.ts.

Defines the plugin interface and registration API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from predator.hooks.types import HookEvent, HookHandler
from predator.tools.base import BaseTool


# ---------------------------------------------------------------------------
# Plugin config validation
# ---------------------------------------------------------------------------


class PluginConfigSchema(BaseModel):
    """Pydantic model for plugin configuration validation.

    Plugins declare their expected config shape by subclassing this model.
    The loader validates user-supplied config against the schema before
    passing it to the plugin.
    """

    class Config:
        extra = "forbid"


# ---------------------------------------------------------------------------
# Plugin commands
# ---------------------------------------------------------------------------


@dataclass
class PluginCommand:
    """A CLI / slash command registered by a plugin."""

    name: str
    description: str
    handler: Callable[..., Any]
    aliases: list[str] = field(default_factory=list)
    usage: str = ""


# ---------------------------------------------------------------------------
# Plugin manifest
# ---------------------------------------------------------------------------


class PluginState(str, Enum):
    """Runtime state of a loaded plugin."""

    DISCOVERED = "discovered"
    REGISTERED = "registered"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginManifest:
    """Plugin manifest — metadata and capabilities declaration."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    requires: list[str] = field(default_factory=list)  # Required system binaries
    config_schema: Optional[type[PluginConfigSchema]] = None


# ---------------------------------------------------------------------------
# Plugin API
# ---------------------------------------------------------------------------


class PluginAPI:
    """API available to plugins during registration and activation.

    Mirrors OpenClaw's OpenClawPluginApi with extension points:
    - registerTool()    — add AI tools
    - registerHook()    — hook into lifecycle events
    - registerCommand() — custom slash / CLI commands
    - registerService() — background services
    """

    def __init__(self) -> None:
        self._tools: list[BaseTool] = []
        self._hooks: list[tuple[str, HookHandler, int]] = []
        self._commands: list[PluginCommand] = []
        self._services: list[Callable] = []

    # -- registration helpers ------------------------------------------------

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool for the agent to use."""
        self._tools.append(tool)

    def register_hook(
        self,
        event: str | HookEvent,
        handler: HookHandler,
        priority: int = 100,
    ) -> None:
        """Register a lifecycle hook."""
        event_str = event.value if isinstance(event, HookEvent) else event
        self._hooks.append((event_str, handler, priority))

    def register_command(self, command: PluginCommand) -> None:
        """Register a slash / CLI command."""
        self._commands.append(command)

    def register_service(self, service_fn: Callable) -> None:
        """Register a background service."""
        self._services.append(service_fn)

    # -- accessors -----------------------------------------------------------

    @property
    def tools(self) -> list[BaseTool]:
        return self._tools

    @property
    def hooks(self) -> list[tuple[str, HookHandler, int]]:
        return self._hooks

    @property
    def commands(self) -> list[PluginCommand]:
        return self._commands

    @property
    def services(self) -> list[Callable]:
        return self._services


# ---------------------------------------------------------------------------
# Plugin base class
# ---------------------------------------------------------------------------


class PredatorPlugin:
    """Base class for PREDATOR plugins.

    Plugins can override:
    - register(api) — register tools, hooks, commands during discovery
    - activate(api) — activate services and runtime features
    - deactivate() — cleanup
    - get_status() — return health / state information
    """

    manifest: PluginManifest

    def register(self, api: PluginAPI) -> None:
        """Called during plugin discovery. Register tools and hooks here."""
        pass

    def activate(self, api: PluginAPI) -> None:
        """Called after all plugins are registered. Start services here."""
        pass

    def deactivate(self) -> None:
        """Called on shutdown. Cleanup resources here."""
        pass

    def get_status(self) -> dict[str, Any]:
        """Return health and state information for this plugin.

        Returns a dict that typically includes:
        - state: PluginState value
        - version: plugin version
        - Any plugin-specific diagnostics
        """
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "state": PluginState.ACTIVE.value,
        }

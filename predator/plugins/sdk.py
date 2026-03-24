"""Plugin SDK — convenience base class for building PREDATOR plugins.

Third-party and bundled plugins can inherit from ``PluginBase`` instead of
the lower-level ``PredatorPlugin``.  ``PluginBase`` auto-generates the
manifest from class attributes and wires up tool / hook registration so
that subclasses only need to override the ``tools`` and ``hooks``
properties.

Example::

    from predator.plugins.sdk import PluginBase

    class MyPlugin(PluginBase):
        id = "my-plugin"
        name = "My Plugin"
        version = "0.1.0"
        description = "Does something useful."

        @property
        def tools(self):
            return [MyTool()]

        @property
        def hooks(self):
            return [("agent_start", self._on_start, 50)]
"""

from __future__ import annotations

from typing import Any

from predator.hooks.types import HookHandler
from predator.plugins.types import (
    PluginAPI,
    PluginConfigSchema,
    PluginManifest,
    PluginState,
    PredatorPlugin,
)
from predator.tools.base import BaseTool


class PluginBase(PredatorPlugin):
    """Convenience base class for PREDATOR plugins.

    Subclasses declare metadata as class attributes and override the
    ``tools`` / ``hooks`` properties.  The ``register`` method
    automatically registers everything with the PluginAPI.
    """

    # -- override these in subclasses ----------------------------------------
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    requires: list[str] = []
    config_schema: type[PluginConfigSchema] | None = None

    # -- manifest auto-generation --------------------------------------------

    @property
    def manifest(self) -> PluginManifest:  # type: ignore[override]
        """Auto-generate the manifest from class attributes."""
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            requires=list(self.requires),
            config_schema=self.config_schema,
        )

    # -- extension points for subclasses ------------------------------------

    @property
    def tools(self) -> list[BaseTool]:
        """Override to return tool instances this plugin provides."""
        return []

    @property
    def hooks(self) -> list[tuple[str, HookHandler, int]]:
        """Override to return ``(event, handler, priority)`` tuples."""
        return []

    # -- lifecycle -----------------------------------------------------------

    def register(self, api: PluginAPI) -> None:
        """Auto-register all tools and hooks declared by the plugin."""
        for tool in self.tools:
            api.register_tool(tool)

        for event, handler, priority in self.hooks:
            api.register_hook(event, handler, priority)

    def activate(self, api: PluginAPI) -> None:
        """Called after all plugins are registered. Override if needed."""
        pass

    def deactivate(self) -> None:
        """Called on shutdown. Override to release resources."""
        pass

    def get_status(self) -> dict[str, Any]:
        """Return health/state dict for the plugin."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "state": PluginState.ACTIVE.value,
            "tools": [t.name for t in self.tools],
            "hooks": [h[0] for h in self.hooks],
        }

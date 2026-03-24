"""Plugin registry — tracks active plugins and their status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from predator.plugins.types import PredatorPlugin


@dataclass
class PluginRecord:
    """Record of a loaded plugin."""

    plugin: PredatorPlugin
    enabled: bool = True
    error: Optional[str] = None


class PluginRegistry:
    """Simple registry tracking plugin state."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginRecord] = {}

    def register(self, plugin: PredatorPlugin, enabled: bool = True) -> None:
        self._plugins[plugin.manifest.id] = PluginRecord(plugin=plugin, enabled=enabled)

    def get(self, plugin_id: str) -> Optional[PluginRecord]:
        return self._plugins.get(plugin_id)

    def is_enabled(self, plugin_id: str) -> bool:
        record = self._plugins.get(plugin_id)
        return record.enabled if record else False

    def list_all(self) -> list[PluginRecord]:
        return list(self._plugins.values())

    def list_enabled(self) -> list[PluginRecord]:
        return [r for r in self._plugins.values() if r.enabled]

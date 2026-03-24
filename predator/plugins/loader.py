"""Plugin loader — mirrors OpenClaw's plugins/loader.ts.

Discovers and loads plugins from:
- Bundled plugins (built-in)
- Global directory (~/.predator/plugins/)
- Workspace directory
- Config-specified paths
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from predator.config.paths import get_plugins_dir
from predator.plugins.types import (
    PluginAPI,
    PluginState,
    PredatorPlugin,
    PluginManifest,
)
from predator.utils.logger import get_logger

log = get_logger("plugins.loader")

# Path to bundled plugins shipped with PREDATOR
_BUNDLED_DIR = Path(__file__).parent / "bundled"


class PluginLoader:
    """Discovers and loads PREDATOR plugins.

    Mirrors OpenClaw's plugin discovery lifecycle:
    1. Scan directories for plugin modules
    2. Load and validate manifests
    3. Register phase (tools, hooks, commands)
    4. Activate phase (start services)
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PredatorPlugin] = {}
        self._disabled: set[str] = set()
        self._states: dict[str, PluginState] = {}
        self._api = PluginAPI()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, extra_dirs: Optional[list[str]] = None) -> list[str]:
        """Discover plugins from known directories."""
        discovered: list[str] = []

        # Bundled plugins
        discovered.extend(self._scan_directory(_BUNDLED_DIR))

        # Global plugins directory
        global_dir = get_plugins_dir()
        discovered.extend(self._scan_directory(global_dir))

        # Extra directories
        if extra_dirs:
            for d in extra_dirs:
                p = Path(d).expanduser().resolve()
                if p.is_dir():
                    discovered.extend(self._scan_directory(p))

        log.info(f"Discovered {len(discovered)} plugins")
        return discovered

    def discover_from_config(self, config: Any) -> list[str]:
        """Discover plugins specified in a config object.

        Expects *config* to expose ``plugins.entries`` — a list of dicts
        with at least a ``path`` key, e.g.::

            config.plugins.entries = [
                {"path": "~/my-plugins/scanner.py", "enabled": True},
            ]

        Returns the list of discovered plugin paths.
        """
        discovered: list[str] = []

        entries: list[dict[str, Any]] = []
        try:
            entries = getattr(getattr(config, "plugins", None), "entries", []) or []
        except Exception:
            pass

        for entry in entries:
            if isinstance(entry, dict):
                path_str = entry.get("path")
                enabled = entry.get("enabled", True)
                if not path_str or not enabled:
                    continue
                p = Path(path_str).expanduser().resolve()
                if p.exists():
                    discovered.append(str(p))
                else:
                    log.warning(f"Config plugin path not found: {path_str}")
            elif isinstance(entry, str):
                p = Path(entry).expanduser().resolve()
                if p.exists():
                    discovered.append(str(p))

        log.info(f"Discovered {len(discovered)} plugins from config")
        return discovered

    def _scan_directory(self, directory: Path) -> list[str]:
        """Scan a directory for plugin modules."""
        found: list[str] = []
        if not directory.is_dir():
            return found

        for entry in directory.iterdir():
            # Plugin as a Python file
            if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("_"):
                found.append(str(entry))
            # Plugin as a package directory
            elif entry.is_dir() and (entry / "__init__.py").exists():
                found.append(str(entry))

        return found

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, plugin_path: str) -> Optional[PredatorPlugin]:
        """Load a single plugin from a path."""
        path = Path(plugin_path)

        try:
            module = None
            if path.is_file():
                module_name = f"predator_plugin_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
            elif path.is_dir():
                module_name = f"predator_plugin_{path.name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, path / "__init__.py"
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
            else:
                log.warning(f"Plugin path not found: {plugin_path}")
                return None

            if module is None:
                log.warning(f"Could not create module for {plugin_path}")
                return None

            # Look for plugin class or factory
            plugin: Optional[PredatorPlugin] = None
            if hasattr(module, "plugin"):
                plugin = module.plugin
            elif hasattr(module, "Plugin"):
                plugin = module.Plugin()
            elif hasattr(module, "create_plugin"):
                plugin = module.create_plugin()

            if plugin and isinstance(plugin, PredatorPlugin):
                pid = plugin.manifest.id
                self._plugins[pid] = plugin
                self._states[pid] = PluginState.DISCOVERED
                log.info(f"Loaded plugin: {plugin.manifest.name} ({pid})")
                return plugin
            else:
                log.warning(f"No valid plugin found in {plugin_path}")
                return None

        except Exception as e:
            log.error(f"Failed to load plugin from {plugin_path}: {e}")
            return None

    def load_all_discovered(
        self,
        extra_dirs: Optional[list[str]] = None,
        config: Any = None,
    ) -> PluginAPI:
        """Discover, load, register, and activate all plugins in one call.

        Convenience method that chains the full lifecycle:
        discover -> load -> register -> activate.
        """
        paths = self.discover(extra_dirs)
        if config is not None:
            paths.extend(self.discover_from_config(config))

        for p in paths:
            self.load(p)

        self.register_all()
        self.activate_all()
        return self._api

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register_all(self) -> PluginAPI:
        """Run register phase on all loaded plugins."""
        for plugin_id, plugin in self._plugins.items():
            if plugin_id in self._disabled:
                continue
            try:
                plugin.register(self._api)
                self._states[plugin_id] = PluginState.REGISTERED
                log.debug(f"Plugin registered: {plugin_id}")
            except Exception as e:
                self._states[plugin_id] = PluginState.ERROR
                log.error(f"Plugin registration failed for {plugin_id}: {e}")
        return self._api

    def activate_all(self) -> None:
        """Run activate phase on all loaded plugins."""
        for plugin_id, plugin in self._plugins.items():
            if plugin_id in self._disabled:
                continue
            try:
                plugin.activate(self._api)
                self._states[plugin_id] = PluginState.ACTIVE
                log.debug(f"Plugin activated: {plugin_id}")
            except Exception as e:
                self._states[plugin_id] = PluginState.ERROR
                log.error(f"Plugin activation failed for {plugin_id}: {e}")

    def deactivate_all(self) -> None:
        """Deactivate all plugins."""
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.deactivate()
                self._states[plugin_id] = PluginState.DISCOVERED
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Plugin access & control
    # ------------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> Optional[PredatorPlugin]:
        """Return a loaded plugin by its id, or ``None``."""
        return self._plugins.get(plugin_id)

    def enable_plugin(self, plugin_id: str) -> bool:
        """Re-enable a previously disabled plugin.

        Returns ``True`` if the plugin was found and enabled.
        """
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            log.warning(f"Cannot enable unknown plugin: {plugin_id}")
            return False

        self._disabled.discard(plugin_id)
        # Run registration + activation for the re-enabled plugin
        try:
            plugin.register(self._api)
            plugin.activate(self._api)
            self._states[plugin_id] = PluginState.ACTIVE
            log.info(f"Plugin enabled: {plugin_id}")
            return True
        except Exception as e:
            self._states[plugin_id] = PluginState.ERROR
            log.error(f"Failed to enable plugin {plugin_id}: {e}")
            return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a loaded plugin (deactivate and mark disabled).

        Returns ``True`` if the plugin was found and disabled.
        """
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            log.warning(f"Cannot disable unknown plugin: {plugin_id}")
            return False

        try:
            plugin.deactivate()
        except Exception:
            pass

        self._disabled.add(plugin_id)
        self._states[plugin_id] = PluginState.DISABLED
        log.info(f"Plugin disabled: {plugin_id}")
        return True

    def get_status_all(self) -> dict[str, dict[str, Any]]:
        """Return status of every known plugin.

        Calls ``get_status()`` on each plugin and merges in the loader's
        own state tracking.
        """
        result: dict[str, dict[str, Any]] = {}
        for pid, plugin in self._plugins.items():
            try:
                status = plugin.get_status()
            except Exception:
                status = {}
            status["state"] = self._states.get(pid, PluginState.DISCOVERED).value
            status["enabled"] = pid not in self._disabled
            result[pid] = status
        return result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def api(self) -> PluginAPI:
        return self._api

    @property
    def loaded_plugins(self) -> dict[str, PredatorPlugin]:
        return self._plugins

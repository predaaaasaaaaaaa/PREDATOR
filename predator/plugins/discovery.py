"""Plugin discovery — scans multiple locations for PREDATOR plugins.

Discovery sources (checked in order):
1. ``~/.predator/plugins/`` — global user plugins
2. ``./plugins/`` — workspace-local plugins
3. Paths listed under ``plugins.paths`` in ``predator.yaml``

Each candidate directory must contain a ``plugin.yaml`` manifest that
conforms to :class:`PluginManifestSchema`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from predator.config.paths import get_plugins_dir
from predator.plugins.manifest import PluginManifestSchema
from predator.utils.logger import get_logger

log = get_logger("plugins.discovery")


class DiscoveredPlugin:
    """A plugin that has been found on disk but not yet loaded."""

    def __init__(self, path: Path, manifest: PluginManifestSchema) -> None:
        self.path = path
        self.manifest = manifest

    def __repr__(self) -> str:
        return f"<DiscoveredPlugin {self.manifest.id} @ {self.path}>"


def _load_manifest(plugin_dir: Path) -> Optional[PluginManifestSchema]:
    """Try to parse ``plugin.yaml`` inside *plugin_dir*."""
    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.is_file():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
        return PluginManifestSchema(**raw)
    except Exception as exc:
        log.warning(f"Invalid plugin.yaml in {plugin_dir}: {exc}")
        return None


def _scan_directory(directory: Path) -> list[DiscoveredPlugin]:
    """Scan *directory* for sub-directories that contain a ``plugin.yaml``."""
    results: list[DiscoveredPlugin] = []
    if not directory.is_dir():
        return results

    for entry in directory.iterdir():
        if not entry.is_dir():
            continue
        manifest = _load_manifest(entry)
        if manifest is not None:
            results.append(DiscoveredPlugin(path=entry, manifest=manifest))

    return results


def _read_config_paths(config_path: Optional[Path] = None) -> list[str]:
    """Read ``plugins.paths`` from ``predator.yaml`` (workspace root)."""
    candidates = [
        config_path,
        Path.cwd() / "predator.yaml",
        Path.cwd() / ".predator.yaml",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    cfg: dict[str, Any] = yaml.safe_load(fh) or {}
                return cfg.get("plugins", {}).get("paths", [])
            except Exception:
                pass
    return []


def discover_plugins(
    *,
    workspace_dir: Optional[Path] = None,
    config_path: Optional[Path] = None,
    extra_dirs: Optional[list[str]] = None,
) -> list[DiscoveredPlugin]:
    """Discover all available plugins across the standard search locations.

    Parameters
    ----------
    workspace_dir:
        Override for the current workspace root (defaults to cwd).
    config_path:
        Explicit path to ``predator.yaml`` if not in cwd.
    extra_dirs:
        Additional directories to scan (e.g. from CLI flags).

    Returns
    -------
    list[DiscoveredPlugin]
        All plugins found (including disabled ones — the loader decides
        whether to skip them).
    """
    workspace = workspace_dir or Path.cwd()
    discovered: list[DiscoveredPlugin] = []
    seen_ids: set[str] = set()

    def _add(plugins: list[DiscoveredPlugin]) -> None:
        for p in plugins:
            if p.manifest.id not in seen_ids:
                seen_ids.add(p.manifest.id)
                discovered.append(p)
            else:
                log.debug(
                    f"Skipping duplicate plugin '{p.manifest.id}' at {p.path}"
                )

    # 1. Global plugins directory (~/.predator/plugins/)
    _add(_scan_directory(get_plugins_dir()))

    # 2. Workspace-local plugins (./plugins/)
    _add(_scan_directory(workspace / "plugins"))

    # 3. Paths from predator.yaml config
    for extra in _read_config_paths(config_path):
        path = Path(extra).expanduser().resolve()
        _add(_scan_directory(path))

    # 4. Programmatically supplied extra directories
    if extra_dirs:
        for d in extra_dirs:
            _add(_scan_directory(Path(d).expanduser().resolve()))

    log.info(f"Discovered {len(discovered)} plugin(s)")
    return discovered

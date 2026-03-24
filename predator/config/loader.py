"""Configuration loader — mirrors OpenClaw's config/io.ts.

Handles YAML loading, env var substitution, validation, defaults,
config includes, and hot-reload support.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from predator.config.env import substitute_env_recursive
from predator.config.paths import get_config_path
from predator.config.schema import PredatorConfig
from predator.utils.logger import get_logger

log = get_logger("config")

# Cached config instance
_cached_config: Optional[PredatorConfig] = None
_cached_mtime: float = 0.0


def _resolve_includes(data: dict, base_dir: Path, seen: set[str] | None = None) -> dict:
    """Resolve 'includes' directives in config — prevents circular includes."""
    if seen is None:
        seen = set()

    includes = data.pop("includes", [])
    if not isinstance(includes, list):
        includes = [includes]

    for include_path in includes:
        resolved = (base_dir / include_path).resolve()
        key = str(resolved)
        if key in seen:
            log.warning(f"Circular include detected: {key}")
            continue
        seen.add(key)

        if resolved.is_file():
            with open(resolved) as f:
                included = yaml.safe_load(f) or {}
            included = _resolve_includes(included, resolved.parent, seen)
            # Merge: included values are defaults, main config overrides
            _deep_merge(data, included)

    return data


def _deep_merge(target: dict, source: dict) -> dict:
    """Deep merge source into target. Target values take precedence."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge(target[key], value)
        elif key not in target:
            target[key] = value
    return target


def load_config(
    config_path: Optional[str | Path] = None,
    force_reload: bool = False,
) -> PredatorConfig:
    """Load and validate the PREDATOR configuration.

    Mirrors OpenClaw's loadConfig():
    1. Resolve config file path
    2. Read & parse YAML
    3. Resolve includes
    4. Substitute env vars
    5. Validate with Pydantic schema
    6. Cache result
    """
    global _cached_config, _cached_mtime

    path = Path(config_path) if config_path else get_config_path()

    # Check cache
    if not force_reload and _cached_config is not None:
        try:
            current_mtime = path.stat().st_mtime if path.exists() else 0.0
            if current_mtime == _cached_mtime:
                return _cached_config
        except OSError:
            pass

    if not path.exists():
        log.info(f"No config file found at {path}, using defaults")
        _cached_config = PredatorConfig()
        _cached_mtime = 0.0
        return _cached_config

    log.info(f"Loading config from {path}")

    try:
        with open(path) as f:
            raw_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.error(f"Failed to parse config: {e}")
        _cached_config = PredatorConfig()
        return _cached_config

    # Resolve includes
    raw_data = _resolve_includes(raw_data, path.parent)

    # Env var substitution
    raw_data = substitute_env_recursive(raw_data)

    # Validate and create config
    try:
        config = PredatorConfig(**raw_data)
    except Exception as e:
        log.error(f"Config validation error: {e}")
        config = PredatorConfig()

    _cached_config = config
    try:
        _cached_mtime = path.stat().st_mtime
    except OSError:
        _cached_mtime = 0.0

    return config


def write_config(config: PredatorConfig, config_path: Optional[str | Path] = None) -> None:
    """Write configuration to YAML file."""
    path = Path(config_path) if config_path else get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude_none=True, exclude_defaults=False)

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    log.info(f"Config written to {path}")

    # Invalidate cache
    global _cached_config, _cached_mtime
    _cached_config = None
    _cached_mtime = 0.0


def create_default_config(config_path: Optional[str | Path] = None) -> PredatorConfig:
    """Create a default config file if one doesn't exist."""
    path = Path(config_path) if config_path else get_config_path()
    if path.exists():
        return load_config(path)

    config = PredatorConfig()
    write_config(config, path)
    return config

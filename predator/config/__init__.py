"""PREDATOR configuration system — mirrors OpenClaw's config/ module."""

from predator.config.loader import load_config
from predator.config.paths import get_state_dir, get_config_path
from predator.config.schema import PredatorConfig

__all__ = ["load_config", "get_state_dir", "get_config_path", "PredatorConfig"]

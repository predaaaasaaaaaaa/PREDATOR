"""Path resolution for PREDATOR state, config, and data — mirrors OpenClaw's config/paths.ts.

State directory: ~/.predator/ (or PREDATOR_STATE_DIR env)
Config file: ~/.predator/config.yaml
Sessions: ~/.predator/sessions/
Logs: ~/.predator/logs/
Plugins: ~/.predator/plugins/
Memory: ~/.predator/memory/
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_state_dir() -> Path:
    """Get the PREDATOR state directory (~/.predator by default).

    Supports profile isolation via PREDATOR_PROFILE env var.
    """
    base = os.environ.get("PREDATOR_STATE_DIR", os.path.expanduser("~/.predator"))
    profile = os.environ.get("PREDATOR_PROFILE")
    if profile:
        base = os.path.join(base, "profiles", profile)
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """Get the path to the config file."""
    # Check env override
    env_path = os.environ.get("PREDATOR_CONFIG")
    if env_path:
        return Path(env_path)
    return get_state_dir() / "config.yaml"


def get_sessions_dir(agent_id: str = "default") -> Path:
    """Get the sessions directory for an agent."""
    path = get_state_dir() / "agents" / agent_id / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    """Get the logs directory."""
    path = get_state_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_plugins_dir() -> Path:
    """Get the plugins directory."""
    path = get_state_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_memory_dir() -> Path:
    """Get the memory directory."""
    path = get_state_dir() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_skills_dir() -> Path:
    """Get the skills directory."""
    path = get_state_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_approvals_file() -> Path:
    """Get the exec approvals file."""
    return get_state_dir() / "approvals.json"


def get_device_key_path() -> Path:
    """Get the device private key path."""
    return get_state_dir() / "device.key"


def ensure_state_dirs() -> None:
    """Ensure all state subdirectories exist."""
    get_state_dir()
    get_logs_dir()
    get_plugins_dir()
    get_memory_dir()
    get_skills_dir()

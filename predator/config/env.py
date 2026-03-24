"""Environment variable handling — mirrors OpenClaw's config/env-substitution.ts.

Supports ${VAR_NAME} syntax in YAML config values with optional defaults.
"""

from __future__ import annotations

import os
import re
from typing import Any


# Pattern: ${VAR_NAME} or ${VAR_NAME:-default_value}
_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")


def substitute_env_vars(value: str) -> str:
    """Replace ${VAR} and ${VAR:-default} patterns with environment values."""

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        return match.group(0)  # Keep original if not found and no default

    return _ENV_PATTERN.sub(_replace, value)


def substitute_env_recursive(data: Any) -> Any:
    """Recursively substitute environment variables in a config structure."""
    if isinstance(data, str):
        return substitute_env_vars(data)
    elif isinstance(data, dict):
        return {k: substitute_env_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [substitute_env_recursive(item) for item in data]
    return data


# Key environment variables PREDATOR recognizes
ENV_VARS = {
    "PREDATOR_STATE_DIR": "Override state directory (~/.predator)",
    "PREDATOR_CONFIG": "Override config file path",
    "PREDATOR_PROFILE": "Use isolated profile",
    "PREDATOR_GATEWAY_PORT": "Override gateway port",
    "PREDATOR_GATEWAY_HOST": "Override gateway bind address",
    "PREDATOR_LOG_LEVEL": "Set log level (debug/info/warning/error)",
    "ANTHROPIC_API_KEY": "Anthropic (Claude) API key",
    "OPENAI_API_KEY": "OpenAI API key",
    "SHODAN_API_KEY": "Shodan API key",
    "HUNTER_API_KEY": "Hunter.io API key",
    "VIRUSTOTAL_API_KEY": "VirusTotal API key",
    "CENSYS_API_ID": "Censys API ID",
    "CENSYS_API_SECRET": "Censys API secret",
}

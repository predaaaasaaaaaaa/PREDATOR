"""Config CLI commands — mirrors OpenClaw's config management."""

from __future__ import annotations

import click
from rich.syntax import Syntax

from predator.cli.theme import console, print_header, print_success, print_error, print_warning, print_info


@click.group("config")
def config_group():
    """Manage PREDATOR configuration."""
    pass


@config_group.command("show")
def config_show():
    """Display the current configuration."""
    from predator.config.paths import get_config_path

    config_path = get_config_path()
    if config_path.exists():
        content = config_path.read_text()
        syntax = Syntax(content, "yaml", theme="monokai", line_numbers=True)
        console.print(syntax)
    else:
        print_warning("No config file found. Run 'predator setup' first.")


@config_group.command("path")
def config_path():
    """Show the config file path."""
    from predator.config.paths import get_config_path, get_state_dir

    console.print(f"Config file: {get_config_path()}")
    console.print(f"State dir:   {get_state_dir()}")


@config_group.command("get")
@click.argument("key")
def config_get(key):
    """Get a specific config value."""
    from predator.config.loader import load_config

    config = load_config()
    data = config.model_dump()

    # Navigate nested keys (e.g., "agent.model")
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            print_error(f"Key not found: {key}")
            return

    if isinstance(current, (dict, list)):
        import json
        console.print_json(json.dumps(current))
    else:
        console.print(str(current))


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value."""
    import yaml

    from predator.config.paths import get_config_path

    config_path = get_config_path()

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Navigate and set nested key
    parts = key.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    print_success(f"Set {key} = {value}")


@config_group.command("reset")
@click.confirmation_option(prompt="Reset config to defaults?")
def config_reset():
    """Reset configuration to defaults."""
    from predator.config.loader import create_default_config

    create_default_config()
    print_success("Config reset to defaults")

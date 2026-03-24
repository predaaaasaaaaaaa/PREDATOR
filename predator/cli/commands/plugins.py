"""Plugins CLI commands — manage PREDATOR plugins."""

from __future__ import annotations

import click
from rich.table import Table

from predator.cli.theme import console, print_header, print_success, print_error, print_warning, print_info


@click.group("plugins")
def plugins_group():
    """Manage PREDATOR plugins."""
    pass


@plugins_group.command("list")
def plugins_list():
    """List installed plugins."""
    from predator.plugins.loader import PluginLoader

    loader = PluginLoader()
    discovered = loader.discover()

    if discovered:
        console.print(f"[bold #FF0033]Found {len(discovered)} plugin(s):[/]")
        for path in discovered:
            console.print(f"  - {path}")
    else:
        console.print("[dim]No plugins installed[/dim]")
        console.print("[dim]Place plugins in ~/.predator/plugins/[/dim]")


@plugins_group.command("install")
@click.argument("path")
def plugins_install(path):
    """Install a plugin from a path."""
    from predator.plugins.loader import PluginLoader

    loader = PluginLoader()
    plugin = loader.load(path)
    if plugin:
        print_success(f"Installed: {plugin.manifest.name} v{plugin.manifest.version}")
    else:
        print_error(f"Failed to install plugin from {path}")

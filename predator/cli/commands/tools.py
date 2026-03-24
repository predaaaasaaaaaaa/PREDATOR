"""Tools CLI commands — list and inspect available tools."""

from __future__ import annotations

import click
from rich.table import Table

from predator.cli.theme import console, print_error, print_header, print_info, print_success, print_warning

RED = "#FF0033"
GREEN = "#00FF41"
CYAN = "#00D4FF"
DIM = "#666666"
AMBER = "#FFB300"


@click.group("tools")
def tools_group():
    """Manage and inspect PREDATOR tools."""
    pass


@tools_group.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
def tools_list(category):
    """List all registered tools."""
    from predator.tools.base import ToolCategory
    from predator.tools.registry import create_default_registry

    registry = create_default_registry()
    tools = registry.get_all()

    if category:
        try:
            cat = ToolCategory(category)
            tools = [t for t in tools if t.category == cat]
        except ValueError:
            print_error(f"Unknown category: {category}")
            console.print(f"Valid: {', '.join(c.value for c in ToolCategory)}")
            return

    table = Table(title=f"[bold {RED}]PREDATOR Tools ({len(tools)})[/]", border_style=DIM)
    table.add_column("Name", style=f"bold {CYAN}")
    table.add_column("Category", style=CYAN)
    table.add_column("Description", max_width=60)
    table.add_column("Approval", style="dim")

    for tool in sorted(tools, key=lambda t: (t.category.value, t.name)):
        approval = f"[{AMBER}]required[/]" if tool.requires_approval else ""
        table.add_row(
            tool.name,
            tool.category.value,
            tool.description[:60] + "..." if len(tool.description) > 60 else tool.description,
            approval,
        )

    console.print(table)

    # Summary
    summary = registry.summary()
    parts = [f"{cat}: {count}" for cat, count in sorted(summary.items())]
    console.print(f"\n[dim]{' | '.join(parts)}[/dim]")


@tools_group.command("info")
@click.argument("tool_name")
def tools_info(tool_name):
    """Show detailed information about a tool."""
    from predator.tools.registry import create_default_registry

    registry = create_default_registry()
    tool = registry.get(tool_name)

    if tool is None:
        print_error(f"Tool '{tool_name}' not found")
        return

    console.print(f"[bold {RED}]{tool.name}[/]")
    console.print(f"Category: [{CYAN}]{tool.category.value}[/]")
    console.print(f"Approval required: {'Yes' if tool.requires_approval else 'No'}")
    console.print(f"\n{tool.description}\n")

    # Parameters
    params = tool.get_parameters()
    properties = params.get("properties", {})
    required = params.get("required", [])

    if properties:
        console.print(f"[bold {RED}]Parameters:[/]")
        for name, schema in properties.items():
            req = f" [{RED}]*[/]" if name in required else ""
            ptype = schema.get("type", "any")
            desc = schema.get("description", "")
            console.print(f"  {name}{req} ({ptype}): {desc}")


@tools_group.command("detect")
def tools_detect():
    """Detect installed security tools on the system."""
    from predator.utils.platform import detect_platform

    info = detect_platform()

    table = Table(title=f"[bold {RED}]Detected Tools ({len(info.available_tools)})[/]", border_style=DIM)
    table.add_column("Tool", style=f"bold {CYAN}")
    table.add_column("Path", style="dim")

    for name, path in sorted(info.available_tools.items()):
        table.add_row(name, path)

    console.print(table)

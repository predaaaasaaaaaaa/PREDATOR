"""Subagent CLI commands — manage and monitor PREDATOR subagents.

Mirrors OpenClaw's commands-subagents.ts for user-facing subagent management.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import click
from rich.panel import Panel
from rich.table import Table

from predator.cli.theme import console, print_error, print_info, print_success, print_warning

RED = "#FF0033"
GREEN = "#00FF41"
CYAN = "#00D4FF"
AMBER = "#FFB300"
DIM = "#666666"


@click.group("subagents")
def subagents_group():
    """Manage PREDATOR subagents — list, kill, monitor spawned agents."""
    pass


@subagents_group.command("list")
@click.option("--parent", "-p", default="", help="Filter by parent session key")
@click.option("--active", "-a", is_flag=True, help="Show only active subagents")
def subagents_list(parent: str, active: bool):
    """List all spawned subagents and their status."""
    from predator.agents.subagent import get_spawner

    spawner = get_spawner()

    if parent:
        records = spawner.get_children(parent)
    else:
        records = spawner.get_all_records()

    if active:
        records = [r for r in records if not r.is_done]

    if not records:
        console.print(f"[{DIM}]No subagents found.[/]")
        return

    table = Table(
        title=f"[bold {RED}]PREDATOR Subagents ({len(records)})[/]",
        border_style=DIM,
    )
    table.add_column("ID", style=f"bold {CYAN}")
    table.add_column("Label", style="bold")
    table.add_column("State", style="dim")
    table.add_column("Parent", style="dim", max_width=25)
    table.add_column("Depth", style="dim")
    table.add_column("Time", style="dim")
    table.add_column("Tokens", style="dim")

    state_colors = {
        "pending": AMBER,
        "running": CYAN,
        "completed": GREEN,
        "failed": RED,
        "cancelled": DIM,
        "timeout": AMBER,
    }

    for r in records:
        color = state_colors.get(r.state.value, DIM)
        table.add_row(
            r.run_id,
            r.label,
            f"[{color}]{r.state.value.upper()}[/]",
            r.parent_session_key[:25],
            str(r.spawn_depth),
            f"{r.elapsed:.1f}s",
            str(r.total_tokens),
        )

    console.print(table)


@subagents_group.command("info")
@click.argument("run_id")
def subagents_info(run_id: str):
    """Show detailed info about a specific subagent."""
    from predator.agents.subagent import get_spawner

    spawner = get_spawner()
    record = spawner.registry.get(run_id)

    if not record:
        print_error(f"Subagent {run_id} not found")
        return

    state_colors = {
        "completed": GREEN, "failed": RED, "running": CYAN,
        "pending": AMBER, "timeout": AMBER, "cancelled": DIM,
    }
    color = state_colors.get(record.state.value, DIM)

    console.print(Panel(
        f"[bold {RED}]Subagent: {record.label}[/]\n"
        f"[{DIM}]Run ID:[/]  [{CYAN}]{record.run_id}[/]\n"
        f"[{DIM}]State:[/]   [{color}]{record.state.value.upper()}[/]\n"
        f"[{DIM}]Session:[/] {record.session_key}\n"
        f"[{DIM}]Parent:[/]  {record.parent_session_key}\n"
        f"[{DIM}]Depth:[/]   {record.spawn_depth}\n"
        f"[{DIM}]Model:[/]   {record.model or 'default'}\n"
        f"[{DIM}]Time:[/]    {record.elapsed:.1f}s\n"
        f"[{DIM}]Tokens:[/]  {record.total_tokens}\n"
        f"[{DIM}]Turns:[/]   {record.turns}\n\n"
        f"[bold {RED}]Task:[/]\n{record.task[:500]}\n\n"
        + (f"[bold {GREEN}]Result:[/]\n{record.result_text[:1000]}" if record.result_text else "")
        + (f"[bold {RED}]Error:[/]\n{record.error}" if record.error else ""),
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))


@subagents_group.command("kill")
@click.argument("run_id")
def subagents_kill(run_id: str):
    """Kill a running subagent."""
    from predator.agents.subagent import get_spawner

    spawner = get_spawner()

    killed = asyncio.get_event_loop().run_until_complete(
        spawner.kill(run_id)
    )

    if killed:
        print_success(f"Subagent {run_id} terminated")
    else:
        print_error(f"Could not kill subagent {run_id} — may be finished or not found")

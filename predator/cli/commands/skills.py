"""Skills CLI commands — list and inspect available skills."""

from __future__ import annotations

import click
from rich.table import Table

from predator.cli.theme import console, print_error, print_header, print_info, print_success, print_warning

RED = "#FF0033"
CYAN = "#00D4FF"
DIM = "#666666"


@click.group("skills")
def skills_group():
    """Manage PREDATOR skills."""
    pass


@skills_group.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
def skills_list(category):
    """List all available skills."""
    from predator.skills.loader import SkillLoader

    loader = SkillLoader()
    loader.load_defaults()

    skills = loader.get_all()
    if category:
        skills = [s for s in skills if s.category == category]

    if skills:
        table = Table(title=f"[bold {RED}]PREDATOR Skills ({len(skills)})[/]", border_style=DIM)
        table.add_column("ID", style=f"bold {CYAN}")
        table.add_column("Name")
        table.add_column("Category", style=CYAN)
        table.add_column("Description", max_width=50)

        for skill in sorted(skills, key=lambda s: s.category):
            table.add_row(skill.id, skill.name, skill.category, skill.description[:50])

        console.print(table)
    else:
        console.print("[dim]No skills found[/dim]")


@skills_group.command("info")
@click.argument("skill_id")
def skills_info(skill_id):
    """Show detailed information about a skill."""
    from predator.skills.loader import SkillLoader

    loader = SkillLoader()
    loader.load_defaults()

    skill = loader.get(skill_id)
    if skill is None:
        print_error(f"Skill '{skill_id}' not found")
        return

    console.print(f"[bold {RED}]{skill.name}[/] ({skill.id})")
    console.print(f"Category: [{CYAN}]{skill.category}[/]")
    console.print(f"Version: {skill.version}")
    if skill.author:
        console.print(f"Author: {skill.author}")
    if skill.tags:
        console.print(f"Tags: {', '.join(skill.tags)}")
    if skill.requires:
        console.print(f"Requires: {', '.join(skill.requires)}")
    console.print(f"\n{skill.description}\n")
    console.print(f"[bold {RED}]Prompt:[/]")
    console.print(skill.prompt[:500])

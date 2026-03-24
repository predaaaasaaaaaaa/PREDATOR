"""Setup command — mirrors OpenClaw's onboard/setup wizard."""

from __future__ import annotations

import os
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from predator.cli.theme import (
    SHARK_SMALL,
    console,
    print_error,
    print_header,
    print_info,
    print_separator,
    print_success,
    print_warning,
)
from predator.config.loader import create_default_config, write_config
from predator.config.paths import ensure_state_dirs, get_config_path, get_state_dir
from predator.config.schema import AuthProfile, PredatorConfig
from predator.version import __version__

RED = "#FF0033"
GREEN = "#00FF41"
CYAN = "#00D4FF"
DIM = "#666666"


@click.command("setup")
@click.option("--non-interactive", is_flag=True, help="Skip interactive prompts")
def setup_cmd(non_interactive):
    """Initialize PREDATOR — create config, set up API keys, verify tools.

    Interactive setup wizard that mirrors OpenClaw's onboard command.
    """
    console.print()
    console.print(SHARK_SMALL)
    console.print(
        Panel(
            f"[bold {RED}]PREDATOR[/] [{DIM}]// Setup Wizard[/]\n"
            f"[{DIM}]v{__version__}[/]",
            border_style=RED,
        )
    )
    print_separator()
    console.print()

    # Create state directories
    console.print(f"[bold {RED}]1.[/] [{CYAN}]Creating state directories...[/]")
    ensure_state_dirs()
    state_dir = get_state_dir()
    console.print(f"   State directory: {state_dir}")
    print_success("Done")
    console.print()

    # Config file
    config_path = get_config_path()
    console.print(f"[bold {RED}]2.[/] [{CYAN}]Configuration file...[/]")

    if config_path.exists():
        console.print(f"   Config already exists at: {config_path}")
        if not non_interactive and not Confirm.ask("   Overwrite existing config?", default=False):
            console.print("   Keeping existing config")
            config = PredatorConfig()
        else:
            config = PredatorConfig()
            write_config(config, config_path)
            print_success(f"Config created at {config_path}")
    else:
        config = create_default_config(config_path)
        console.print(f"   [{GREEN}]Config created at {config_path}[/]")

    console.print()

    # API Keys
    console.print(f"[bold {RED}]3.[/] [{CYAN}]LLM Provider Setup...[/]")

    if not non_interactive:
        # Anthropic
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            console.print(f"   Anthropic API key found in environment: ...{anthropic_key[-8:]}")
        else:
            key = Prompt.ask(
                "   Enter your Anthropic API key (or press Enter to skip)",
                default="",
                show_default=False,
            )
            if key:
                config.providers.profiles["anthropic"] = AuthProfile(
                    provider="anthropic", api_key=key
                )
                write_config(config, config_path)
                print_success("Anthropic key saved")
            else:
                print_warning("Skipped — set ANTHROPIC_API_KEY env var later")

        # OpenAI (optional)
        if Confirm.ask("   Set up OpenAI as well?", default=False):
            key = Prompt.ask("   Enter your OpenAI API key", default="")
            if key:
                config.providers.profiles["openai"] = AuthProfile(
                    provider="openai", api_key=key
                )
                write_config(config, config_path)
                print_success("OpenAI key saved")
    else:
        console.print("   [dim]Non-interactive mode — configure API keys manually[/dim]")

    console.print()

    # Tool detection
    console.print(f"[bold {RED}]4.[/] [{CYAN}]Detecting installed security tools...[/]")
    try:
        from predator.utils.platform import detect_platform

        info = detect_platform()
        console.print(f"   Distribution: {info.distro} {'(Kali Linux!)' if info.is_kali else ''}")
        console.print(f"   Root: {'Yes' if info.is_root else 'No'}")
        console.print(f"   Tools found: {len(info.available_tools)}")

        if info.available_tools:
            # Group by category
            categories = {}
            from predator.utils.platform import KNOWN_TOOLS

            for name in sorted(info.available_tools.keys()):
                categories.setdefault("tools", []).append(name)

            tools_str = ", ".join(sorted(info.available_tools.keys()))
            print_success(tools_str)
        else:
            print_warning("No security tools detected — install with apt")
    except Exception as e:
        print_warning(f"Platform detection skipped: {e}")

    console.print()

    # Done
    console.print(
        Panel(
            f"[bold {GREEN}]Setup complete![/]\n\n"
            f"[bold {RED}]Next steps:[/]\n"
            f"  [{GREEN}]$[/] [bold]predator agent -m 'scan example.com'[/]  [{DIM}]Talk to the agent[/]\n"
            f"  [{GREEN}]$[/] [bold]predator gateway run[/]                  [{DIM}]Start the gateway[/]\n"
            f"  [{GREEN}]$[/] [bold]predator doctor[/]                       [{DIM}]Verify system health[/]\n"
            f"  [{GREEN}]$[/] [bold]predator configure[/]                    [{DIM}]Set up channels & more[/]\n"
            f"  [{GREEN}]$[/] [bold]predator tools list[/]                   [{DIM}]List available tools[/]",
            border_style=GREEN,
            title=f"[bold {RED}]PREDATOR[/]",
            title_align="left",
        )
    )

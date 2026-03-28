"""CLI program — mirrors OpenClaw's cli/program.ts using Click.

This is the main CLI entry point that registers all commands.
Uses Click instead of Commander.js, with lazy loading for fast startup.
"""

from __future__ import annotations

import click

from predator.cli.theme import console, print_banner
from predator.version import __version__


class PredatorGroup(click.Group):
    """Custom Click group with lazy command loading.

    Mirrors OpenClaw's lazy command registration pattern.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lazy_commands: dict[str, str] = {
            "gateway": "predator.cli.commands.gateway:gateway_group",
            "agent": "predator.cli.commands.agent:agent_cmd",
            "setup": "predator.cli.commands.setup:setup_cmd",
            "configure": "predator.cli.commands.configure:configure_cmd",
            "config": "predator.cli.commands.config_cmd:config_group",
            "doctor": "predator.cli.commands.doctor:doctor_cmd",
            "sessions": "predator.cli.commands.sessions:sessions_group",
            "tools": "predator.cli.commands.tools:tools_group",
            "skills": "predator.cli.commands.skills:skills_group",
            "plugins": "predator.cli.commands.plugins:plugins_group",
            "scan": "predator.cli.commands.scan:scan_group",
            "channels": "predator.cli.commands.channels:channels_group",
            "daemon": "predator.cli.commands.daemon:daemon_group",
            "subagents": "predator.cli.commands.subagents:subagents_group",
        }

    def list_commands(self, ctx):
        commands = list(super().list_commands(ctx))
        commands.extend(sorted(self._lazy_commands.keys()))
        return sorted(set(commands))

    def get_command(self, ctx, cmd_name):
        cmd = super().get_command(ctx, cmd_name)
        if cmd:
            return cmd

        if cmd_name in self._lazy_commands:
            import importlib

            module_path, attr_name = self._lazy_commands[cmd_name].rsplit(":", 1)
            try:
                module = importlib.import_module(module_path)
                return getattr(module, attr_name)
            except (ImportError, AttributeError) as e:
                console.print(f"[error]Failed to load command '{cmd_name}': {e}[/error]")
                return None
        return None


@click.group(cls=PredatorGroup, invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--debug", is_flag=True, help="Enable debug output")
@click.option("--profile", type=str, help="Use isolated profile")
@click.version_option(__version__, prog_name="PREDATOR")
@click.pass_context
def cli(ctx, verbose, debug, profile):
    """PREDATOR — Autonomous AI Agent for Ethical Hackers & Cybersecurity Professionals.

    Run security tools, OSINT reconnaissance, and penetration testing
    with an autonomous AI agent that has full access to your Linux system.

    \b
    Quick start:
      predator setup                 Initialize PREDATOR
      predator configure             Interactive setup wizard (channels, providers, etc.)
      predator configure channels    Set up Telegram, Discord, Slack, etc.
      predator agent -m "..."        Send a message to the agent
      predator gateway run           Start the gateway server
      predator scan osint <target>   Run OSINT reconnaissance
      predator scan ports <target>   Port scan a target
      predator scan social <user>    Hunt social media profiles
      predator channels list         Show connected channels
      predator doctor                Check system health
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug

    if verbose or debug:
        from predator.utils.logger import setup_logging
        setup_logging(verbose=verbose, debug=debug)

    if ctx.invoked_subcommand is None:
        print_banner()
        console.print(f"[dim]  v{__version__}[/dim]")
        console.print()
        console.print("  [dim #CC0029]$[/] [bold #FF0033]predator --help[/]           [dim]Show all commands[/]")
        console.print("  [dim #CC0029]$[/] [bold #FF0033]predator setup[/]            [dim]Initialize PREDATOR[/]")
        console.print("  [dim #CC0029]$[/] [bold #FF0033]predator agent -m \"...\"[/]   [dim]Talk to the agent[/]")
        console.print("  [dim #CC0029]$[/] [bold #FF0033]predator gateway start[/]    [dim]Start the gateway[/]")
        console.print()

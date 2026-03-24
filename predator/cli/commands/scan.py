"""Scan commands — quick-access shortcuts for common OSINT and pentesting operations.

These are convenience commands that wrap the agent with pre-built prompts.
"""

from __future__ import annotations

import asyncio
import sys

import click

from predator.cli.theme import console, print_header, print_success, print_error, print_warning, print_info


def _run_agent_with_prompt(prompt: str):
    """Helper to run the agent with a pre-built prompt."""

    async def _run():
        from predator.agents.runtime import AgentRuntime
        from predator.config.loader import load_config
        from predator.providers.anthropic import AnthropicProvider
        from predator.providers.openai import OpenAIProvider
        from predator.providers.ollama import OllamaProvider
        from predator.sessions.transcript import SessionTranscript
        from predator.tools.registry import create_default_registry

        config = load_config()

        default_provider = config.providers.default
        if default_provider == "openai":
            provider = OpenAIProvider()
        elif default_provider == "ollama":
            provider = OllamaProvider()
        else:
            provider = AnthropicProvider(default_model=config.agent.model)

        if not provider.is_configured():
            print_error("No LLM provider configured. Run 'predator setup' first.")
            sys.exit(1)

        registry = create_default_registry()
        transcript = SessionTranscript("scan", "default")

        def on_text(text: str):
            console.print(text, end="", highlight=False)

        def on_tool_start(tool_id: str, name: str, args: dict):
            console.print(f"\n[bold yellow]▶ {name}[/bold yellow]")

        def on_tool_end(tool_id: str, name: str, is_error: bool):
            status = "[red]✗[/red]" if is_error else "[green]✓[/green]"
            console.print(f"  {status} {name}")

        runtime = AgentRuntime(
            provider=provider,
            registry=registry,
            config=config,
            transcript=transcript,
            on_text=on_text,
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
        )

        result = await runtime.run(message=prompt)
        console.print(
            f"\n\n[dim]─── {len(result.turns)} turns | "
            f"{result.total_tokens} tokens | "
            f"{result.total_elapsed:.1f}s ───[/dim]"
        )

    asyncio.run(_run())


@click.group("scan")
def scan_group():
    """Quick-access scanning and reconnaissance commands."""
    pass


@scan_group.command("osint")
@click.argument("target")
@click.option("--passive-only", is_flag=True, help="Only passive recon (no active scanning)")
def scan_osint(target, passive_only):
    """Run comprehensive OSINT reconnaissance on a target.

    \b
    Examples:
      predator scan osint example.com
      predator scan osint john.doe@email.com
      predator scan osint johndoe_username
      predator scan osint 192.168.1.1
    """
    mode = "passive-only" if passive_only else "comprehensive passive and active"
    prompt = (
        f"Perform a {mode} OSINT reconnaissance on the target: {target}\n\n"
        "Follow this methodology:\n"
        "1. Determine the target type (domain, email, username, IP)\n"
        "2. Run appropriate passive recon tools (WHOIS, DNS, theHarvester, etc.)\n"
        "3. Enumerate subdomains if it's a domain\n"
        "4. Search for associated social media accounts\n"
        "5. Check for data breaches if it's an email\n"
        "6. Correlate all findings\n"
        "7. Present a structured summary of intelligence gathered\n\n"
        "Use all available tools and be thorough."
    )
    _run_agent_with_prompt(prompt)


@scan_group.command("ports")
@click.argument("target")
@click.option("--ports", "-p", default="1-1000", help="Port range")
@click.option("--aggressive", is_flag=True, help="Aggressive scan with version/OS detection")
def scan_ports(target, ports, aggressive):
    """Run port scan on a target."""
    scan_type = "aggressive (-A)" if aggressive else "SYN"
    prompt = (
        f"Run a {scan_type} Nmap port scan on {target} for ports {ports}.\n"
        "Detect services and versions. Summarize findings with:\n"
        "- Open ports and services\n"
        "- Service versions\n"
        "- Potential vulnerabilities based on versions\n"
        "- Recommendations"
    )
    _run_agent_with_prompt(prompt)


@scan_group.command("subdomains")
@click.argument("domain")
def scan_subdomains(domain):
    """Enumerate subdomains of a domain."""
    prompt = (
        f"Enumerate all subdomains of {domain} using multiple tools:\n"
        "1. Use Sublist3r or Amass for passive enumeration\n"
        "2. Use theHarvester to find additional subdomains\n"
        "3. Try DNS zone transfer (dnsrecon -t axfr)\n"
        "4. Compile a deduplicated list of all discovered subdomains\n"
        "5. Resolve each subdomain to an IP address\n"
        "6. Present results in a clean table format"
    )
    _run_agent_with_prompt(prompt)


@scan_group.command("social")
@click.argument("username")
def scan_social(username):
    """Search for a username across social media platforms."""
    prompt = (
        f"Search for the username '{username}' across all social media platforms.\n"
        "Use Sherlock to check 400+ websites.\n"
        "Present found accounts with URLs in a clean list."
    )
    _run_agent_with_prompt(prompt)


@scan_group.command("vuln")
@click.argument("target")
def scan_vuln(target):
    """Run vulnerability scan on a target."""
    prompt = (
        f"Run a vulnerability assessment on {target}:\n"
        "1. Port scan to identify services\n"
        "2. Service version detection\n"
        "3. Search for known CVEs using searchsploit\n"
        "4. Run Nikto if it's a web server\n"
        "5. Summarize vulnerabilities by severity (Critical/High/Medium/Low)\n"
        "6. Provide remediation recommendations"
    )
    _run_agent_with_prompt(prompt)

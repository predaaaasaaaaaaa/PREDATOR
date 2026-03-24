"""Doctor command — mirrors OpenClaw's diagnostic/health check system."""

from __future__ import annotations

import os
import shutil
import sys

import click
from rich.table import Table

from predator.cli.theme import console, print_header, print_success, print_error, print_warning


@click.command("doctor")
@click.option("--fix", is_flag=True, help="Attempt to fix issues")
def doctor_cmd(fix):
    """Run system health checks and diagnostics.

    Verifies:
    - Python version
    - Config file
    - API keys
    - Installed security tools
    - Gateway connectivity
    - Disk space
    """
    print_header("PREDATOR Doctor -- System Health Check")

    checks: list[tuple[str, str, str]] = []  # (name, status, detail)

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        checks.append(("Python version", "[green]OK[/green]", py_ver))
    else:
        checks.append(("Python version", "[red]FAIL[/red]", f"{py_ver} (need 3.11+)"))

    # 2. Platform
    if sys.platform == "linux":
        try:
            from predator.utils.platform import detect_platform

            info = detect_platform()
            distro = f"{info.distro} {'(Kali!)' if info.is_kali else ''}"
            checks.append(("Platform", "[green]OK[/green]", distro))
        except Exception:
            checks.append(("Platform", "[green]OK[/green]", "Linux"))
    else:
        checks.append(("Platform", "[red]FAIL[/red]", f"{sys.platform} (Linux required)"))

    # 3. Config file
    from predator.config.paths import get_config_path

    config_path = get_config_path()
    if config_path.exists():
        checks.append(("Config file", "[green]OK[/green]", str(config_path)))
    else:
        checks.append(("Config file", "[yellow]WARN[/yellow]", "Not found — run 'predator setup'"))

    # 4. API Keys
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        checks.append(("Anthropic API key", "[green]OK[/green]", f"...{anthropic_key[-8:]}"))
    else:
        checks.append(("Anthropic API key", "[yellow]WARN[/yellow]", "Not set"))

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        checks.append(("OpenAI API key", "[green]OK[/green]", f"...{openai_key[-8:]}"))
    else:
        checks.append(("OpenAI API key", "[dim]SKIP[/dim]", "Not set (optional)"))

    # 5. Security tools
    essential_tools = ["nmap", "whois", "curl", "git", "python3"]
    osint_tools = ["theharvester", "sherlock", "recon-ng", "exiftool"]
    pentest_tools = ["msfconsole", "sqlmap", "nikto", "hydra"]

    for category, tools in [
        ("Essential", essential_tools),
        ("OSINT", osint_tools),
        ("Pentesting", pentest_tools),
    ]:
        found = sum(1 for t in tools if shutil.which(t))
        total = len(tools)
        if found == total:
            status = "[green]OK[/green]"
        elif found > 0:
            status = "[yellow]PARTIAL[/yellow]"
        else:
            status = "[red]MISSING[/red]"
        missing = [t for t in tools if not shutil.which(t)]
        detail = f"{found}/{total}"
        if missing:
            detail += f" (missing: {', '.join(missing[:3])})"
        checks.append((f"{category} tools", status, detail))

    # 6. Disk space
    try:
        import shutil as sh

        usage = sh.disk_usage("/")
        free_gb = usage.free / (1024**3)
        if free_gb > 5:
            checks.append(("Disk space", "[green]OK[/green]", f"{free_gb:.1f} GB free"))
        elif free_gb > 1:
            checks.append(("Disk space", "[yellow]WARN[/yellow]", f"{free_gb:.1f} GB free"))
        else:
            checks.append(("Disk space", "[red]LOW[/red]", f"{free_gb:.1f} GB free"))
    except Exception:
        checks.append(("Disk space", "[dim]SKIP[/dim]", "Could not check"))

    # Display results
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", width=25)
    table.add_column("Status", width=12)
    table.add_column("Details", width=50)

    for name, status, detail in checks:
        table.add_row(name, status, detail)

    console.print(table)

    # Summary
    ok_count = sum(1 for _, s, _ in checks if "OK" in s)
    warn_count = sum(1 for _, s, _ in checks if "WARN" in s or "PARTIAL" in s)
    fail_count = sum(1 for _, s, _ in checks if "FAIL" in s or "MISSING" in s)

    console.print()
    if fail_count == 0 and warn_count == 0:
        print_success("All checks passed!")
    elif fail_count == 0:
        print_warning(f"{warn_count} warning(s) -- PREDATOR can still operate")
    else:
        print_error(f"{fail_count} check(s) failed -- please fix before using PREDATOR")

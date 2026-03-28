"""PREDATOR visual theme — hacker-friendly CLI design.

Color palette inspired by Kali Linux, Metasploit, and the cyberpunk aesthetic.
The brand identity: BLACK SHARK with RED EYES.

Base: Dark/black backgrounds (terminal default)
Primary: Red (#FF0033) — brand, shark eyes, critical findings
Secondary: Neon green (#00FF41) — success, data, terminal hacker feel
Accent: Cyan (#00D4FF) — info, links, tool names
Warning: Amber (#FFB300) — warnings, caution
Dim: Gray (#666666) — metadata, timestamps, secondary info
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme
from rich.style import Style

# PREDATOR color palette
PREDATOR_THEME = Theme({
    # Brand
    "predator": "bold #FF0033",           # Red — brand color
    "predator.name": "bold #FF0033",      # PREDATOR name
    "predator.dim": "#CC0029",            # Darker red

    # Status
    "success": "bold #00FF41",            # Neon green
    "error": "bold #FF0033",              # Red
    "warning": "bold #FFB300",            # Amber
    "info": "#00D4FF",                    # Cyan

    # Tool output
    "tool.name": "bold #00D4FF",          # Cyan — tool names
    "tool.running": "bold #FFB300",       # Amber — executing
    "tool.success": "#00FF41",            # Green — completed
    "tool.error": "#FF0033",              # Red — failed
    "tool.output": "#E0E0E0",            # Light gray — output text

    # OSINT specific
    "osint.finding": "bold #00FF41",      # Green — important findings
    "osint.target": "bold #FF0033",       # Red — targets
    "osint.data": "#00D4FF",              # Cyan — data points
    "osint.meta": "dim #888888",          # Gray — metadata

    # Scan output
    "scan.port_open": "bold #00FF41",     # Green — open ports
    "scan.port_closed": "dim #666666",    # Gray — closed
    "scan.vuln_critical": "bold #FF0033", # Red — critical
    "scan.vuln_high": "#FF6600",          # Orange — high
    "scan.vuln_medium": "#FFB300",        # Amber — medium
    "scan.vuln_low": "#00D4FF",           # Cyan — low
    "scan.vuln_info": "dim #888888",      # Gray — info

    # UI elements
    "header": "bold #FF0033",             # Section headers
    "subheader": "bold #00D4FF",          # Sub-sections
    "border": "#333333",                  # Borders
    "dim": "dim #666666",                 # Dim text
    "highlight": "bold #FFFFFF",          # White highlight
    "prompt": "#00FF41",                  # Green prompt
    "input": "#FFFFFF",                   # White input
})

# Global themed console
console = Console(theme=PREDATOR_THEME, stderr=False)
err_console = Console(theme=PREDATOR_THEME, stderr=True)


# ──────────────────────────────────────────────────────────
# ASCII ART — Black Shark with Red Eyes
# ──────────────────────────────────────────────────────────

SHARK_LOGO = (
    "[bold #FF0033]"
    "                        ,-.\n"
    "                       / /  \\\n"
    "                      / /    \\\n"
    "                     / /      \\__\n"
    "                    / /  /  \\    \\\n"
    "                   | |  [#CC0000]o[/bold #FF0033]    \\   \\          ___\n"
    "                   | |        \\   \\    ___/   \\\n"
    "                   | |    \\____\\   \\--'       /\n"
    "                    \\ \\                      /\n"
    "                     \\ \\___          ___    /\n"
    "                      \\    \\________/   \\__/\n"
    "                       `---'  \\/  \\/"
    "[/bold #FF0033]"
)

BANNER = (
    "[bold #FF0033]"
    "    ######  ######  ####### ######   #####  ######## ####### ######\n"
    "    ##   ## ##   ## ##      ##   ## ##   ##    ##    ##   ## ##   ##\n"
    "    ######  ######  #####   ##   ## #######    ##    ##   ## ######\n"
    "    ##      ##  ##  ##      ##   ## ##   ##    ##    ##   ## ##  ##\n"
    "    ##      ##   ## ####### ######  ##   ##    ##    ####### ##   ##"
    "[/]\n"
    "[dim #666666]    ---------------------------------------------------------[/]\n"
    "[dim #CC0029]    Autonomous AI Agent for Ethical Hackers & Cybersecurity[/]"
)

BANNER_COMPACT = "[bold #FF0033]PREDATOR[/] [dim #CC0029]// Autonomous Cybersecurity Agent[/]"

SHARK_SMALL = (
    "[bold #FF0033]"
    "           __\n"
    "          /  \\____/\\\n"
    "         |  [#CC0000]o[/bold #FF0033]       \\\\_____\n"
    "          \\      __/     __/\n"
    "           \\____/  \\____/"
    "[/bold #FF0033]"
)

# ──────────────────────────────────────────────────────────
# Styled output helpers
# ──────────────────────────────────────────────────────────

def print_banner(compact: bool = False) -> None:
    """Print the PREDATOR banner."""
    if compact:
        console.print(BANNER_COMPACT)
    else:
        console.print(SHARK_SMALL)
        console.print(BANNER)


def print_header(text: str) -> None:
    """Print a styled section header."""
    console.print(f"\n[header]>>> {text}[/header]")
    console.print(f"[border]{'-' * (len(text) + 4)}[/border]")


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[success]  [+] {text}[/success]")


def print_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[error]  [x] {text}[/error]")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]  ! {text}[/warning]")


def print_info(text: str) -> None:
    """Print an info message."""
    console.print(f"[info]  -> {text}[/info]")


def print_tool_start(tool_name: str, args_preview: str = "") -> None:
    """Print tool execution start."""
    console.print(f"\n[tool.running]  > {tool_name}[/tool.running]")
    if args_preview:
        console.print(f"[dim]    {args_preview[:120]}[/dim]")


def print_tool_end(tool_name: str, is_error: bool = False, elapsed: float = 0) -> None:
    """Print tool execution result."""
    if is_error:
        console.print(f"[tool.error]  [x] {tool_name}[/tool.error] [dim]({elapsed:.1f}s)[/dim]")
    else:
        console.print(f"[tool.success]  [+] {tool_name}[/tool.success] [dim]({elapsed:.1f}s)[/dim]")


def print_finding(severity: str, text: str) -> None:
    """Print a security finding with severity coloring."""
    severity_styles = {
        "critical": "scan.vuln_critical",
        "high": "scan.vuln_high",
        "medium": "scan.vuln_medium",
        "low": "scan.vuln_low",
        "info": "scan.vuln_info",
    }
    style = severity_styles.get(severity.lower(), "dim")
    label = severity.upper()
    console.print(f"[{style}]  [{label}][/{style}] {text}")


def print_target(target: str) -> None:
    """Print a target identifier."""
    console.print(f"[osint.target]  @ Target: {target}[/osint.target]")


def print_agent_response(text: str) -> None:
    """Print agent response text."""
    console.print(text, highlight=False)


def print_separator() -> None:
    """Print a separator line."""
    console.print("[border]" + "-" * 60 + "[/border]")


def print_stats(turns: int, tokens: int, elapsed: float, reason: str = "") -> None:
    """Print agent run statistics."""
    console.print(
        f"\n[dim]--- {turns} turns | {tokens} tokens | "
        f"{elapsed:.1f}s | {reason} ---[/dim]"
    )

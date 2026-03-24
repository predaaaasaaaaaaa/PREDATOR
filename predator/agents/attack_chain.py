"""Attack Chain Reasoning Engine — multi-step attack path planning.

Real hackers don't just find one vulnerability and stop. They CHAIN findings:
  port scan → service enum → vuln match → exploit → pivot → escalate → own

This engine tracks the attack surface as it's discovered and suggests
the next logical steps in an attack chain based on what's been found.

Attack phases (MITRE ATT&CK inspired):
  1. Reconnaissance — gather intelligence
  2. Resource Development — prepare tools and infrastructure
  3. Initial Access — get a foothold
  4. Execution — run attacker code
  5. Persistence — maintain access
  6. Privilege Escalation — get higher privileges
  7. Defense Evasion — avoid detection
  8. Credential Access — steal credentials
  9. Discovery — learn the environment
  10. Lateral Movement — spread to other systems
  11. Collection — gather target data
  12. Exfiltration — extract data
  13. Impact — achieve objectives
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("agents.attack_chain")


class AttackPhase(str, Enum):
    """Attack phases based on MITRE ATT&CK framework."""

    RECON = "reconnaissance"
    RESOURCE_DEV = "resource_development"
    INITIAL_ACCESS = "initial_access"
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    PRIV_ESC = "privilege_escalation"
    DEF_EVASION = "defense_evasion"
    CRED_ACCESS = "credential_access"
    DISCOVERY = "discovery"
    LATERAL_MOVEMENT = "lateral_movement"
    COLLECTION = "collection"
    EXFILTRATION = "exfiltration"
    IMPACT = "impact"


@dataclass
class AttackNode:
    """A single node in an attack chain."""

    phase: AttackPhase
    technique: str
    description: str
    tool: str = ""
    target: str = ""
    result: str = ""
    success: bool = False
    children: list[AttackNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttackSurface:
    """Discovered attack surface — tracks what we know about the target."""

    # Network
    open_ports: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    os_info: str = ""
    hostnames: list[str] = field(default_factory=list)
    subdomains: list[str] = field(default_factory=list)

    # Web
    web_technologies: list[str] = field(default_factory=list)
    web_endpoints: list[str] = field(default_factory=list)
    web_parameters: list[str] = field(default_factory=list)
    waf_detected: str = ""

    # Credentials
    usernames: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    password_hashes: list[str] = field(default_factory=list)
    cracked_passwords: list[str] = field(default_factory=list)

    # Vulnerabilities
    vulns: list[dict[str, Any]] = field(default_factory=list)
    cves: list[str] = field(default_factory=list)

    # Access
    shells: list[dict[str, Any]] = field(default_factory=list)
    current_user: str = ""
    is_root: bool = False

    # Internal network (post-exploitation)
    internal_hosts: list[str] = field(default_factory=list)
    internal_services: list[dict[str, Any]] = field(default_factory=list)
    pivot_points: list[str] = field(default_factory=list)


# ─── Attack Chain Templates ────────────────────────────────────────
# Common attack chains that PREDATOR can suggest based on findings.

CHAIN_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "web_app_rce": [
        {"phase": "recon", "action": "Enumerate web technologies", "tools": ["whatweb", "httpx", "wappalyzer"]},
        {"phase": "recon", "action": "Directory brute-force", "tools": ["gobuster", "ffuf", "dirb"]},
        {"phase": "recon", "action": "Parameter discovery", "tools": ["arjun", "paramspider"]},
        {"phase": "initial_access", "action": "Test for SQL injection", "tools": ["sqlmap"]},
        {"phase": "initial_access", "action": "Test for command injection", "tools": ["commix"]},
        {"phase": "initial_access", "action": "Test for file inclusion", "tools": ["ffuf", "curl"]},
        {"phase": "initial_access", "action": "Test for SSRF", "tools": ["curl", "ffuf"]},
        {"phase": "execution", "action": "Achieve code execution", "tools": ["reverse_shell", "webshell"]},
        {"phase": "priv_esc", "action": "Escalate privileges", "tools": ["linpeas", "sudo -l"]},
        {"phase": "persistence", "action": "Establish persistence", "tools": ["cron", "ssh_key", "backdoor"]},
    ],

    "network_pentest": [
        {"phase": "recon", "action": "Host discovery", "tools": ["nmap -sn", "arp-scan", "fping"]},
        {"phase": "recon", "action": "Port scanning", "tools": ["nmap", "masscan", "naabu"]},
        {"phase": "recon", "action": "Service enumeration", "tools": ["nmap -sV", "banner grab"]},
        {"phase": "recon", "action": "OS fingerprinting", "tools": ["nmap -O", "p0f"]},
        {"phase": "initial_access", "action": "Exploit vulnerable service", "tools": ["metasploit", "searchsploit"]},
        {"phase": "initial_access", "action": "Brute-force credentials", "tools": ["hydra", "medusa", "ncrack"]},
        {"phase": "cred_access", "action": "Dump credentials", "tools": ["mimikatz", "hashdump", "secretsdump"]},
        {"phase": "lateral_movement", "action": "Pivot to internal hosts", "tools": ["chisel", "socat", "ssh"]},
        {"phase": "priv_esc", "action": "Escalate to domain admin", "tools": ["bloodhound", "rubeus"]},
    ],

    "ad_compromise": [
        {"phase": "recon", "action": "Enumerate AD structure", "tools": ["bloodhound", "ldapsearch", "enum4linux"]},
        {"phase": "recon", "action": "Find SPNs (kerberoasting targets)", "tools": ["GetUserSPNs.py"]},
        {"phase": "cred_access", "action": "Kerberoast", "tools": ["GetUserSPNs.py", "hashcat"]},
        {"phase": "cred_access", "action": "AS-REP roast", "tools": ["GetNPUsers.py", "hashcat"]},
        {"phase": "cred_access", "action": "NTLM relay", "tools": ["responder", "ntlmrelayx"]},
        {"phase": "lateral_movement", "action": "Pass-the-hash", "tools": ["crackmapexec", "impacket"]},
        {"phase": "lateral_movement", "action": "PSExec", "tools": ["psexec.py", "wmiexec.py"]},
        {"phase": "priv_esc", "action": "DCSync", "tools": ["secretsdump.py", "mimikatz"]},
        {"phase": "impact", "action": "Golden ticket", "tools": ["ticketer.py", "mimikatz"]},
    ],

    "wifi_attack": [
        {"phase": "recon", "action": "Scan for wireless networks", "tools": ["airodump-ng", "kismet"]},
        {"phase": "recon", "action": "Identify target network", "tools": ["airodump-ng -c"]},
        {"phase": "initial_access", "action": "Capture WPA handshake", "tools": ["aireplay-ng", "airodump-ng"]},
        {"phase": "cred_access", "action": "Crack WPA password", "tools": ["aircrack-ng", "hashcat"]},
        {"phase": "initial_access", "action": "WPS attack", "tools": ["reaver", "bully"]},
        {"phase": "initial_access", "action": "Evil twin attack", "tools": ["hostapd-wpe", "fluxion"]},
        {"phase": "lateral_movement", "action": "Pivot into network", "tools": ["nmap", "arp-scan"]},
    ],

    "osint_deep": [
        {"phase": "recon", "action": "Domain WHOIS & DNS", "tools": ["whois", "dig", "dnsrecon"]},
        {"phase": "recon", "action": "Subdomain enumeration", "tools": ["subfinder", "amass", "assetfinder"]},
        {"phase": "recon", "action": "Email harvesting", "tools": ["theharvester", "hunter.io"]},
        {"phase": "recon", "action": "Username hunting", "tools": ["sherlock", "social-analyzer"]},
        {"phase": "recon", "action": "Breach data check", "tools": ["h8mail", "dehashed"]},
        {"phase": "recon", "action": "Technology profiling", "tools": ["whatweb", "builtwith", "wappalyzer"]},
        {"phase": "recon", "action": "Social media analysis", "tools": ["sherlock", "social-analyzer"]},
        {"phase": "recon", "action": "Document metadata", "tools": ["exiftool", "metagoofil"]},
        {"phase": "recon", "action": "Certificate transparency", "tools": ["crt.sh", "certspotter"]},
        {"phase": "recon", "action": "Wayback Machine analysis", "tools": ["waybackurls", "gau"]},
    ],

    "cloud_attack": [
        {"phase": "recon", "action": "Enumerate cloud services", "tools": ["cloud_enum", "ScoutSuite"]},
        {"phase": "recon", "action": "S3 bucket enumeration", "tools": ["s3scanner", "aws s3 ls"]},
        {"phase": "initial_access", "action": "Test for misconfigurations", "tools": ["prowler", "ScoutSuite"]},
        {"phase": "cred_access", "action": "Check for exposed credentials", "tools": ["trufflehog", "gitleaks"]},
        {"phase": "priv_esc", "action": "IAM privilege escalation", "tools": ["pacu", "aws-escalate"]},
        {"phase": "lateral_movement", "action": "Cross-account access", "tools": ["aws sts assume-role"]},
        {"phase": "collection", "action": "Exfiltrate data", "tools": ["aws s3 cp", "rclone"]},
    ],
}


class AttackChainEngine:
    """Tracks the attack surface and suggests next steps in the attack chain.

    This engine:
    1. Maintains the discovered attack surface
    2. Determines current attack phase
    3. Suggests next logical steps
    4. Recommends tool chains
    5. Generates attack path visualization
    """

    def __init__(self) -> None:
        self._surface = AttackSurface()
        self._chain: list[AttackNode] = []
        self._current_phase = AttackPhase.RECON

    def update_surface(self, finding_type: str, data: dict[str, Any]) -> None:
        """Update the attack surface with new findings."""
        if finding_type == "open_port":
            self._surface.open_ports.append(data)
        elif finding_type == "service":
            self._surface.services.append(data)
        elif finding_type == "subdomain":
            self._surface.subdomains.append(data.get("subdomain", ""))
        elif finding_type == "email":
            self._surface.emails.append(data.get("email", ""))
        elif finding_type == "username":
            self._surface.usernames.append(data.get("username", ""))
        elif finding_type == "vulnerability":
            self._surface.vulns.append(data)
            if "cve" in data:
                self._surface.cves.append(data["cve"])
        elif finding_type == "web_tech":
            self._surface.web_technologies.append(data.get("tech", ""))
        elif finding_type == "credential":
            if "hash" in data:
                self._surface.password_hashes.append(data["hash"])
            if "password" in data:
                self._surface.cracked_passwords.append(data["password"])
        elif finding_type == "shell":
            self._surface.shells.append(data)
        elif finding_type == "os":
            self._surface.os_info = data.get("os", "")

    def add_chain_node(
        self,
        phase: AttackPhase,
        technique: str,
        description: str,
        tool: str = "",
        target: str = "",
        result: str = "",
        success: bool = False,
    ) -> AttackNode:
        """Record a step in the attack chain."""
        node = AttackNode(
            phase=phase,
            technique=technique,
            description=description,
            tool=tool,
            target=target,
            result=result[:500],
            success=success,
        )
        self._chain.append(node)

        # Auto-advance phase based on success
        if success:
            phase_order = list(AttackPhase)
            current_idx = phase_order.index(self._current_phase)
            node_idx = phase_order.index(phase)
            if node_idx >= current_idx:
                # Move to next phase if we succeeded at current or later phase
                if node_idx + 1 < len(phase_order):
                    self._current_phase = phase_order[node_idx + 1]

        return node

    def suggest_next_steps(self) -> str:
        """Suggest next steps based on current attack surface and phase.

        This is injected into the system prompt or tool results to guide
        the LLM's attack thinking.
        """
        suggestions = []

        # ── Based on what we have, suggest what to do ──

        # Have open ports but no service versions?
        if self._surface.open_ports and not self._surface.services:
            suggestions.append(
                "NEXT: Run service version detection on discovered ports. "
                "Use: nmap -sV -sC -p{ports} {target}"
            )

        # Have services but no vulns checked?
        if self._surface.services and not self._surface.vulns:
            suggestions.append(
                "NEXT: Check discovered services for known vulnerabilities. "
                "Use: searchsploit {service} {version}, nuclei -u {target}, "
                "nmap --script vuln {target}"
            )

        # Have vulns but no exploitation attempted?
        if self._surface.vulns and not self._surface.shells:
            critical_vulns = [v for v in self._surface.vulns if v.get("severity") == "critical"]
            if critical_vulns:
                suggestions.append(
                    f"NEXT: {len(critical_vulns)} CRITICAL vulnerabilities found! "
                    "Attempt exploitation starting with the highest impact vuln. "
                    "Check Metasploit modules and ExploitDB."
                )

        # Have web technologies but haven't scanned for web vulns?
        if self._surface.web_technologies:
            suggestions.append(
                "NEXT: Web technologies detected. Run: "
                "gobuster/ffuf for directories, sqlmap for SQLi, "
                "nuclei for known CVEs, nikto for misconfigs."
            )

        # Have usernames but haven't tried brute-force?
        if self._surface.usernames and not self._surface.cracked_passwords:
            suggestions.append(
                f"NEXT: {len(self._surface.usernames)} usernames discovered. "
                "Consider password attacks: hydra, medusa, or credential stuffing."
            )

        # Have a shell but haven't escalated?
        if self._surface.shells and not self._surface.is_root:
            suggestions.append(
                "NEXT: Shell obtained! Run privilege escalation checks: "
                "linpeas.sh, sudo -l, find SUID binaries, check cron jobs, "
                "check kernel version for exploits."
            )

        # Have subdomains but haven't scanned them?
        if len(self._surface.subdomains) > 5:
            suggestions.append(
                f"NEXT: {len(self._surface.subdomains)} subdomains found. "
                "Probe them with httpx for live hosts, then scan interesting ones."
            )

        # Suggest chain templates based on context
        template_suggestions = self._suggest_chain_template()
        if template_suggestions:
            suggestions.append(template_suggestions)

        if not suggestions:
            suggestions.append(
                "Current phase: " + self._current_phase.value + ". "
                "Continue gathering intelligence and look for attack vectors."
            )

        return "\n".join([f"[ATTACK CHAIN ENGINE]\n"] + suggestions)

    def _suggest_chain_template(self) -> str:
        """Suggest relevant attack chain templates."""
        # Determine which template fits based on what we've found
        if self._surface.web_technologies:
            return self._format_chain_template("web_app_rce")
        elif any(s.get("service") == "smb" or s.get("service") == "microsoft-ds"
                 for s in self._surface.services):
            return self._format_chain_template("ad_compromise")
        elif self._surface.open_ports:
            return self._format_chain_template("network_pentest")
        elif self._surface.subdomains or self._surface.emails:
            return self._format_chain_template("osint_deep")
        return ""

    def _format_chain_template(self, template_name: str) -> str:
        """Format a chain template for display."""
        template = CHAIN_TEMPLATES.get(template_name)
        if not template:
            return ""

        lines = [f"\nSuggested attack chain ({template_name}):"]
        for i, step in enumerate(template, 1):
            tools = ", ".join(step["tools"][:3])
            lines.append(f"  {i}. [{step['phase']}] {step['action']} → {tools}")
        return "\n".join(lines)

    def get_chain_visualization(self) -> str:
        """Generate a text visualization of the attack chain so far."""
        if not self._chain:
            return "No attack chain steps recorded yet."

        lines = ["ATTACK CHAIN PROGRESS:"]
        for i, node in enumerate(self._chain):
            status = "[+]" if node.success else "[-]"
            lines.append(
                f"  {status} Step {i+1}: [{node.phase.value}] {node.technique} "
                f"({node.tool}) → {node.description[:60]}"
            )

        lines.append(f"\nCurrent phase: {self._current_phase.value}")
        lines.append(f"Attack surface: {len(self._surface.open_ports)} ports, "
                      f"{len(self._surface.services)} services, "
                      f"{len(self._surface.vulns)} vulns, "
                      f"{len(self._surface.shells)} shells")

        return "\n".join(lines)

    def get_surface_summary(self) -> str:
        """Get a summary of the discovered attack surface."""
        s = self._surface
        parts = []
        if s.open_ports:
            ports = [str(p.get("port", "")) for p in s.open_ports[:20]]
            parts.append(f"Open ports: {', '.join(ports)}")
        if s.services:
            svcs = [f"{sv.get('service','')}({sv.get('version','')})" for sv in s.services[:10]]
            parts.append(f"Services: {', '.join(svcs)}")
        if s.subdomains:
            parts.append(f"Subdomains: {len(s.subdomains)}")
        if s.emails:
            parts.append(f"Emails: {len(s.emails)}")
        if s.usernames:
            parts.append(f"Usernames: {len(s.usernames)}")
        if s.vulns:
            parts.append(f"Vulns: {len(s.vulns)}")
        if s.shells:
            parts.append(f"Shells: {len(s.shells)}")
        if s.os_info:
            parts.append(f"OS: {s.os_info}")

        return "\n".join(parts) if parts else "Attack surface: empty (start scanning)"

    @property
    def current_phase(self) -> AttackPhase:
        return self._current_phase

    @property
    def surface(self) -> AttackSurface:
        return self._surface

    def reset(self) -> None:
        self._surface = AttackSurface()
        self._chain.clear()
        self._current_phase = AttackPhase.RECON

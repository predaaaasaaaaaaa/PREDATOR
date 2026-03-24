"""Vulnerability Discovery Engine — CVE correlation, exploit matching, vuln chaining.

This is the PREDATOR brain feature that makes it think like a real vulnerability
researcher. When it discovers a service version, OS, or technology, it:

1. Correlates with known CVEs
2. Matches to available exploits (ExploitDB, Metasploit)
3. Assesses exploitability and impact
4. Suggests attack paths
5. Chains vulnerabilities for maximum impact

This runs as an analysis layer that enriches tool output before sending it
back to the LLM, giving the model structured vulnerability intelligence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("agents.vuln_discovery")


@dataclass
class VulnMatch:
    """A matched vulnerability."""

    service: str
    version: str
    cve_ids: list[str] = field(default_factory=list)
    exploit_refs: list[str] = field(default_factory=list)
    severity: str = ""  # critical, high, medium, low
    description: str = ""
    attack_vector: str = ""  # network, adjacent, local, physical
    exploitability: str = ""  # easy, moderate, hard
    msf_module: str = ""  # Metasploit module path
    searchsploit_id: str = ""


@dataclass
class ServiceFingerprint:
    """A detected service with version info."""

    port: int
    protocol: str  # tcp, udp
    service: str  # http, ssh, ftp, smb, etc.
    product: str  # Apache, OpenSSH, vsftpd, etc.
    version: str
    extra_info: str = ""
    os_guess: str = ""


# ─── Known Vulnerable Service Patterns ──────────────────────────────
# Maps service/version patterns to known vulns. This is a built-in
# knowledge base that supplements online lookups.

KNOWN_VULNS: list[dict[str, Any]] = [
    # ── SSH ──
    {"pattern": r"OpenSSH[_ ]([0-6]\.|7\.[0-3])", "service": "OpenSSH",
     "cves": ["CVE-2016-0777", "CVE-2016-0778"], "severity": "high",
     "desc": "OpenSSH < 7.4 — roaming vulnerability, information leak",
     "exploit": "ssh_roaming", "msf": "auxiliary/scanner/ssh/ssh_enumusers"},
    {"pattern": r"OpenSSH[_ ]7\.[0-7]p1", "service": "OpenSSH",
     "cves": ["CVE-2018-15473"], "severity": "medium",
     "desc": "OpenSSH 2.3-7.7 — username enumeration",
     "exploit": "searchsploit OpenSSH 7.7", "msf": "auxiliary/scanner/ssh/ssh_enumusers"},
    {"pattern": r"OpenSSH[_ ](8\.[0-8]|9\.[0-2])", "service": "OpenSSH",
     "cves": ["CVE-2023-38408"], "severity": "critical",
     "desc": "OpenSSH < 9.3p2 — PKCS#11 remote code execution via ssh-agent forwarding",
     "exploit": "CVE-2023-38408", "msf": ""},
    {"pattern": r"OpenSSH[_ ](8\.[5-9]|9\.[0-7])", "service": "OpenSSH",
     "cves": ["CVE-2024-6387"], "severity": "critical",
     "desc": "regreSSHion — OpenSSH signal handler race condition RCE (glibc-based Linux)",
     "exploit": "CVE-2024-6387", "msf": ""},

    # ── Apache ──
    {"pattern": r"Apache[/ ](2\.4\.(0|[1-4][0-9](?!\d))|2\.4\.49|2\.4\.50)", "service": "Apache",
     "cves": ["CVE-2021-41773", "CVE-2021-42013"], "severity": "critical",
     "desc": "Apache 2.4.49/50 — Path traversal + RCE",
     "exploit": "searchsploit Apache 2.4.49", "msf": "exploit/multi/http/apache_normalize_path_rce"},
    {"pattern": r"Apache[/ ]2\.4\.(1[0-9]|2[0-9]|3[0-9]|4[0-8])", "service": "Apache",
     "cves": ["CVE-2019-0211"], "severity": "high",
     "desc": "Apache 2.4.10-48 — privilege escalation via scoreboard manipulation",
     "exploit": "CVE-2019-0211", "msf": ""},
    {"pattern": r"Apache[/ ]2\.2\.", "service": "Apache",
     "cves": ["CVE-2017-7679", "CVE-2017-3167"], "severity": "high",
     "desc": "Apache 2.2.x — multiple vulnerabilities (EOL)",
     "exploit": "searchsploit Apache 2.2", "msf": ""},

    # ── Nginx ──
    {"pattern": r"nginx[/ ](1\.([0-9]|1[0-7])\.|0\.)", "service": "nginx",
     "cves": ["CVE-2019-20372"], "severity": "medium",
     "desc": "nginx < 1.17.7 — HTTP request smuggling",
     "exploit": "CVE-2019-20372", "msf": ""},

    # ── FTP ──
    {"pattern": r"vsftpd 2\.3\.4", "service": "vsftpd",
     "cves": ["CVE-2011-2523"], "severity": "critical",
     "desc": "vsftpd 2.3.4 — backdoor command execution (smiley face trigger)",
     "exploit": "searchsploit vsftpd 2.3.4", "msf": "exploit/unix/ftp/vsftpd_234_backdoor"},
    {"pattern": r"ProFTPD[/ ]1\.[23]\.", "service": "ProFTPD",
     "cves": ["CVE-2015-3306"], "severity": "critical",
     "desc": "ProFTPD 1.3.5 — mod_copy arbitrary file copy",
     "exploit": "searchsploit ProFTPD 1.3.5", "msf": "exploit/unix/ftp/proftpd_modcopy_exec"},

    # ── SMB ──
    {"pattern": r"Samba (3\.[0-5]|2\.)", "service": "Samba",
     "cves": ["CVE-2017-7494"], "severity": "critical",
     "desc": "Samba 3.5.0-4.6.4 — SambaCry RCE",
     "exploit": "searchsploit Samba", "msf": "exploit/linux/samba/is_known_pipename"},
    {"pattern": r"Windows .* (5\.1|6\.0|6\.1)", "service": "Windows SMB",
     "cves": ["CVE-2017-0144"], "severity": "critical",
     "desc": "EternalBlue — Windows SMB RCE (MS17-010)",
     "exploit": "EternalBlue", "msf": "exploit/windows/smb/ms17_010_eternalblue"},
    {"pattern": r"Windows .* 10\.0", "service": "Windows SMB",
     "cves": ["CVE-2020-0796"], "severity": "critical",
     "desc": "SMBGhost — Windows 10 SMBv3 RCE",
     "exploit": "CVE-2020-0796", "msf": "exploit/windows/smb/cve_2020_0796_smbghost"},

    # ── MySQL ──
    {"pattern": r"MySQL[/ ](5\.[0-5]\.)", "service": "MySQL",
     "cves": ["CVE-2012-2122"], "severity": "critical",
     "desc": "MySQL 5.1/5.5 — authentication bypass (memcmp timing)",
     "exploit": "searchsploit MySQL 5.5", "msf": "auxiliary/scanner/mysql/mysql_authbypass_hashdump"},

    # ── PostgreSQL ──
    {"pattern": r"PostgreSQL.*(9\.[0-3]|8\.)", "service": "PostgreSQL",
     "cves": ["CVE-2019-9193"], "severity": "high",
     "desc": "PostgreSQL 9.3+ — authenticated RCE via COPY FROM PROGRAM",
     "exploit": "CVE-2019-9193", "msf": "exploit/multi/postgres/postgres_copy_from_program_cmd_exec"},

    # ── Redis ──
    {"pattern": r"Redis.*(3\.|4\.|5\.[0-2])", "service": "Redis",
     "cves": ["CVE-2022-0543"], "severity": "critical",
     "desc": "Redis < 5.0.3 — unauthenticated RCE (Lua sandbox escape + SLAVEOF)",
     "exploit": "redis-rce", "msf": ""},

    # ── Tomcat ──
    {"pattern": r"Apache Tomcat[/ ](7\.|8\.[05]\.|9\.0\.[0-2][0-9](?!\d))", "service": "Tomcat",
     "cves": ["CVE-2017-12617", "CVE-2020-1938"], "severity": "critical",
     "desc": "Tomcat — JSP upload via PUT + Ghostcat AJP",
     "exploit": "searchsploit Tomcat", "msf": "exploit/multi/http/tomcat_jsp_upload_bypass"},

    # ── WordPress ──
    {"pattern": r"WordPress[/ ](4\.[0-9]\.|5\.[0-4]\.)", "service": "WordPress",
     "cves": ["CVE-2022-21661"], "severity": "high",
     "desc": "WordPress < 5.8.3 — SQL injection via WP_Query",
     "exploit": "wpscan", "msf": ""},

    # ── Jenkins ──
    {"pattern": r"Jenkins[/ ](2\.[0-9]{1,2}(?!\d)|1\.)", "service": "Jenkins",
     "cves": ["CVE-2019-1003000", "CVE-2024-23897"], "severity": "critical",
     "desc": "Jenkins — Script Console RCE / Arbitrary file read",
     "exploit": "searchsploit Jenkins", "msf": "exploit/multi/http/jenkins_script_console"},

    # ── Elasticsearch ──
    {"pattern": r"Elasticsearch[/ ](1\.|6\.[0-7]\.|7\.[0-9]\.)", "service": "Elasticsearch",
     "cves": ["CVE-2015-1427", "CVE-2014-3120"], "severity": "critical",
     "desc": "Elasticsearch — Groovy/MVEL script engine RCE",
     "exploit": "searchsploit Elasticsearch", "msf": "exploit/multi/elasticsearch/script_mvel_rce"},

    # ── PHP ──
    {"pattern": r"PHP[/ ](5\.[0-4]|7\.[0-3]\.|8\.0\.[0-9](?!\d))", "service": "PHP",
     "cves": ["CVE-2024-4577"], "severity": "critical",
     "desc": "PHP-CGI argument injection RCE",
     "exploit": "CVE-2024-4577", "msf": "exploit/multi/http/php_cgi_arg_injection"},

    # ── Log4j ──
    {"pattern": r"(log4j|Log4j)[/ ](2\.(0|1[0-6])\.)", "service": "Log4j",
     "cves": ["CVE-2021-44228"], "severity": "critical",
     "desc": "Log4Shell — JNDI injection RCE",
     "exploit": "log4shell", "msf": "exploit/multi/http/log4shell_header_injection"},

    # ── Spring ──
    {"pattern": r"Spring[/ ].*(4\.3|5\.[0-2])", "service": "Spring Framework",
     "cves": ["CVE-2022-22965"], "severity": "critical",
     "desc": "Spring4Shell — ClassLoader manipulation RCE",
     "exploit": "CVE-2022-22965", "msf": "exploit/multi/http/spring_framework_rce_spring4shell"},

    # ── Exim ──
    {"pattern": r"Exim[/ ](4\.(8[0-9]|9[0-6]))", "service": "Exim",
     "cves": ["CVE-2019-10149"], "severity": "critical",
     "desc": "Exim 4.87-4.91 — The Return of the WIZard RCE",
     "exploit": "searchsploit Exim 4.87", "msf": "exploit/unix/smtp/exim4_string_format"},

    # ── Drupal ──
    {"pattern": r"Drupal[/ ](7\.[0-5][0-9]|8\.[0-5]\.)", "service": "Drupal",
     "cves": ["CVE-2018-7600", "CVE-2019-6340"], "severity": "critical",
     "desc": "Drupalgeddon 2/3 — RCE via AJAX API",
     "exploit": "searchsploit Drupalgeddon", "msf": "exploit/unix/webapp/drupal_drupalgeddon2"},

    # ── Webmin ──
    {"pattern": r"Webmin[/ ](1\.[0-8][0-9][0-9]|1\.9[0-2])", "service": "Webmin",
     "cves": ["CVE-2019-15107"], "severity": "critical",
     "desc": "Webmin 1.890-1.920 — unauthenticated RCE via password_change.cgi",
     "exploit": "searchsploit Webmin", "msf": "exploit/linux/http/webmin_backdoor"},

    # ── IIS ──
    {"pattern": r"IIS[/ ](6\.0|7\.0|7\.5|8\.0)", "service": "IIS",
     "cves": ["CVE-2017-7269"], "severity": "critical",
     "desc": "IIS 6.0 — WebDAV buffer overflow RCE",
     "exploit": "searchsploit IIS 6.0", "msf": "exploit/windows/iis/iis_webdav_scstoragepathfromurl"},

    # ── Confluence ──
    {"pattern": r"Confluence[/ ](7\.[0-9]\.|7\.1[0-8]\.)", "service": "Confluence",
     "cves": ["CVE-2022-26134", "CVE-2023-22515"], "severity": "critical",
     "desc": "Confluence — OGNL injection RCE / Broken access control",
     "exploit": "CVE-2022-26134", "msf": "exploit/multi/http/confluence_ognl_injection"},
]


# ─── Service Version Extraction Patterns ─────────────────────────────
# Regex patterns to extract service/version from tool output (nmap, etc.)

VERSION_PATTERNS: list[tuple[str, str, str]] = [
    # Nmap output format: PORT STATE SERVICE VERSION
    (r"(\d+)/tcp\s+open\s+(\S+)\s+(.*)", "nmap_tcp", "port/tcp service version_info"),
    (r"(\d+)/udp\s+open\s+(\S+)\s+(.*)", "nmap_udp", "port/udp service version_info"),

    # Version strings
    (r"(OpenSSH[_ ]\S+)", "ssh", "OpenSSH version"),
    (r"(Apache[/ ]\S+)", "http", "Apache version"),
    (r"(nginx[/ ]\S+)", "http", "nginx version"),
    (r"(Microsoft IIS[/ ]\S+)", "http", "IIS version"),
    (r"(vsftpd \S+)", "ftp", "vsftpd version"),
    (r"(ProFTPD[/ ]\S+)", "ftp", "ProFTPD version"),
    (r"(MySQL[/ ]\S+)", "mysql", "MySQL version"),
    (r"(PostgreSQL[/ ]\S+)", "postgresql", "PostgreSQL version"),
    (r"(Redis[/ ]?\S+)", "redis", "Redis version"),
    (r"(Apache Tomcat[/ ]\S+)", "http", "Tomcat version"),
    (r"(Samba \S+)", "smb", "Samba version"),
    (r"(PHP[/ ]\S+)", "http", "PHP version"),
    (r"(WordPress[/ ]\S+)", "http", "WordPress version"),
    (r"(Drupal[/ ]\S+)", "http", "Drupal version"),
    (r"(Jenkins[/ ]\S+)", "http", "Jenkins version"),
    (r"(Elasticsearch[/ ]\S+)", "http", "Elasticsearch version"),
    (r"(Exim[/ ]\S+)", "smtp", "Exim version"),
    (r"(Webmin[/ ]\S+)", "http", "Webmin version"),
    (r"(Confluence[/ ]\S+)", "http", "Confluence version"),
    (r"(Windows .+ Build \d+)", "os", "Windows version"),
    (r"(Ubuntu \S+)", "os", "Ubuntu version"),
    (r"(Debian \S+)", "os", "Debian version"),
    (r"(CentOS \S+)", "os", "CentOS version"),
]


class VulnDiscoveryEngine:
    """Analyzes tool output for known vulnerabilities and enriches it.

    This engine:
    1. Parses service/version fingerprints from tool output
    2. Correlates against known CVE patterns
    3. Suggests exploits and Metasploit modules
    4. Enriches the tool output with vulnerability intelligence

    The enriched output goes back to the LLM so it can make informed
    decisions about exploitation paths.
    """

    def __init__(self) -> None:
        self._findings: list[VulnMatch] = []
        self._fingerprints: list[ServiceFingerprint] = []

    def analyze_output(self, tool_name: str, output: str) -> Optional[str]:
        """Analyze tool output for vulnerabilities and return enrichment text.

        Returns None if no vulns found, or enrichment text to append.
        """
        if not output or len(output) < 10:
            return None

        # Extract service fingerprints
        fingerprints = self._extract_fingerprints(output)
        if not fingerprints:
            # Try to match version strings directly
            matches = self._match_known_vulns(output)
            if not matches:
                return None
        else:
            self._fingerprints.extend(fingerprints)
            matches = []
            for fp in fingerprints:
                fp_matches = self._match_known_vulns(f"{fp.product} {fp.version}")
                matches.extend(fp_matches)

        if not matches:
            return None

        self._findings.extend(matches)

        # Build enrichment text
        lines = [
            f"\n{'='*60}",
            "[PREDATOR VULNERABILITY DISCOVERY ENGINE]",
            f"Found {len(matches)} potential vulnerabilities:",
            "",
        ]

        for i, m in enumerate(matches, 1):
            severity_icon = {
                "critical": "!!!",
                "high": "!! ",
                "medium": "!  ",
                "low": ".  ",
            }.get(m.severity, "?  ")

            lines.append(f"  [{severity_icon}] #{i}: {m.description}")
            lines.append(f"      Service: {m.service} {m.version}")
            if m.cve_ids:
                lines.append(f"      CVEs: {', '.join(m.cve_ids)}")
            if m.msf_module:
                lines.append(f"      Metasploit: {m.msf_module}")
            if m.exploit_refs:
                lines.append(f"      Exploits: {', '.join(m.exploit_refs)}")
            lines.append(f"      Severity: {m.severity.upper()}")
            lines.append("")

        lines.extend([
            "RECOMMENDED ACTIONS:",
            "  1. Verify each vulnerability with targeted probes",
            "  2. Check exploit availability: searchsploit <service> <version>",
            "  3. For Metasploit modules: use the module path shown above",
            "  4. Cross-reference CVEs for patch status",
            "  5. Consider attack chains — can you chain these for greater impact?",
            f"{'='*60}\n",
        ])

        return "\n".join(lines)

    def _extract_fingerprints(self, output: str) -> list[ServiceFingerprint]:
        """Extract service fingerprints from nmap-style output."""
        fingerprints = []

        # Parse nmap output lines
        for line in output.split("\n"):
            # Match: PORT/PROTO STATE SERVICE VERSION
            m = re.match(r"(\d+)/(tcp|udp)\s+open\s+(\S+)\s*(.*)", line.strip())
            if m:
                port = int(m.group(1))
                proto = m.group(2)
                service = m.group(3)
                version_info = m.group(4).strip()

                # Extract product and version from version_info
                product = ""
                version = ""
                for vp, _, _ in VERSION_PATTERNS:
                    vm = re.search(vp, version_info)
                    if vm:
                        product = vm.group(1)
                        # Try to extract just the version number
                        v_match = re.search(r"[\d.]+", product)
                        if v_match:
                            version = v_match.group(0)
                        break

                if not product:
                    product = version_info.split()[0] if version_info else service

                fingerprints.append(ServiceFingerprint(
                    port=port,
                    protocol=proto,
                    service=service,
                    product=product,
                    version=version,
                    extra_info=version_info,
                ))

        return fingerprints

    def _match_known_vulns(self, text: str) -> list[VulnMatch]:
        """Match text against known vulnerability patterns."""
        matches = []

        for vuln in KNOWN_VULNS:
            if re.search(vuln["pattern"], text, re.IGNORECASE):
                match = VulnMatch(
                    service=vuln["service"],
                    version=re.search(vuln["pattern"], text, re.IGNORECASE).group(0),
                    cve_ids=vuln.get("cves", []),
                    exploit_refs=[vuln["exploit"]] if vuln.get("exploit") else [],
                    severity=vuln.get("severity", "medium"),
                    description=vuln.get("desc", ""),
                    msf_module=vuln.get("msf", ""),
                )
                matches.append(match)

        return matches

    def get_findings_summary(self) -> str:
        """Get a summary of all findings across the session."""
        if not self._findings:
            return "No vulnerabilities discovered yet."

        by_severity: dict[str, list[VulnMatch]] = {}
        for f in self._findings:
            by_severity.setdefault(f.severity, []).append(f)

        lines = ["VULNERABILITY SUMMARY:"]
        for sev in ["critical", "high", "medium", "low"]:
            vulns = by_severity.get(sev, [])
            if vulns:
                lines.append(f"  {sev.upper()}: {len(vulns)}")
                for v in vulns:
                    lines.append(f"    - {v.service} {v.version}: {v.description}")
        lines.append(f"Total: {len(self._findings)} vulnerabilities")
        return "\n".join(lines)

    @property
    def findings(self) -> list[VulnMatch]:
        return self._findings

    @property
    def fingerprints(self) -> list[ServiceFingerprint]:
        return self._fingerprints

    def reset(self) -> None:
        self._findings.clear()
        self._fingerprints.clear()

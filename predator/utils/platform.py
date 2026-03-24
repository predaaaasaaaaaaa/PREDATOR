"""Platform detection and Kali Linux identification — PREDATOR runs on Linux only.

Detects:
- Linux distribution (Kali, Ubuntu, Debian, Arch, etc.)
- Available security tools
- System capabilities (root, network interfaces, etc.)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class PlatformInfo:
    """System platform information."""

    distro: str = "unknown"
    distro_version: str = ""
    is_kali: bool = False
    is_root: bool = False
    hostname: str = ""
    kernel: str = ""
    arch: str = ""
    available_tools: dict[str, str] = field(default_factory=dict)


# Core tools PREDATOR knows about — maps tool name to binary name
KNOWN_TOOLS: dict[str, str] = {
    # Recon / Scanning
    "nmap": "nmap",
    "masscan": "masscan",
    "zmap": "zmap",
    # Domain / Web OSINT
    "theharvester": "theHarvester",
    "amass": "amass",
    "sublist3r": "sublist3r",
    "dnsrecon": "dnsrecon",
    "dnsenum": "dnsenum",
    "whois": "whois",
    "dig": "dig",
    "fierce": "fierce",
    "whatweb": "whatweb",
    "wafw00f": "wafw00f",
    # Social OSINT
    "sherlock": "sherlock",
    "social-analyzer": "social-analyzer",
    # Email OSINT
    "h8mail": "h8mail",
    "holehe": "holehe",
    # Phone OSINT
    "phoneinfoga": "phoneinfoga",
    # Metadata
    "exiftool": "exiftool",
    # OSINT Frameworks
    "recon-ng": "recon-ng",
    "spiderfoot": "spiderfoot",
    "maltego": "maltego",
    "sn0int": "sn0int",
    # Vuln Scanning
    "nikto": "nikto",
    "wpscan": "wpscan",
    "sqlmap": "sqlmap",
    "nuclei": "nuclei",
    # Exploitation
    "msfconsole": "msfconsole",
    "searchsploit": "searchsploit",
    "hydra": "hydra",
    "john": "john",
    "hashcat": "hashcat",
    # Wireless
    "aircrack-ng": "aircrack-ng",
    "wifite": "wifite",
    "bettercap": "bettercap",
    # Network
    "wireshark": "wireshark",
    "tcpdump": "tcpdump",
    "netcat": "nc",
    "ncat": "ncat",
    "socat": "socat",
    "ettercap": "ettercap",
    # Web
    "burpsuite": "burpsuite",
    "gobuster": "gobuster",
    "dirb": "dirb",
    "ffuf": "ffuf",
    "feroxbuster": "feroxbuster",
    # Post-exploitation
    "linpeas": "linpeas.sh",
    "enum4linux": "enum4linux",
    "bloodhound": "bloodhound",
    # Forensics
    "volatility": "vol.py",
    "binwalk": "binwalk",
    "foremost": "foremost",
    "autopsy": "autopsy",
    # Reverse Engineering
    "ghidra": "ghidra",
    "radare2": "r2",
    # Misc
    "curl": "curl",
    "wget": "wget",
    "git": "git",
    "python3": "python3",
    "pip": "pip3",
    "tor": "tor",
    "proxychains": "proxychains4",
    "sshuttle": "sshuttle",
    "responder": "responder",
    "impacket": "impacket-smbserver",
}


def _read_os_release() -> dict[str, str]:
    """Parse /etc/os-release."""
    result: dict[str, str] = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    result[key] = val.strip('"')
    except FileNotFoundError:
        pass
    return result


def _detect_tools() -> dict[str, str]:
    """Detect which known tools are available on the system."""
    found: dict[str, str] = {}
    for name, binary in KNOWN_TOOLS.items():
        path = shutil.which(binary)
        if path:
            found[name] = path
    return found


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """Detect the current platform. Results are cached."""
    os_release = _read_os_release()
    distro_id = os_release.get("ID", "unknown")
    distro_version = os_release.get("VERSION_ID", "")

    info = PlatformInfo(
        distro=distro_id,
        distro_version=distro_version,
        is_kali=distro_id.lower() == "kali",
        is_root=os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        hostname=os.uname().nodename if hasattr(os, "uname") else "",
        kernel=os.uname().release if hasattr(os, "uname") else "",
        arch=os.uname().machine if hasattr(os, "uname") else "",
        available_tools=_detect_tools(),
    )
    return info


def check_tool_available(tool_name: str) -> Optional[str]:
    """Check if a specific tool is available. Returns path or None."""
    info = detect_platform()
    return info.available_tools.get(tool_name)


def require_tool(tool_name: str) -> str:
    """Require a tool to be available, raise if not found."""
    path = check_tool_available(tool_name)
    if path is None:
        binary = KNOWN_TOOLS.get(tool_name, tool_name)
        raise FileNotFoundError(
            f"Tool '{tool_name}' (binary: {binary}) is not installed. "
            f"Install it with: sudo apt install {tool_name}"
        )
    return path

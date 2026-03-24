"""Auto-installer — autonomously installs missing tools when PREDATOR needs them.

CRITICAL FEATURE: When the agent tries to use a tool (nmap, sqlmap, etc.) and it's
not installed on the system, PREDATOR detects this and installs it automatically
WITHOUT asking the user. After install, it informs the user what was installed.

Mirrors real hacker workflow: you need a tool, you install it, you use it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional

from predator.utils.logger import get_logger

log = get_logger("tools.auto_installer")


@dataclass
class InstallResult:
    """Result of an auto-install attempt."""

    tool_name: str
    package_name: str
    success: bool
    method: str  # apt, pip, go, snap, git, gem, npm, cargo, manual
    output: str = ""
    error: str = ""
    already_installed: bool = False


# ─── Tool → Package mapping ───────────────────────────────────────────
# Maps binary names to their install commands across package managers.
# This is what makes PREDATOR truly autonomous on Linux/Kali.

TOOL_PACKAGES: dict[str, dict] = {
    # ── Network Reconnaissance ──
    "nmap": {"apt": "nmap", "desc": "Network scanner"},
    "masscan": {"apt": "masscan", "desc": "Fast port scanner"},
    "zmap": {"apt": "zmap", "desc": "Internet-wide scanner"},
    "hping3": {"apt": "hping3", "desc": "Packet crafting tool"},
    "netcat": {"apt": "ncat", "alt_bins": ["nc", "ncat"], "desc": "Network utility"},
    "nc": {"apt": "ncat", "desc": "Netcat"},
    "ncat": {"apt": "ncat", "desc": "Nmap netcat"},
    "traceroute": {"apt": "traceroute", "desc": "Route tracer"},
    "tcpdump": {"apt": "tcpdump", "desc": "Packet analyzer"},
    "tshark": {"apt": "tshark", "desc": "Terminal Wireshark"},
    "wireshark": {"apt": "wireshark", "desc": "Network protocol analyzer"},
    "arp-scan": {"apt": "arp-scan", "desc": "ARP scanner"},
    "arping": {"apt": "arping", "desc": "ARP ping"},
    "fping": {"apt": "fping", "desc": "Fast ping sweep"},
    "nbtscan": {"apt": "nbtscan", "desc": "NetBIOS scanner"},
    "onesixtyone": {"apt": "onesixtyone", "desc": "SNMP scanner"},
    "snmpwalk": {"apt": "snmp", "desc": "SNMP walker"},

    # ── Web Application Testing ──
    "nikto": {"apt": "nikto", "desc": "Web server scanner"},
    "sqlmap": {"apt": "sqlmap", "pip": "sqlmap", "desc": "SQL injection tool"},
    "gobuster": {"apt": "gobuster", "go": "github.com/OJ/gobuster/v3@latest", "desc": "Directory/DNS brute-forcer"},
    "ffuf": {"apt": "ffuf", "go": "github.com/ffuf/ffuf/v2@latest", "desc": "Fast web fuzzer"},
    "dirb": {"apt": "dirb", "desc": "Web content scanner"},
    "dirsearch": {"pip": "dirsearch", "desc": "Web path scanner"},
    "wfuzz": {"pip": "wfuzz", "desc": "Web fuzzer"},
    "whatweb": {"apt": "whatweb", "desc": "Web technology identifier"},
    "wpscan": {"apt": "wpscan", "gem": "wpscan", "desc": "WordPress scanner"},
    "joomscan": {"apt": "joomscan", "desc": "Joomla scanner"},
    "wafw00f": {"pip": "wafw00f", "desc": "WAF detector"},
    "httpx": {"go": "github.com/projectdiscovery/httpx/cmd/httpx@latest", "desc": "Fast HTTP prober"},
    "httprobe": {"go": "github.com/tomnomnom/httprobe@latest", "desc": "HTTP/S probe"},
    "arjun": {"pip": "arjun", "desc": "HTTP parameter finder"},
    "commix": {"apt": "commix", "desc": "Command injection exploiter"},
    "xsser": {"apt": "xsser", "desc": "XSS scanner"},
    "dalfox": {"go": "github.com/hahwul/dalfox/v2@latest", "desc": "XSS scanner"},

    # ── Vulnerability Scanning ──
    "nuclei": {"go": "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest", "desc": "Template-based vuln scanner"},
    "naabu": {"go": "github.com/projectdiscovery/naabu/v2/cmd/naabu@latest", "desc": "Fast port scanner"},
    "openvas": {"apt": "openvas", "desc": "Vulnerability scanner"},
    "lynis": {"apt": "lynis", "desc": "Security auditing tool"},
    "trivy": {"apt": "trivy", "desc": "Container vulnerability scanner"},
    "grype": {"manual": "curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin", "desc": "Container vuln scanner"},

    # ── OSINT & Reconnaissance ──
    "theHarvester": {"apt": "theharvester", "pip": "theHarvester", "desc": "Email/subdomain harvester"},
    "theharvester": {"apt": "theharvester", "pip": "theHarvester", "desc": "Email/subdomain harvester"},
    "sherlock": {"pip": "sherlock-project", "desc": "Username hunter"},
    "recon-ng": {"apt": "recon-ng", "desc": "Recon framework"},
    "maltego": {"apt": "maltego", "desc": "OSINT visual link analysis"},
    "spiderfoot": {"pip": "spiderfoot", "desc": "OSINT automation"},
    "amass": {"apt": "amass", "go": "github.com/owasp-amass/amass/v4/...@master", "desc": "Subdomain enumeration"},
    "subfinder": {"go": "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest", "desc": "Subdomain finder"},
    "assetfinder": {"go": "github.com/tomnomnom/assetfinder@latest", "desc": "Asset finder"},
    "waybackurls": {"go": "github.com/tomnomnom/waybackurls@latest", "desc": "Wayback Machine URL fetcher"},
    "gau": {"go": "github.com/lc/gau/v2/cmd/gau@latest", "desc": "Get All URLs"},
    "hakrawler": {"go": "github.com/hakluke/hakrawler@latest", "desc": "Web crawler"},
    "katana": {"go": "github.com/projectdiscovery/katana/cmd/katana@latest", "desc": "Next-gen crawler"},
    "photon": {"pip": "photon", "desc": "Fast web crawler"},
    "exiftool": {"apt": "libimage-exiftool-perl", "desc": "Metadata extractor"},
    "metagoofil": {"apt": "metagoofil", "desc": "Metadata extractor"},
    "fierce": {"pip": "fierce", "desc": "DNS recon"},
    "dnsrecon": {"apt": "dnsrecon", "pip": "dnsrecon", "desc": "DNS enumeration"},
    "dnsenum": {"apt": "dnsenum", "desc": "DNS enumeration"},
    "dnsmap": {"apt": "dnsmap", "desc": "DNS brute-forcer"},
    "whois": {"apt": "whois", "desc": "WHOIS lookup"},
    "dmitry": {"apt": "dmitry", "desc": "Deepmagic info gathering"},
    "h8mail": {"pip": "h8mail", "desc": "Email breach hunter"},

    # ── Password Attacks ──
    "hydra": {"apt": "hydra", "desc": "Online password cracker"},
    "john": {"apt": "john", "desc": "John the Ripper"},
    "hashcat": {"apt": "hashcat", "desc": "GPU password cracker"},
    "medusa": {"apt": "medusa", "desc": "Parallel brute-forcer"},
    "ncrack": {"apt": "ncrack", "desc": "Network auth cracker"},
    "cewl": {"apt": "cewl", "desc": "Custom wordlist generator"},
    "crunch": {"apt": "crunch", "desc": "Wordlist generator"},
    "hashid": {"pip": "hashid", "desc": "Hash identifier"},
    "hash-identifier": {"apt": "hash-identifier", "desc": "Hash type identifier"},
    "ophcrack": {"apt": "ophcrack", "desc": "Windows password cracker"},
    "patator": {"apt": "patator", "desc": "Multi-protocol brute-forcer"},

    # ── Exploitation ──
    "msfconsole": {"apt": "metasploit-framework", "desc": "Metasploit Framework"},
    "msfvenom": {"apt": "metasploit-framework", "desc": "Metasploit payload generator"},
    "searchsploit": {"apt": "exploitdb", "desc": "Exploit-DB search"},
    "beef-xss": {"apt": "beef-xss", "desc": "Browser exploitation"},
    "responder": {"apt": "responder", "desc": "LLMNR/NBT-NS poisoner"},
    "impacket-smbserver": {"pip": "impacket", "apt": "python3-impacket", "desc": "Impacket SMB"},
    "crackmapexec": {"pip": "crackmapexec", "apt": "crackmapexec", "desc": "Network pentest tool"},
    "evil-winrm": {"gem": "evil-winrm", "desc": "WinRM shell"},
    "smbclient": {"apt": "smbclient", "desc": "SMB client"},
    "rpcclient": {"apt": "samba-common-bin", "desc": "RPC client"},
    "enum4linux": {"apt": "enum4linux", "desc": "SMB/Samba enumerator"},
    "bloodhound": {"apt": "bloodhound", "desc": "AD relationship mapper"},
    "chisel": {"go": "github.com/jpillora/chisel@latest", "desc": "TCP/UDP tunnel"},
    "socat": {"apt": "socat", "desc": "Multipurpose relay"},

    # ── Wireless ──
    "aircrack-ng": {"apt": "aircrack-ng", "desc": "WiFi cracking suite"},
    "airodump-ng": {"apt": "aircrack-ng", "desc": "WiFi packet capture"},
    "aireplay-ng": {"apt": "aircrack-ng", "desc": "WiFi packet injection"},
    "wifite": {"apt": "wifite", "desc": "Automated WiFi auditor"},
    "reaver": {"apt": "reaver", "desc": "WPS attack tool"},
    "bully": {"apt": "bully", "desc": "WPS brute-force"},
    "kismet": {"apt": "kismet", "desc": "Wireless detector"},
    "hostapd-wpe": {"apt": "hostapd-wpe", "desc": "Evil twin AP"},
    "fluxion": {"git": "https://github.com/FluxionNetwork/fluxion.git", "desc": "WiFi social engineering"},

    # ── Post-Exploitation ──
    "linpeas": {"manual": "curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh -o /tmp/linpeas.sh && chmod +x /tmp/linpeas.sh", "desc": "Linux privilege escalation"},
    "pspy": {"manual": "curl -L https://github.com/DominicBreuker/pspy/releases/latest/download/pspy64 -o /tmp/pspy64 && chmod +x /tmp/pspy64", "desc": "Process snooper"},
    "mimikatz": {"apt": "mimikatz", "desc": "Windows credential dumper"},
    "powershell": {"apt": "powershell", "desc": "PowerShell for Linux"},

    # ── Forensics ──
    "volatility": {"pip": "volatility3", "desc": "Memory forensics"},
    "binwalk": {"apt": "binwalk", "desc": "Firmware analysis"},
    "foremost": {"apt": "foremost", "desc": "File carving"},
    "autopsy": {"apt": "autopsy", "desc": "Digital forensics"},
    "steghide": {"apt": "steghide", "desc": "Steganography"},
    "stegseek": {"apt": "stegseek", "desc": "Fast steghide cracker"},
    "strings": {"apt": "binutils", "desc": "String extractor"},
    "file": {"apt": "file", "desc": "File type identifier"},
    "xxd": {"apt": "xxd", "desc": "Hex dump"},

    # ── Reverse Engineering ──
    "ghidra": {"apt": "ghidra", "desc": "RE framework"},
    "radare2": {"apt": "radare2", "desc": "RE framework"},
    "r2": {"apt": "radare2", "desc": "Radare2"},
    "gdb": {"apt": "gdb", "desc": "GNU debugger"},
    "ltrace": {"apt": "ltrace", "desc": "Library call tracer"},
    "strace": {"apt": "strace", "desc": "System call tracer"},
    "objdump": {"apt": "binutils", "desc": "Object file dumper"},
    "upx": {"apt": "upx-ucl", "desc": "Packer/unpacker"},

    # ── Crypto & Tunneling ──
    "openssl": {"apt": "openssl", "desc": "Crypto toolkit"},
    "ssh": {"apt": "openssh-client", "desc": "SSH client"},
    "sshpass": {"apt": "sshpass", "desc": "SSH password tool"},
    "proxychains": {"apt": "proxychains4", "desc": "Proxy chains"},
    "tor": {"apt": "tor", "desc": "Tor anonymity"},
    "openvpn": {"apt": "openvpn", "desc": "VPN client"},
    "wireguard": {"apt": "wireguard-tools", "desc": "WireGuard VPN"},
    "stunnel": {"apt": "stunnel4", "desc": "SSL tunnel"},

    # ── Container & Cloud ──
    "docker": {"apt": "docker.io", "desc": "Container runtime"},
    "kubectl": {"apt": "kubectl", "desc": "Kubernetes CLI"},
    "aws": {"pip": "awscli", "desc": "AWS CLI"},
    "gcloud": {"manual": "curl https://sdk.cloud.google.com | bash", "desc": "Google Cloud CLI"},
    "az": {"pip": "azure-cli", "desc": "Azure CLI"},
    "terraform": {"apt": "terraform", "desc": "Infrastructure as Code"},
    "scout": {"pip": "scoutsuite", "desc": "Cloud security auditor"},

    # ── Utilities ──
    "curl": {"apt": "curl", "desc": "HTTP client"},
    "wget": {"apt": "wget", "desc": "File downloader"},
    "git": {"apt": "git", "desc": "Version control"},
    "jq": {"apt": "jq", "desc": "JSON processor"},
    "yq": {"pip": "yq", "desc": "YAML processor"},
    "tmux": {"apt": "tmux", "desc": "Terminal multiplexer"},
    "screen": {"apt": "screen", "desc": "Terminal multiplexer"},
    "tree": {"apt": "tree", "desc": "Directory tree"},
    "htop": {"apt": "htop", "desc": "Process viewer"},
    "python3": {"apt": "python3", "desc": "Python 3"},
    "pip3": {"apt": "python3-pip", "desc": "Python package manager"},
    "pip": {"apt": "python3-pip", "desc": "Python package manager"},
    "go": {"apt": "golang-go", "desc": "Go language"},
    "ruby": {"apt": "ruby-full", "desc": "Ruby language"},
    "gem": {"apt": "ruby-full", "desc": "Ruby package manager"},
    "node": {"apt": "nodejs", "desc": "Node.js runtime"},
    "npm": {"apt": "npm", "desc": "Node package manager"},
    "cargo": {"apt": "cargo", "desc": "Rust package manager"},
    "rustc": {"apt": "rustc", "desc": "Rust compiler"},
    "make": {"apt": "build-essential", "desc": "Build tools"},
    "gcc": {"apt": "build-essential", "desc": "C compiler"},
    "g++": {"apt": "build-essential", "desc": "C++ compiler"},
    "unzip": {"apt": "unzip", "desc": "Unzip utility"},
    "7z": {"apt": "p7zip-full", "desc": "7-Zip"},
    "netstat": {"apt": "net-tools", "desc": "Network statistics"},
    "ifconfig": {"apt": "net-tools", "desc": "Network interface config"},
    "ip": {"apt": "iproute2", "desc": "IP routing utility"},
    "dig": {"apt": "dnsutils", "desc": "DNS lookup"},
    "nslookup": {"apt": "dnsutils", "desc": "DNS lookup"},
    "host": {"apt": "dnsutils", "desc": "DNS lookup"},
}


class AutoInstaller:
    """Detects missing tools and installs them autonomously.

    This is CRITICAL for PREDATOR's autonomy — when the agent needs a tool
    that isn't installed, it installs it without asking. After the task is done,
    it informs the user what was installed.
    """

    def __init__(self) -> None:
        self._installed: list[InstallResult] = []
        self._install_lock = asyncio.Lock()
        self._checked_cache: dict[str, bool] = {}

    def is_tool_installed(self, tool_name: str) -> bool:
        """Check if a tool binary exists on the system."""
        if tool_name in self._checked_cache:
            return self._checked_cache[tool_name]

        found = shutil.which(tool_name) is not None

        # Check alternative binary names
        if not found and tool_name in TOOL_PACKAGES:
            alt_bins = TOOL_PACKAGES[tool_name].get("alt_bins", [])
            for alt in alt_bins:
                if shutil.which(alt):
                    found = True
                    break

        self._checked_cache[tool_name] = found
        return found

    def get_package_info(self, tool_name: str) -> Optional[dict]:
        """Get package info for a tool."""
        return TOOL_PACKAGES.get(tool_name)

    async def install_tool(self, tool_name: str) -> InstallResult:
        """Install a missing tool autonomously.

        Tries install methods in order: apt → pip → go → gem → npm → cargo → git → manual
        Returns InstallResult with success/failure info.
        """
        async with self._install_lock:
            # Already installed?
            if self.is_tool_installed(tool_name):
                result = InstallResult(
                    tool_name=tool_name,
                    package_name=tool_name,
                    success=True,
                    method="already_installed",
                    already_installed=True,
                )
                return result

            pkg_info = TOOL_PACKAGES.get(tool_name)
            if not pkg_info:
                return InstallResult(
                    tool_name=tool_name,
                    package_name=tool_name,
                    success=False,
                    method="unknown",
                    error=f"No install recipe for '{tool_name}'. Try: apt install {tool_name}",
                )

            # Try each install method in priority order
            install_methods = [
                ("apt", self._install_apt),
                ("pip", self._install_pip),
                ("go", self._install_go),
                ("gem", self._install_gem),
                ("npm", self._install_npm),
                ("cargo", self._install_cargo),
                ("git", self._install_git),
                ("manual", self._install_manual),
            ]

            for method_name, install_fn in install_methods:
                if method_name not in pkg_info:
                    continue

                package = pkg_info[method_name]
                log.info(f"Auto-installing {tool_name} via {method_name}: {package}")

                result = await install_fn(tool_name, package)
                if result.success:
                    # Clear cache so next check sees the new binary
                    self._checked_cache.pop(tool_name, None)
                    self._installed.append(result)
                    log.info(f"Successfully installed {tool_name} via {method_name}")
                    return result
                else:
                    log.warning(f"Failed to install {tool_name} via {method_name}: {result.error}")

            # All methods failed
            return InstallResult(
                tool_name=tool_name,
                package_name=tool_name,
                success=False,
                method="all_failed",
                error=f"All install methods failed for '{tool_name}'",
            )

    async def ensure_tool(self, tool_name: str) -> InstallResult:
        """Ensure a tool is available — install if missing.

        This is the main entry point: call before using any external tool.
        """
        if self.is_tool_installed(tool_name):
            return InstallResult(
                tool_name=tool_name,
                package_name=tool_name,
                success=True,
                method="already_installed",
                already_installed=True,
            )
        return await self.install_tool(tool_name)

    async def ensure_tools(self, tool_names: list[str]) -> list[InstallResult]:
        """Ensure multiple tools are available."""
        results = []
        for name in tool_names:
            result = await self.ensure_tool(name)
            results.append(result)
        return results

    def get_installed_report(self) -> str:
        """Get a report of all tools that were auto-installed during this session.

        This is shown to the user after task completion.
        """
        if not self._installed:
            return ""

        lines = ["[AUTO-INSTALLED TOOLS]"]
        for r in self._installed:
            lines.append(f"  + {r.tool_name} (via {r.method}: {r.package_name})")
        lines.append(f"Total: {len(self._installed)} tools installed automatically.")
        return "\n".join(lines)

    @property
    def installed_tools(self) -> list[InstallResult]:
        return self._installed

    # ─── Private install methods ──────────────────────────────────────

    async def _run_cmd(self, cmd: str, timeout: int = 300) -> tuple[bool, str, str]:
        """Run a shell command and return (success, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            success = proc.returncode == 0
            return success, stdout.decode(errors="replace"), stderr.decode(errors="replace")
        except asyncio.TimeoutError:
            return False, "", "Install timed out"
        except Exception as e:
            return False, "", str(e)

    async def _install_apt(self, tool_name: str, package: str) -> InstallResult:
        """Install via apt-get (Debian/Ubuntu/Kali)."""
        # Update package list first if needed
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        sudo = "" if is_root else "sudo "

        # Try install directly first (faster), then with update if it fails
        cmd = f"DEBIAN_FRONTEND=noninteractive {sudo}apt-get install -y {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        if not success:
            # Try with update
            update_cmd = f"{sudo}apt-get update -qq"
            await self._run_cmd(update_cmd, timeout=120)
            success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        return InstallResult(
            tool_name=tool_name,
            package_name=package,
            success=success,
            method="apt",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_pip(self, tool_name: str, package: str) -> InstallResult:
        """Install via pip3."""
        cmd = f"pip3 install --break-system-packages {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        if not success:
            # Try without --break-system-packages (older pip)
            cmd = f"pip3 install {package}"
            success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        if not success:
            # Try pipx as fallback
            cmd = f"pipx install {package}"
            success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        return InstallResult(
            tool_name=tool_name,
            package_name=package,
            success=success,
            method="pip",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_go(self, tool_name: str, package: str) -> InstallResult:
        """Install via go install."""
        # Ensure Go is installed first
        if not shutil.which("go"):
            go_result = await self._install_apt("go", "golang-go")
            if not go_result.success:
                return InstallResult(
                    tool_name=tool_name, package_name=package,
                    success=False, method="go",
                    error="Go is not installed and could not be auto-installed",
                )

        cmd = f"go install {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=600)

        # Go installs to ~/go/bin — ensure it's in PATH
        if success:
            go_bin = os.path.expanduser("~/go/bin")
            if go_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{go_bin}:{os.environ.get('PATH', '')}"

        return InstallResult(
            tool_name=tool_name,
            package_name=package,
            success=success,
            method="go",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_gem(self, tool_name: str, package: str) -> InstallResult:
        """Install via Ruby gem."""
        if not shutil.which("gem"):
            gem_result = await self._install_apt("ruby", "ruby-full")
            if not gem_result.success:
                return InstallResult(
                    tool_name=tool_name, package_name=package,
                    success=False, method="gem",
                    error="Ruby/gem not available",
                )

        cmd = f"gem install {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        return InstallResult(
            tool_name=tool_name, package_name=package,
            success=success, method="gem",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_npm(self, tool_name: str, package: str) -> InstallResult:
        """Install via npm."""
        if not shutil.which("npm"):
            npm_result = await self._install_apt("npm", "npm")
            if not npm_result.success:
                return InstallResult(
                    tool_name=tool_name, package_name=package,
                    success=False, method="npm",
                    error="npm not available",
                )

        cmd = f"npm install -g {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        return InstallResult(
            tool_name=tool_name, package_name=package,
            success=success, method="npm",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_cargo(self, tool_name: str, package: str) -> InstallResult:
        """Install via cargo (Rust)."""
        if not shutil.which("cargo"):
            return InstallResult(
                tool_name=tool_name, package_name=package,
                success=False, method="cargo",
                error="Cargo/Rust not available",
            )

        cmd = f"cargo install {package}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=600)

        return InstallResult(
            tool_name=tool_name, package_name=package,
            success=success, method="cargo",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_git(self, tool_name: str, repo_url: str) -> InstallResult:
        """Install by cloning a git repo."""
        install_dir = f"/opt/{tool_name}"
        cmd = f"git clone --depth 1 {repo_url} {install_dir}"
        success, stdout, stderr = await self._run_cmd(cmd, timeout=300)

        if success:
            # Try running install script if exists
            for script in ["install.sh", "setup.sh", "install.py", "setup.py"]:
                script_path = f"{install_dir}/{script}"
                if os.path.exists(script_path):
                    if script.endswith(".sh"):
                        await self._run_cmd(f"chmod +x {script_path} && bash {script_path}")
                    else:
                        await self._run_cmd(f"python3 {script_path}")
                    break

            # Symlink main binary if found
            for candidate in [tool_name, f"{tool_name}.py", f"{tool_name}.sh"]:
                candidate_path = f"{install_dir}/{candidate}"
                if os.path.exists(candidate_path):
                    await self._run_cmd(f"chmod +x {candidate_path} && ln -sf {candidate_path} /usr/local/bin/{tool_name}")
                    break

        return InstallResult(
            tool_name=tool_name, package_name=repo_url,
            success=success, method="git",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )

    async def _install_manual(self, tool_name: str, command: str) -> InstallResult:
        """Install via manual command."""
        success, stdout, stderr = await self._run_cmd(command, timeout=600)

        return InstallResult(
            tool_name=tool_name, package_name=command[:80],
            success=success, method="manual",
            output=stdout[-2000:] if stdout else "",
            error=stderr[-1000:] if not success else "",
        )


# Singleton instance
auto_installer = AutoInstaller()

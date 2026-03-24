#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PREDATOR — Install Script for Linux / Kali Linux                  ║
# ║  Autonomous AI Agent for Ethical Hackers & Cybersecurity Pros      ║
# ╚══════════════════════════════════════════════════════════════════════╝

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[-]${NC} $*"; }
info()  { echo -e "${CYAN}[*]${NC} $*"; }

# ── Banner ──
echo -e "${RED}"
cat << 'BANNER'
    ____  ____  __________  ___  __________  ____
   / __ \/ __ \/ ____/ __ \/   |/_  __/ __ \/ __ \
  / /_/ / /_/ / __/ / / / / /| | / / / / / / /_/ /
 / ____/ _, _/ /___/ /_/ / ___ |/ / / /_/ / _, _/
/_/   /_/ |_/_____/_____/_/  |_/_/  \____/_/ |_|

   Autonomous AI Agent for Ethical Hackers v1.0.0
BANNER
echo -e "${NC}"

# ── Pre-checks ──
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    error "PREDATOR is designed for Linux systems only."
    error "Detected OS: $OSTYPE"
    exit 1
fi

PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.11+ is required but not found."
    error "Install with: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PY_VERSION=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    error "Python 3.11+ required, found $PY_VERSION"
    exit 1
fi

log "Found Python $PY_VERSION ($PYTHON_CMD)"

# ── Detect distro ──
DISTRO="unknown"
IS_KALI=false
if [ -f /etc/os-release ]; then
    source /etc/os-release
    DISTRO="$ID"
    if [[ "$ID" == "kali" ]]; then
        IS_KALI=true
        log "Kali Linux detected — full security toolset available"
    fi
fi

# ── Install system dependencies ──
info "Installing system dependencies..."

SUDO=""
if [[ $EUID -ne 0 ]]; then
    SUDO="sudo"
fi

$SUDO apt-get update -qq 2>/dev/null || warn "apt-get update failed (non-critical)"

# Core dependencies
CORE_DEPS="python3-pip python3-venv python3-dev build-essential git curl wget jq"
$SUDO apt-get install -y $CORE_DEPS 2>/dev/null || warn "Some core deps failed (may already be installed)"

# ── Create virtual environment ──
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$INSTALL_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python virtual environment..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
log "Virtual environment activated: $VENV_DIR"

# ── Install PREDATOR ──
info "Installing PREDATOR and dependencies..."
pip install --upgrade pip setuptools wheel 2>/dev/null
pip install -e "$INSTALL_DIR" 2>&1 | tail -5

log "PREDATOR installed successfully!"

# ── Create config directory ──
PREDATOR_HOME="$HOME/.predator"
mkdir -p "$PREDATOR_HOME"/{sessions,memory,plugins,skills,logs}

# Create default config if it doesn't exist
if [[ ! -f "$PREDATOR_HOME/config.yaml" ]]; then
    info "Creating default configuration..."
    cat > "$PREDATOR_HOME/config.yaml" << 'YAML'
# PREDATOR Configuration
# See docs for full options: https://github.com/predator-ai/predator

identity:
  name: PREDATOR
  description: "Autonomous AI agent for ethical hacking & cybersecurity"

providers:
  default: anthropic
  profiles:
    anthropic:
      provider: anthropic
      # api_key: set ANTHROPIC_API_KEY env var
    openai:
      provider: openai
      # api_key: set OPENAI_API_KEY env var

agent:
  model: claude-sonnet-4-20250514
  temperature: 0.3
  max_tokens: 16384
  thinking_budget: 10000

exec:
  timeout: 1800
  security_mode: allowlist

osint:
  passive_only: false
  require_authorization: true
  output_dir: ~/predator-reports

gateway:
  port: 7777
  host: localhost
  bind_mode: loopback

memory:
  enabled: true
  auto_save: true
YAML
    log "Default config created at $PREDATOR_HOME/config.yaml"
fi

# ── Create shell wrapper ──
WRAPPER="/usr/local/bin/predator"
if [[ $EUID -eq 0 ]]; then
    cat > "$WRAPPER" << WRAPPER
#!/usr/bin/env bash
source "$VENV_DIR/bin/activate"
exec python -m predator.entry "\$@"
WRAPPER
    chmod +x "$WRAPPER"
    log "Created system-wide 'predator' command"
else
    $SUDO bash -c "cat > $WRAPPER << WRAPPER
#!/usr/bin/env bash
source \"$VENV_DIR/bin/activate\"
exec python -m predator.entry \"\\\$@\"
WRAPPER"
    $SUDO chmod +x "$WRAPPER"
    log "Created system-wide 'predator' command"
fi

# ── Install optional security tools (Kali has most of these) ──
if $IS_KALI; then
    log "Kali Linux: most security tools are pre-installed"
else
    info "Installing core security tools..."
    SECURITY_TOOLS="nmap whois dnsutils net-tools traceroute curl wget git"
    $SUDO apt-get install -y $SECURITY_TOOLS 2>/dev/null || warn "Some security tools failed to install"

    info "Note: PREDATOR will auto-install additional tools as needed."
    info "Tools like gobuster, ffuf, nuclei, sqlmap will be installed on first use."
fi

# ── Final summary ──
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  PREDATOR INSTALLED SUCCESSFULLY             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Config:${NC}     $PREDATOR_HOME/config.yaml"
echo -e "  ${BOLD}Sessions:${NC}   $PREDATOR_HOME/sessions/"
echo -e "  ${BOLD}Memory:${NC}     $PREDATOR_HOME/memory/"
echo -e "  ${BOLD}Plugins:${NC}    $PREDATOR_HOME/plugins/"
echo ""
echo -e "  ${CYAN}Quick start:${NC}"
echo -e "    1. Set your API key:  export ANTHROPIC_API_KEY=sk-..."
echo -e "    2. Start PREDATOR:    predator agent 'scan example.com'"
echo -e "    3. Start gateway:     predator gateway start"
echo -e "    4. System check:      predator doctor"
echo ""
echo -e "  ${YELLOW}PREDATOR auto-installs missing tools when needed.${NC}"
echo -e "  ${YELLOW}No manual tool installation required!${NC}"
echo ""

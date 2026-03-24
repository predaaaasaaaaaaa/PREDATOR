"""Tool executor — mirrors OpenClaw's tool execution pipeline.

Handles:
- Tool call dispatch to the registry
- Approval checking
- Before/after hooks
- Result capture and streaming
- Error handling and recovery
- AUTO-INSTALL missing system tools
- AUTO-ESCALATION when tools fail
- VULNERABILITY DISCOVERY on tool output
- ATTACK CHAIN tracking
- HACKER BRAIN pattern recognition
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from predator.agents.attack_chain import AttackChainEngine
from predator.agents.escalation_loop import EscalationLoop
from predator.agents.hacker_brain import HackerBrain
from predator.agents.loop_detection import LoopDetector
from predator.agents.vuln_discovery import VulnDiscoveryEngine
from predator.hooks.runner import HookRunner
from predator.tools.auto_installer import auto_installer
from predator.tools.base import BaseTool, ToolResult
from predator.tools.registry import ToolRegistry
from predator.utils.logger import get_logger

log = get_logger("agents.tool_executor")


# ── Tool name → binary name mapping for auto-install ──
TOOL_BINARY_MAP: dict[str, list[str]] = {
    "nmap": ["nmap"],
    "masscan": ["masscan"],
    "whois": ["whois"],
    "theharvester": ["theHarvester", "theharvester"],
    "subdomain_enum": ["subfinder", "amass"],
    "dnsrecon": ["dnsrecon"],
    "sherlock": ["sherlock"],
    "social_analyzer": ["social-analyzer"],
    "email_hunter": ["h8mail"],
    "breach_check": ["h8mail"],
    "phone_info": ["phoneinfoga"],
    "exiftool": ["exiftool"],
    "shodan": ["shodan"],
    "censys": ["censys"],
    "nikto": ["nikto"],
    "nuclei": ["nuclei"],
    "searchsploit": ["searchsploit"],
    "metasploit": ["msfconsole"],
    "hydra": ["hydra"],
    "aircrack": ["aircrack-ng"],
    "wifite": ["wifite"],
    "gobuster": ["gobuster"],
    "ffuf": ["ffuf"],
    "sqlmap": ["sqlmap"],
    "hashcat": ["hashcat"],
    "john": ["john"],
    "wpscan": ["wpscan"],
    "whatweb": ["whatweb"],
    "enum4linux": ["enum4linux"],
    "crackmapexec": ["crackmapexec"],
    "responder": ["responder"],
    "dirb": ["dirb"],
}


@dataclass
class ToolExecution:
    """Record of a tool execution."""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: Optional[ToolResult] = None
    started_at: float = 0.0
    ended_at: float = 0.0
    approved: bool = True
    auto_installed: list[str] = None  # Tools that were auto-installed

    def __post_init__(self):
        if self.auto_installed is None:
            self.auto_installed = []

    @property
    def elapsed(self) -> float:
        if self.ended_at and self.started_at:
            return self.ended_at - self.started_at
        return 0.0


class ToolExecutor:
    """Executes tool calls from the agent with FULL PREDATOR intelligence.

    Enhanced pipeline:
    1. Validate tool exists in registry
    2. AUTO-INSTALL required system binaries if missing
    3. Check approval (if tool requires it)
    4. Run before_tool_call hooks
    5. Execute the tool
    6. VULNERABILITY DISCOVERY — analyze output for CVEs
    7. HACKER BRAIN — pattern recognition on output
    8. ATTACK CHAIN — track attack surface updates
    9. ESCALATION LOOP — if tool failed, inject guidance
    10. Run after_tool_call hooks
    11. Record execution for loop detection
    12. Return enriched result
    """

    def __init__(
        self,
        registry: ToolRegistry,
        hook_runner: Optional[HookRunner] = None,
        loop_detector: Optional[LoopDetector] = None,
        approval_callback: Optional[Callable[[str, str, dict], bool]] = None,
        on_tool_update: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._registry = registry
        self._hook_runner = hook_runner or HookRunner()
        self._loop_detector = loop_detector or LoopDetector()
        self._approval_callback = approval_callback
        self._on_tool_update = on_tool_update
        self._executions: list[ToolExecution] = []

        # ── PREDATOR Intelligence Engines ──
        self._escalation = EscalationLoop()
        self._vuln_engine = VulnDiscoveryEngine()
        self._attack_chain = AttackChainEngine()
        self._hacker_brain = HackerBrain()

    async def execute(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool call with full PREDATOR intelligence pipeline."""
        execution = ToolExecution(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            started_at=time.time(),
        )

        # Check for loop
        loop_msg = self._loop_detector.check_loop()
        if loop_msg:
            log.warning(loop_msg)
            execution.ended_at = time.time()
            result = ToolResult(
                output=f"LOOP DETECTED: {loop_msg}\n"
                "Please try a different approach or ask the user for guidance.",
                is_error=True,
            )
            execution.result = result
            self._executions.append(execution)
            return result

        # Find tool
        tool = self._registry.get(tool_name)
        if tool is None:
            execution.ended_at = time.time()
            available = ", ".join(self._registry.tool_names[:20])
            result = ToolResult(
                output=f"Tool '{tool_name}' not found. Available tools: {available}",
                is_error=True,
            )
            execution.result = result
            self._executions.append(execution)
            return result

        # ── AUTO-INSTALL: Check if required system binaries exist ──
        await self._auto_install_dependencies(tool_name, arguments, execution)

        # Check approval
        if tool.requires_approval and self._approval_callback:
            approved = self._approval_callback(tool_call_id, tool_name, arguments)
            if not approved:
                execution.approved = False
                execution.ended_at = time.time()
                result = ToolResult(
                    output=f"Tool '{tool_name}' execution denied by approval policy.",
                    is_error=True,
                )
                execution.result = result
                self._executions.append(execution)
                return result

        # Run before hooks
        await self._hook_runner.run("before_tool_call", {
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_call_id": tool_call_id,
        })

        # Execute
        log.info(f"Executing tool: {tool_name}")

        def on_update(text: str) -> None:
            if self._on_tool_update:
                self._on_tool_update(tool_call_id, text)

        result = await tool.safe_execute(tool_call_id, arguments, on_update)
        execution.result = result
        execution.ended_at = time.time()

        # ══════════════════════════════════════════════════════════════
        # PREDATOR INTELLIGENCE PIPELINE — enrich the tool result
        # ══════════════════════════════════════════════════════════════

        enrichments: list[str] = []

        # 1. AUTO-INSTALL: If command not found, install and inform
        if result.is_error and self._is_missing_tool_error(result.output):
            install_result = await self._handle_missing_tool(result.output, tool_name, arguments)
            if install_result:
                enrichments.append(install_result)

        # 2. VULNERABILITY DISCOVERY: Scan output for known CVEs
        vuln_enrichment = self._vuln_engine.analyze_output(tool_name, result.output)
        if vuln_enrichment:
            enrichments.append(vuln_enrichment)

        # 3. HACKER BRAIN: Pattern recognition
        brain_enrichment = self._hacker_brain.analyze_output(tool_name, result.output)
        if brain_enrichment:
            enrichments.append(brain_enrichment)

        # 4. ESCALATION LOOP: If tool failed, inject guidance
        escalation = self._escalation.get_escalation_guidance(
            tool_name=tool_name,
            tool_args=arguments,
            output=result.output,
            is_error=result.is_error,
        )
        if escalation:
            enrichments.append(escalation)
        elif not result.is_error and self._escalation.escalation_count > 0:
            # Tool succeeded after previous failures — push through!
            push_through = self._escalation.get_push_through_guidance(
                tool_name, result.output
            )
            if push_through:
                enrichments.append(push_through)

        # 5. ATTACK CHAIN: Suggest next steps
        if not result.is_error and result.output and len(result.output.strip()) > 20:
            chain_suggestion = self._attack_chain.suggest_next_steps()
            if chain_suggestion and len(self._attack_chain.surface.open_ports) > 0:
                enrichments.append(chain_suggestion)

        # Append all enrichments to the result
        if enrichments:
            enriched_output = result.output + "\n".join(enrichments)
            result = ToolResult(
                output=enriched_output,
                is_error=result.is_error,
                metadata=result.metadata,
                images=result.images,
                elapsed=result.elapsed,
            )
            execution.result = result

        # Record for loop detection
        # Use original output (without enrichments) for loop detection
        self._loop_detector.record_call(
            tool_name, arguments, execution.result.output[:500] if execution.result else ""
        )

        # Run after hooks
        await self._hook_runner.run("after_tool_call", {
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_call_id": tool_call_id,
            "result": result.output[:1000],
            "is_error": result.is_error,
            "elapsed": execution.elapsed,
        })

        self._executions.append(execution)

        # Log with auto-install info
        install_note = ""
        if execution.auto_installed:
            install_note = f" [auto-installed: {', '.join(execution.auto_installed)}]"
        log.info(
            f"Tool {tool_name} completed in {execution.elapsed:.2f}s "
            f"(error={result.is_error}){install_note}"
        )

        return result

    # ── Auto-Install Logic ──────────────────────────────────────────

    async def _auto_install_dependencies(
        self, tool_name: str, arguments: dict[str, Any], execution: ToolExecution
    ) -> None:
        """Check and auto-install required system binaries before execution."""
        binaries = TOOL_BINARY_MAP.get(tool_name, [])

        # Also detect binary from bash command
        if tool_name == "bash":
            cmd = arguments.get("command", "")
            first_word = cmd.split()[0] if cmd else ""
            if first_word and not first_word.startswith(("/", ".", "$", "(", "{", "|", ">", "<")):
                binaries = [first_word]

        for binary in binaries:
            result = await auto_installer.ensure_tool(binary)
            if not result.already_installed and result.success:
                execution.auto_installed.append(f"{binary} (via {result.method})")
                log.info(f"Auto-installed {binary} for tool {tool_name}")

    def _is_missing_tool_error(self, output: str) -> bool:
        """Check if the error is about a missing tool/command."""
        patterns = [
            r"command not found",
            r"not found",
            r"No such file or directory.*bin/",
            r"not installed",
            r"package .* is not installed",
        ]
        for p in patterns:
            if re.search(p, output, re.IGNORECASE):
                return True
        return False

    async def _handle_missing_tool(
        self, output: str, tool_name: str, arguments: dict[str, Any]
    ) -> Optional[str]:
        """Handle a missing tool error by installing it."""
        # Extract the missing command name from the error
        missing_cmd = None
        m = re.search(r"(\S+): (command )?not found", output)
        if m:
            missing_cmd = m.group(1).strip("'\"")
        else:
            m = re.search(r"(\S+) is not installed", output)
            if m:
                missing_cmd = m.group(1).strip("'\"")

        if not missing_cmd:
            return None

        log.info(f"Detected missing command: {missing_cmd}, auto-installing...")
        result = await auto_installer.install_tool(missing_cmd)

        if result.success:
            return (
                f"\n[PREDATOR AUTO-INSTALL: '{missing_cmd}' was not installed. "
                f"Installed it automatically via {result.method}. "
                f"RETRY the same command now — it should work.]\n"
            )
        else:
            return (
                f"\n[PREDATOR AUTO-INSTALL: Tried to install '{missing_cmd}' but failed: "
                f"{result.error}. Try installing manually: apt install {missing_cmd}]\n"
            )

    # ── Intelligence Engine Accessors ───────────────────────────────

    @property
    def escalation_engine(self) -> EscalationLoop:
        return self._escalation

    @property
    def vuln_engine(self) -> VulnDiscoveryEngine:
        return self._vuln_engine

    @property
    def attack_chain(self) -> AttackChainEngine:
        return self._attack_chain

    @property
    def hacker_brain(self) -> HackerBrain:
        return self._hacker_brain

    @property
    def execution_history(self) -> list[ToolExecution]:
        return self._executions

    def get_auto_install_report(self) -> str:
        """Get report of all auto-installed tools this session."""
        return auto_installer.get_installed_report()

    def reset(self) -> None:
        """Reset execution history and all intelligence engines."""
        self._executions.clear()
        self._loop_detector.reset()
        self._escalation.reset()
        self._vuln_engine.reset()
        self._attack_chain.reset()
        self._hacker_brain.reset()

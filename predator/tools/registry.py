"""Tool registry — mirrors OpenClaw's tool registration and discovery system.

Central registry for all tools available to the agent.
Supports:
- Tool registration/deregistration
- Category-based filtering
- Allow/block list enforcement
- Plugin tool registration
"""

from __future__ import annotations

from typing import Optional

from predator.tools.base import BaseTool, ToolCategory
from predator.utils.logger import get_logger

log = get_logger("tools.registry")


class ToolRegistry:
    """Central registry of all PREDATOR tools.

    Mirrors OpenClaw's tool registration pattern where:
    - Core tools are registered at startup
    - Plugin tools can be added dynamically
    - Allow/block lists filter available tools per agent
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        if tool.name in self._tools:
            log.warning(f"Tool '{tool.name}' already registered, replacing")
        self._tools[tool.name] = tool
        log.debug(f"Registered tool: {tool.name} [{tool.category.value}]")

    def unregister(self, name: str) -> Optional[BaseTool]:
        """Unregister a tool by name."""
        return self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[BaseTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_by_category(self, category: ToolCategory) -> list[BaseTool]:
        """Get tools by category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_filtered(
        self,
        allowed: Optional[list[str]] = None,
        blocked: Optional[list[str]] = None,
        categories: Optional[list[ToolCategory]] = None,
    ) -> list[BaseTool]:
        """Get tools filtered by allow/block lists and categories.

        Mirrors OpenClaw's agent tool policy:
        - If allowed is set, only those tools are available
        - If blocked is set, those tools are excluded
        - Categories further filter the result
        """
        tools = list(self._tools.values())

        if allowed:
            tools = [t for t in tools if t.name in allowed]

        if blocked:
            tools = [t for t in tools if t.name not in blocked]

        if categories:
            tools = [t for t in tools if t.category in categories]

        return tools

    def get_llm_schemas(
        self,
        allowed: Optional[list[str]] = None,
        blocked: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get LLM-compatible tool schemas for all available tools."""
        tools = self.get_filtered(allowed=allowed, blocked=blocked)
        return [tool.to_llm_schema() for tool in tools]

    @property
    def tool_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    @property
    def count(self) -> int:
        return len(self._tools)

    def summary(self) -> dict[str, int]:
        """Category-wise tool count summary."""
        result: dict[str, int] = {}
        for tool in self._tools.values():
            key = tool.category.value
            result[key] = result.get(key, 0) + 1
        return result


def create_default_registry() -> ToolRegistry:
    """Create a registry with all default PREDATOR tools registered.

    Mirrors OpenClaw's tool initialization — registers core tools at startup.
    """
    registry = ToolRegistry()

    # Import and register core tools
    from predator.tools.bash import BashTool
    from predator.tools.file_ops import (
        ReadFileTool,
        WriteFileTool,
        ListDirectoryTool,
        SearchFilesTool,
        GrepTool,
    )
    from predator.tools.web import WebFetchTool

    # Core system tools
    registry.register(BashTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListDirectoryTool())
    registry.register(SearchFilesTool())
    registry.register(GrepTool())
    registry.register(WebFetchTool())

    # OSINT tools
    from predator.tools.osint.recon import NmapTool, MasscanTool
    from predator.tools.osint.domain import (
        WhoisTool,
        TheHarvesterTool,
        SubdomainEnumTool,
        DnsReconTool,
    )
    from predator.tools.osint.social import SherlockTool, SocialAnalyzerTool
    from predator.tools.osint.email import EmailHunterTool, BreachCheckTool
    from predator.tools.osint.phone import PhoneInfoTool
    from predator.tools.osint.metadata import ExifTool
    from predator.tools.osint.network import ShodanTool, CensysTool
    from predator.tools.osint.browser import (
        BrowserNavigateTool,
        BrowserScreenshotTool,
        BrowserExtractTool,
    )

    registry.register(NmapTool())
    registry.register(MasscanTool())
    registry.register(WhoisTool())
    registry.register(TheHarvesterTool())
    registry.register(SubdomainEnumTool())
    registry.register(DnsReconTool())
    registry.register(SherlockTool())
    registry.register(SocialAnalyzerTool())
    registry.register(EmailHunterTool())
    registry.register(BreachCheckTool())
    registry.register(PhoneInfoTool())
    registry.register(ExifTool())
    registry.register(ShodanTool())
    registry.register(CensysTool())

    # Browser OSINT tools
    registry.register(BrowserNavigateTool())
    registry.register(BrowserScreenshotTool())
    registry.register(BrowserExtractTool())

    # Pentesting tools
    from predator.tools.pentesting.vuln_scan import NiktoTool, NucleiTool
    from predator.tools.pentesting.exploit import (
        SearchSploitTool,
        MetasploitTool,
        HydraTool,
    )
    from predator.tools.pentesting.wireless import AircrackTool, WifiteTool

    registry.register(NiktoTool())
    registry.register(NucleiTool())
    registry.register(SearchSploitTool())
    registry.register(MetasploitTool())
    registry.register(HydraTool())
    registry.register(AircrackTool())
    registry.register(WifiteTool())

    # Web attack tools (gobuster, ffuf, sqlmap, hashcat, john, wpscan, dalfox, commix)
    from predator.tools.pentesting.web_attack import (
        GobusterTool,
        FfufTool,
        SqlmapTool,
        HashcatTool,
        JohnTool,
        WpscanTool,
        DalfoxTool,
        CommixTool,
    )

    registry.register(GobusterTool())
    registry.register(FfufTool())
    registry.register(SqlmapTool())
    registry.register(HashcatTool())
    registry.register(JohnTool())
    registry.register(WpscanTool())
    registry.register(DalfoxTool())
    registry.register(CommixTool())

    # Credential attack & post-exploitation tools
    from predator.tools.pentesting.credential_attack import (
        CrackMapExecTool,
        ImpacketTool,
        ResponderTool,
        ChiselTool,
        Enum4linuxTool,
        LinpeasTool,
    )

    registry.register(CrackMapExecTool())
    registry.register(ImpacketTool())
    registry.register(ResponderTool())
    registry.register(ChiselTool())
    registry.register(Enum4linuxTool())
    registry.register(LinpeasTool())

    # Advanced OSINT tools (subfinder, amass, waybackurls, gau, katana, httpx, crtsh)
    from predator.tools.osint.advanced import (
        SubfinderTool,
        AmassTool,
        WaybackUrlsTool,
        GauTool,
        KatanaTool,
        HttpxTool,
        CrtshTool,
    )

    registry.register(SubfinderTool())
    registry.register(AmassTool())
    registry.register(WaybackUrlsTool())
    registry.register(GauTool())
    registry.register(KatanaTool())
    registry.register(HttpxTool())
    registry.register(CrtshTool())

    # Agent-facing tools (autonomous capabilities)
    from predator.agents.tools.web_search_tool import WebSearchTool as AgentWebSearch, WebFetchReadableTool
    from predator.agents.tools.memory_tool import MemorySaveTool, MemoryRecallTool, MemoryTargetTool
    from predator.agents.tools.message_tool import SendMessageTool, SendAlertTool
    from predator.agents.tools.cron_tool import CronCreateTool, CronListTool, CronManageTool
    from predator.agents.tools.session_tool import SessionListTool, SessionHistoryTool, SessionDeleteTool
    from predator.agents.tools.model_tool import SwitchModelTool, ListModelsTool

    registry.register(AgentWebSearch())
    registry.register(WebFetchReadableTool())
    registry.register(MemorySaveTool())
    registry.register(MemoryRecallTool())
    registry.register(MemoryTargetTool())
    registry.register(SendMessageTool())
    registry.register(SendAlertTool())
    registry.register(CronCreateTool())
    registry.register(CronListTool())
    registry.register(CronManageTool())
    registry.register(SessionListTool())
    registry.register(SessionHistoryTool())
    registry.register(SessionDeleteTool())
    registry.register(SwitchModelTool())
    registry.register(ListModelsTool())

    # Channel action tools (platform-specific rich interactions)
    from predator.agents.tools.channel_actions import (
        TelegramActionsTool,
        DiscordActionsTool,
        SlackActionsTool,
    )

    registry.register(TelegramActionsTool())
    registry.register(DiscordActionsTool())
    registry.register(SlackActionsTool())

    # Subagent tools (multi-agent orchestration)
    from predator.agents.tools.subagent_tool import (
        SubagentSpawnTool,
        SubagentListTool,
        SubagentWaitTool,
        SubagentKillTool,
        SubagentSteerTool,
    )

    registry.register(SubagentSpawnTool())
    registry.register(SubagentListTool())
    registry.register(SubagentWaitTool())
    registry.register(SubagentKillTool())
    registry.register(SubagentSteerTool())

    log.info(f"Default tool registry created with {registry.count} tools")
    return registry

"""Base tool definitions — mirrors OpenClaw's AgentTool interface.

All PREDATOR tools inherit from BaseTool and register via the ToolRegistry.
Tools are exposed to the LLM as callable functions with JSON Schema parameters.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ToolCategory(str, Enum):
    """Tool categories — extends OpenClaw's categories for cybersecurity."""

    SYSTEM = "system"           # Bash, file ops, process management
    BROWSER = "browser"         # Web browsing and automation
    WEB = "web"                 # HTTP requests, web search
    OSINT = "osint"             # OSINT tools (recon, domain, social, etc.)
    PENTESTING = "pentesting"   # Exploitation, vuln scanning, wireless
    FORENSICS = "forensics"     # Digital forensics tools
    NETWORK = "network"         # Network analysis and scanning
    REPORTING = "reporting"     # Report generation
    UTILITY = "utility"        # Misc utilities
    SESSION = "session"         # Session/agent management
    MEMORY = "memory"           # Knowledge/memory operations


@dataclass
class ToolParameter:
    """A single tool parameter definition."""

    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[list[str]] = None


@dataclass
class ToolResult:
    """Result of a tool execution — mirrors OpenClaw's AgentToolResult."""

    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)  # Base64 or file paths
    elapsed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"output": self.output, "is_error": self.is_error}
        if self.metadata:
            result["metadata"] = self.metadata
        if self.images:
            result["images"] = self.images
        return result


class BaseTool(ABC):
    """Base class for all PREDATOR tools.

    Mirrors OpenClaw's AgentTool interface:
    - name: Unique tool identifier
    - description: Human-readable description (shown to LLM)
    - category: Tool category for filtering
    - parameters: JSON Schema parameters
    - execute(): Async execution method
    """

    name: str
    description: str
    category: ToolCategory = ToolCategory.UTILITY
    requires_approval: bool = False  # Mirrors OpenClaw's approval system
    owner_only: bool = False

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return JSON Schema for tool parameters.

        Must return a dict with:
        {
            "type": "object",
            "properties": { ... },
            "required": [ ... ]
        }
        """
        ...

    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            tool_call_id: Unique ID for this tool invocation
            arguments: Parsed arguments matching the parameter schema
            on_update: Optional callback for streaming partial results

        Returns:
            ToolResult with output and metadata
        """
        ...

    def to_llm_schema(self) -> dict[str, Any]:
        """Convert to the format expected by LLM APIs (Anthropic/OpenAI tool schema)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_parameters(),
        }

    def validate_args(self, arguments: dict[str, Any]) -> Optional[str]:
        """Basic argument validation. Returns error message or None."""
        schema = self.get_parameters()
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for param_name in required:
            if param_name not in arguments:
                return f"Missing required parameter: {param_name}"

        for param_name, value in arguments.items():
            if param_name not in properties:
                continue  # Allow extra params
            expected_type = properties[param_name].get("type")
            if expected_type == "string" and not isinstance(value, str):
                return f"Parameter '{param_name}' must be a string"
            if expected_type == "number" and not isinstance(value, (int, float)):
                return f"Parameter '{param_name}' must be a number"
            if expected_type == "boolean" and not isinstance(value, bool):
                return f"Parameter '{param_name}' must be a boolean"
            if expected_type == "array" and not isinstance(value, list):
                return f"Parameter '{param_name}' must be an array"

        return None

    async def safe_execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        """Execute with validation and error handling."""
        # Validate
        error = self.validate_args(arguments)
        if error:
            return ToolResult(output=error, is_error=True)

        # Execute with timing
        start = time.time()
        try:
            result = await self.execute(tool_call_id, arguments, on_update)
            result.elapsed = time.time() - start
            return result
        except Exception as e:
            return ToolResult(
                output=f"Tool error: {type(e).__name__}: {str(e)}",
                is_error=True,
                elapsed=time.time() - start,
            )

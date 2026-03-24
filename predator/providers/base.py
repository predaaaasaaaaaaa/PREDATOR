"""Base LLM provider — mirrors OpenClaw's provider abstraction layer.

All providers implement the same interface for model interaction,
supporting streaming, tool use, and thinking/reasoning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


@dataclass
class ModelMessage:
    """A message in the conversation."""

    role: str  # system, user, assistant, tool
    content: str | list[dict[str, Any]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


@dataclass
class ModelRequest:
    """Request to the LLM — mirrors OpenClaw's agent request building."""

    messages: list[ModelMessage]
    model: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 8192
    thinking_budget: Optional[int] = None
    system_prompt: Optional[str] = None
    stop_sequences: Optional[list[str]] = None


@dataclass
class ToolCall:
    """A tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamEvent:
    """A streaming event from the model."""

    type: str  # text_delta, tool_call_start, tool_call_delta, thinking, done, error
    text: str = ""
    tool_call: Optional[ToolCall] = None
    thinking: str = ""
    usage: Optional[dict[str, int]] = None


@dataclass
class ModelResponse:
    """Complete response from the LLM."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str = ""
    stop_reason: str = ""  # end_turn, tool_use, max_tokens
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    raw: Optional[Any] = None


class BaseProvider(ABC):
    """Base class for LLM providers.

    Mirrors OpenClaw's provider pattern:
    - Auth profile management
    - Streaming support
    - Tool use support
    - Rate limiting awareness
    - Cooldown management
    """

    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Send a completion request and return the full response."""
        ...

    @abstractmethod
    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        """Send a completion request and stream events."""
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this provider has valid credentials."""
        ...

"""Channel system types — mirrors OpenClaw's channel plugin architecture."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol

class ChatType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    CHANNEL = "channel"

class DeliveryMode(str, Enum):
    DIRECT = "direct"      # Bot token → platform API directly
    GATEWAY = "gateway"    # Via PREDATOR gateway
    HYBRID = "hybrid"      # Support both

@dataclass
class ChannelMeta:
    id: str
    label: str
    blurb: str = ""
    docs_path: str = ""
    order: int = 99
    aliases: list[str] = field(default_factory=list)

@dataclass
class ChannelCapabilities:
    threads: bool = False
    reactions: bool = False
    polls: bool = False
    media: bool = False
    buttons: bool = False
    voice: bool = False
    video: bool = False
    location: bool = False

@dataclass
class InboundMessage:
    """Normalized inbound message from any chat platform."""
    id: str = ""
    sender_id: str = ""
    conversation_id: str = ""
    to: str = ""
    account_id: str = ""
    body: str = ""
    chat_type: ChatType = ChatType.DIRECT
    sender_name: str = ""
    sender_username: str = ""
    reply_to_id: str = ""
    reply_to_body: str = ""
    group_subject: str = ""
    timestamp: int = 0
    media_url: str = ""
    media_path: str = ""
    media_type: str = ""
    mentioned_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class MessageContext:
    """Full context for routing an inbound message to the agent."""
    channel: str = ""
    sender_id: str = ""
    sender_name: str = ""
    sender_username: str = ""
    to: str = ""
    chat_type: ChatType = ChatType.DIRECT
    body: str = ""
    body_for_agent: str = ""
    body_for_commands: str = ""
    reply_to_id: str = ""
    reply_to_body: str = ""
    thread_label: str = ""
    message_thread_id: str = ""
    session_key: str = ""
    main_session_key: str = ""
    command_authorized: bool = False
    media_url: str = ""
    media_path: str = ""
    media_type: str = ""
    account_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class ReplyPayload:
    """Agent response to deliver back to the channel."""
    text: str = ""
    media_url: str = ""
    media_urls: list[str] = field(default_factory=list)
    format: Literal["plain", "markdown", "html"] = "markdown"
    channel_data: dict[str, Any] = field(default_factory=dict)

@dataclass
class OutboundResult:
    """Result from delivering a message to a platform."""
    channel: str = ""
    message_id: str = ""
    chat_id: str = ""
    conversation_id: str = ""
    timestamp: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass
class ChannelAccountSnapshot:
    """Health/status snapshot for a channel account."""
    account_id: str = ""
    name: str = ""
    enabled: bool = False
    configured: bool = False
    running: bool = False
    connected: bool = False
    reconnect_attempts: int = 0
    last_connected_at: int | None = None
    last_message_at: int | None = None
    last_error: str | None = None
    mode: str = ""

class ChannelPlugin(ABC):
    """Base class for all channel plugins."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def meta(self) -> ChannelMeta: ...

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities()

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.DIRECT

    @property
    def text_chunk_limit(self) -> int:
        return 4000

    # Config
    def list_account_ids(self, config: Any) -> list[str]:
        return []

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        return {}

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        return False

    # Gateway (start/stop listeners)
    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        pass

    async def stop_account(self, account_id: str) -> None:
        pass

    # Outbound (send messages)
    async def send_text(self, to: str, text: str, account_id: str | None = None, reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        raise NotImplementedError(f"Channel {self.id} does not support sending text")

    async def send_media(self, to: str, caption: str, media_url: str, account_id: str | None = None) -> OutboundResult:
        raise NotImplementedError(f"Channel {self.id} does not support sending media")

    # Message normalization
    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        raise NotImplementedError

    # Text chunking
    def chunk_text(self, text: str) -> list[str]:
        limit = self.text_chunk_limit
        if len(text) <= limit:
            return [text]
        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, limit)
            if split_at < limit // 2:
                split_at = text.rfind(" ", 0, limit)
            if split_at < limit // 4:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks

    # Security
    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        return True

    # Status
    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        return ChannelAccountSnapshot(account_id=account_id)

"""Anthropic (Claude) provider — mirrors OpenClaw's Anthropic integration.

Primary LLM provider for PREDATOR, supporting:
- Claude Opus, Sonnet, Haiku models
- Extended thinking
- Tool use with streaming
- Vision (image analysis)
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Optional

from predator.providers.base import (
    BaseProvider,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ProviderType,
    StreamEvent,
    ToolCall,
)
from predator.utils.logger import get_logger

log = get_logger("providers.anthropic")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    provider_type = ProviderType.ANTHROPIC

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = base_url
        self.default_model = default_model
        self._client = None

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if self._client is None:
            import anthropic

            kwargs: dict[str, Any] = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = anthropic.AsyncAnthropic(**kwargs)
        return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        """Convert ModelMessages to Anthropic API format."""
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                continue  # System prompt handled separately

            entry: dict[str, Any] = {"role": msg.role}

            if msg.role == "tool":
                entry = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                        }
                    ],
                }
            elif msg.tool_calls:
                # Assistant message with tool calls
                content_blocks: list[dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"],
                    })
                entry["content"] = content_blocks
            else:
                entry["content"] = msg.content

            messages.append(entry)
        return messages

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tool schemas to Anthropic format."""
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in tools
        ]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Send a completion request to Claude."""
        client = self._get_client()
        model = request.model or self.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.system_prompt:
            kwargs["system"] = request.system_prompt

        if request.tools:
            kwargs["tools"] = self._build_tools(request.tools)

        if request.thinking_budget:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": request.thinking_budget,
            }
            # Remove temperature when thinking is enabled
            kwargs.pop("temperature", None)

        log.debug(f"Sending request to {model}")
        response = await client.messages.create(**kwargs)

        # Parse response
        content_text = ""
        thinking_text = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "thinking":
                thinking_text += block.thinking
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        return ModelResponse(
            content=content_text,
            tool_calls=tool_calls,
            thinking=thinking_text,
            stop_reason=response.stop_reason or "",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            model=model,
            raw=response,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        """Stream response from Claude."""
        client = self._get_client()
        model = request.model or self.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.system_prompt:
            kwargs["system"] = request.system_prompt

        if request.tools:
            kwargs["tools"] = self._build_tools(request.tools)

        if request.thinking_budget:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": request.thinking_budget,
            }
            kwargs.pop("temperature", None)

        async with client.messages.stream(**kwargs) as stream:
            current_tool_id = ""
            current_tool_name = ""
            tool_input_json = ""

            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id = block.id
                        current_tool_name = block.name
                        tool_input_json = ""
                        yield StreamEvent(
                            type="tool_call_start",
                            tool_call=ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments={},
                            ),
                        )
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamEvent(type="text_delta", text=delta.text)
                    elif delta.type == "thinking_delta":
                        yield StreamEvent(type="thinking", thinking=delta.thinking)
                    elif delta.type == "input_json_delta":
                        tool_input_json += delta.partial_json
                elif event.type == "content_block_stop":
                    if current_tool_id and tool_input_json:
                        try:
                            args = json.loads(tool_input_json)
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamEvent(
                            type="tool_call_start",
                            tool_call=ToolCall(
                                id=current_tool_id,
                                name=current_tool_name,
                                arguments=args,
                            ),
                        )
                        current_tool_id = ""
                        tool_input_json = ""
                elif event.type == "message_stop":
                    final = await stream.get_final_message()
                    yield StreamEvent(
                        type="done",
                        usage={
                            "input_tokens": final.usage.input_tokens,
                            "output_tokens": final.usage.output_tokens,
                        },
                    )

    async def list_models(self) -> list[str]:
        """List available Claude models."""
        return [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
        ]

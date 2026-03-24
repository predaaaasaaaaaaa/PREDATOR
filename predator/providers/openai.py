"""OpenAI provider — mirrors OpenClaw's OpenAI integration.

Supports GPT-4, GPT-4o, o1, o3 models with tool use and streaming.
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

log = get_logger("providers.openai")


class OpenAIProvider(BaseProvider):
    """OpenAI GPT provider."""

    provider_type = ProviderType.OPENAI

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url
        self.default_model = default_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            kwargs: dict[str, Any] = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key or os.environ.get("OPENAI_API_KEY"))

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        for msg in request.messages:
            if msg.role == "system":
                continue

            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}

            if msg.role == "tool":
                entry["tool_call_id"] = msg.tool_call_id

            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            messages.append(entry)
        return messages

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._get_client()
        model = request.model or self.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.tools:
            kwargs["tools"] = self._build_tools(request.tools)

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        return ModelResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "",
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            model=model,
            raw=response,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        client = self._get_client()
        model = request.model or self.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.tools:
            kwargs["tools"] = self._build_tools(request.tools)

        stream = await client.chat.completions.create(**kwargs)
        tool_calls_acc: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                yield StreamEvent(type="text_delta", text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

            finish = chunk.choices[0].finish_reason if chunk.choices else None
            if finish:
                # Emit accumulated tool calls
                for acc in tool_calls_acc.values():
                    try:
                        args = json.loads(acc["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    yield StreamEvent(
                        type="tool_call_start",
                        tool_call=ToolCall(id=acc["id"], name=acc["name"], arguments=args),
                    )
                yield StreamEvent(type="done")

    async def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o3-mini"]

"""Ollama provider — local model inference for offline/airgapped operations.

Mirrors OpenClaw's Ollama support for running models locally.
Critical for sensitive pentesting engagements where data can't leave the machine.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx

from predator.providers.base import (
    BaseProvider,
    ModelRequest,
    ModelResponse,
    ProviderType,
    StreamEvent,
    ToolCall,
)
from predator.utils.logger import get_logger

log = get_logger("providers.ollama")


class OllamaProvider(BaseProvider):
    """Ollama local model provider."""

    provider_type = ProviderType.OLLAMA

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def is_configured(self) -> bool:
        """Check if Ollama is running."""
        try:
            import httpx as h

            r = h.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            if msg.role == "system":
                continue
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    async def complete(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self.default_model

        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in request.tools
            ]

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        tool_calls: list[ToolCall] = []

        raw_tools = data.get("message", {}).get("tool_calls", [])
        for i, tc in enumerate(raw_tools):
            func = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=f"ollama_{i}",
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {}),
                )
            )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason="end_turn",
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
            model=model,
            raw=data,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamEvent]:
        model = request.model or self.default_model

        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield StreamEvent(type="text_delta", text=content)

                    if data.get("done"):
                        yield StreamEvent(
                            type="done",
                            usage={
                                "input_tokens": data.get("prompt_eval_count", 0),
                                "output_tokens": data.get("eval_count", 0),
                            },
                        )

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

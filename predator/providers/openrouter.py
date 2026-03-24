"""OpenRouter provider — aggregated access to 100+ LLMs.

OpenRouter uses the OpenAI-compatible API format, so we subclass the
OpenAI provider and just swap the base URL and auth header.
"""

from __future__ import annotations

import os
from typing import Optional

from predator.providers.openai import OpenAIProvider
from predator.providers.base import ProviderType
from predator.utils.logger import get_logger

log = get_logger("providers.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter provider — OpenAI-compatible API for 100+ models.

    Uses the same wire format as OpenAI, just with a different base URL
    and API key. Supports Claude, GPT, Llama, Mistral, Gemini, etc.
    """

    provider_type = ProviderType.OPENROUTER

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "anthropic/claude-sonnet-4-20250514",
    ) -> None:
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        resolved_url = base_url or OPENROUTER_BASE_URL

        super().__init__(
            api_key=resolved_key,
            base_url=resolved_url,
            default_model=default_model,
        )

        log.debug(f"OpenRouter provider: model={default_model}")

    def is_configured(self) -> bool:
        return bool(self.api_key)

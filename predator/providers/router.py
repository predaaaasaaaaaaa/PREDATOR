"""Provider router — runtime model switching for PREDATOR.

Holds all configured LLM providers and enables switching between them
mid-conversation. Providers are lazy-initialized on first use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from predator.config.schema import ProvidersConfig
from predator.providers.base import BaseProvider, ProviderType
from predator.utils.logger import get_logger

log = get_logger("providers.router")


@dataclass
class ProviderInfo:
    """Summary of a configured provider and its models."""

    name: str
    provider_type: str
    is_configured: bool
    is_active: bool
    default_model: Optional[str] = None
    available_models: list[str] = field(default_factory=list)


class ProviderRouter:
    """Routes LLM requests to the active provider.

    Supports runtime switching between providers/models without
    restarting the agent. Providers are lazy-initialized — they are
    only created the first time they are selected.
    """

    def __init__(self, providers_config: ProvidersConfig) -> None:
        self._config = providers_config
        self._active_name: str = providers_config.default
        self._providers: dict[str, BaseProvider] = {}
        self._model_overrides: dict[str, str] = {}  # provider_name -> model override

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current(self) -> BaseProvider:
        """Return the currently active provider, initializing it if needed."""
        return self._get_or_create(self._active_name)

    @property
    def current_name(self) -> str:
        """Return the name of the currently active provider."""
        return self._active_name

    @property
    def current_model(self) -> Optional[str]:
        """Return the model override for the active provider, if any."""
        return self._model_overrides.get(self._active_name)

    def switch(self, provider_name: str, model: Optional[str] = None) -> BaseProvider:
        """Switch the active provider and optionally override the model.

        Args:
            provider_name: Name of the provider profile (e.g. 'anthropic', 'openai').
            model: Optional model identifier to use with the provider.

        Returns:
            The newly active BaseProvider instance.

        Raises:
            ValueError: If the provider name is not configured.
        """
        if provider_name not in self._config.profiles:
            available = ", ".join(self._config.profiles.keys())
            raise ValueError(
                f"Provider '{provider_name}' is not configured. "
                f"Available providers: {available}"
            )

        self._active_name = provider_name

        if model is not None:
            self._model_overrides[provider_name] = model
            # If the provider is already initialized, update its default_model
            if provider_name in self._providers:
                provider = self._providers[provider_name]
                if hasattr(provider, "default_model"):
                    provider.default_model = model

        provider = self._get_or_create(provider_name)
        log.info(
            f"Switched to provider '{provider_name}'"
            + (f" with model '{model}'" if model else "")
        )
        return provider

    def list_available(self) -> list[ProviderInfo]:
        """List all configured providers with their status and models.

        Returns:
            List of ProviderInfo with details about each configured provider.
        """
        result: list[ProviderInfo] = []

        for name, profile in self._config.profiles.items():
            # Determine if the provider is initialized and configured
            is_initialized = name in self._providers
            is_configured = False
            available_models: list[str] = []

            if is_initialized:
                provider = self._providers[name]
                is_configured = provider.is_configured()
            else:
                # Check basic configuration without initializing
                is_configured = bool(profile.api_key) or profile.provider == "ollama"

            # Determine the default model
            default_model = self._model_overrides.get(name) or profile.model

            result.append(ProviderInfo(
                name=name,
                provider_type=profile.provider,
                is_configured=is_configured,
                is_active=(name == self._active_name),
                default_model=default_model,
                available_models=available_models,
            ))

        return result

    async def list_models(self, provider_name: Optional[str] = None) -> list[str]:
        """List models for a provider. Defaults to the active provider.

        Args:
            provider_name: Name of the provider to query, or None for active.

        Returns:
            List of model identifier strings.
        """
        name = provider_name or self._active_name
        provider = self._get_or_create(name)
        return await provider.list_models()

    # ------------------------------------------------------------------
    # Provider factory (lazy initialization)
    # ------------------------------------------------------------------

    def _get_or_create(self, name: str) -> BaseProvider:
        """Get an existing provider or create one from config on first use."""
        if name in self._providers:
            return self._providers[name]

        if name not in self._config.profiles:
            raise ValueError(f"No provider profile configured for '{name}'")

        profile = self._config.profiles[name]
        provider = self._create_provider(profile.provider, profile)
        self._providers[name] = provider

        # Apply any model override
        model_override = self._model_overrides.get(name)
        if model_override and hasattr(provider, "default_model"):
            provider.default_model = model_override

        log.debug(f"Initialized provider '{name}' (type={profile.provider})")
        return provider

    def _create_provider(self, provider_type: str, profile: Any) -> BaseProvider:
        """Factory method to create a provider from its type and config profile.

        Imports are deferred so that optional dependencies (openai, ollama)
        are only required when their provider is actually used.
        """
        if provider_type == ProviderType.ANTHROPIC or provider_type == "anthropic":
            from predator.providers.anthropic import AnthropicProvider

            return AnthropicProvider(
                api_key=profile.api_key,
                base_url=profile.base_url,
                default_model=profile.model or "claude-sonnet-4-20250514",
            )

        elif provider_type == ProviderType.OPENAI or provider_type == "openai":
            from predator.providers.openai import OpenAIProvider

            return OpenAIProvider(
                api_key=profile.api_key,
                base_url=profile.base_url,
                default_model=profile.model or "gpt-4o",
            )

        elif provider_type == ProviderType.OLLAMA or provider_type == "ollama":
            from predator.providers.ollama import OllamaProvider

            return OllamaProvider(
                base_url=profile.base_url or "http://localhost:11434",
                default_model=profile.model or "llama3",
            )

        elif provider_type == ProviderType.OPENROUTER or provider_type == "openrouter":
            from predator.providers.openrouter import OpenRouterProvider

            return OpenRouterProvider(
                api_key=profile.api_key,
                default_model=profile.model or "anthropic/claude-sonnet-4-20250514",
            )

        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    # ------------------------------------------------------------------
    # BaseProvider delegation (so ProviderRouter can be used as a provider)
    # ------------------------------------------------------------------

    async def complete(self, request: Any) -> Any:
        """Delegate to the active provider's complete method."""
        return await self.current.complete(request)

    async def stream(self, request: Any) -> Any:
        """Delegate to the active provider's stream method."""
        return await self.current.stream(request)

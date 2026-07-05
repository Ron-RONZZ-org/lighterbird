"""LLM provider abstraction — config, factory, and interface.

Providers are stateless and created on demand per AGENTS-core.md rules.
Provider state (which provider is active) is managed by the server layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider instance.

    Attributes:
        provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, or any
            OpenAI-compatible provider name.
        api_key: API key (retrieved from keyring at instantiation time).
        base_url: API base URL.
        model: Model name (e.g. ``"gpt-4o"``, ``"llama3"``).
        temperature: Sampling temperature (0.0 — 2.0).
        max_tokens: Maximum tokens in the response.
    """

    provider_type: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMProvider(Protocol):
    """Stateless provider interface for chat and command generation."""

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with ``role`` and ``content``.
            stream: If True, return an async iterator of tokens.

        Returns:
            Full response string (non-streaming) or async iterator (streaming).
        """
        ...

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Ask the LLM to generate a structured command from natural language.

        Args:
            message: User's natural language input.
            command_defs: List of available command definitions.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` or ``None``.
        """
        ...


def get_provider(config: ProviderConfig) -> LLMProvider:
    """Create a provider instance on demand (never cached).

    Args:
        config: Provider configuration.

    Returns:
        An :class:`LLMProvider` instance.
    """
    if config.provider_type == "ollama":
        from lighterbird.core.providers import OllamaProvider
        return OllamaProvider(config)
    # Everything else is treated as OpenAI-compatible (openai, deepseek,
    # groq, together, or any custom endpoint).
    from lighterbird.core.providers import OpenAICompatibleProvider
    return OpenAICompatibleProvider(config)


__all__ = [
    "LLMProvider",
    "ProviderConfig",
    "get_provider",
]

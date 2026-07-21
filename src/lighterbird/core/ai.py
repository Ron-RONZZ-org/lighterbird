"""LLM provider abstraction — config, factory, and interface.

Provider configuration now comes from ``lighterllm.llm.config``.
Providers are stateless and created on demand.
Provider state (which provider is active) is managed by the server layer.
"""

from __future__ import annotations

from lighterllm.llm import ProviderConfig
from lighterllm.llm.protocol import LLMProvider


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
    # Everything else is treated as OpenAI-compatible
    from lighterbird.core.providers import OpenAICompatibleProvider

    return OpenAICompatibleProvider(config)


__all__ = [
    "LLMProvider",
    "ProviderConfig",
    "get_provider",
]

"""Tests for lighterbird.core.ai — LLM provider factory.

Covers: get_provider for various provider types.
"""

from __future__ import annotations

from lighterbird.core.ai import ProviderConfig, get_provider


class TestGetProvider:
    def test_ollama_provider(self):
        config = ProviderConfig(
            provider_type="ollama",
            base_url="http://localhost:11434",
            model="llama3",
        )
        provider = get_provider(config)
        from lighterbird.core.providers import OllamaProvider
        assert isinstance(provider, OllamaProvider)

    def test_openai_provider(self):
        config = ProviderConfig(
            provider_type="openai",
            api_key="sk-test",
            base_url="https://api.openai.com",
            model="gpt-4o",
        )
        provider = get_provider(config)
        from lighterbird.core.providers import OpenAICompatibleProvider
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_deepseek_defaults_to_openai_compatible(self):
        config = ProviderConfig(
            provider_type="deepseek",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )
        provider = get_provider(config)
        from lighterbird.core.providers import OpenAICompatibleProvider
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_provider_config_defaults(self):
        config = ProviderConfig()
        assert config.provider_type == "openai"
        assert config.temperature == 0.7
        assert config.max_tokens == 2048

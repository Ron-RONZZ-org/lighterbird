"""Tests for core/providers.py — OpenAICompatibleProvider, OllamaProvider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from lightercore.exceptions import AIError
from lighterllm.llm import ProviderConfig

from lighterbird.core.providers import OllamaProvider, OpenAICompatibleProvider

# ── ProviderConfig helper ────────────────────────────────────────────────────


def _config(provider_type="openai", api_key="sk-test", **overrides):
    kwargs = dict(
        provider_type=provider_type,
        api_key=api_key,
        model="gpt-4o",
        temperature=0.7,
        max_tokens=1000,
        base_url="",
    )
    kwargs.update(overrides)
    return ProviderConfig(**kwargs)


# ── OpenAICompatibleProvider ──────────────────────────────────────────────────


class TestOpenAICompatibleProviderInit:
    def test_init_with_api_key(self):
        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.config.is_available() is True
        assert provider.model == "gpt-4o"

    def test_init_ollama_no_key(self):
        cfg = _config(provider_type="ollama", api_key="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.config.is_available() is True  # ollama doesn't need key

    def test_init_no_key_non_ollama(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.config.is_available() is False

    def test_init_empty_model_default(self):
        cfg = _config(model="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.model == "gpt-4o"

    def test_init_custom_model(self):
        cfg = _config(model="gpt-4o-mini")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.model == "gpt-4o-mini"


class TestOpenAICompatibleProviderChat:
    @pytest.mark.asyncio
    async def test_chat_not_configured(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        with pytest.raises(AIError, match="not configured"):
            await provider.chat([{"role": "user", "content": "Hi"}])

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_client):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from LLM"}}]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        result = await provider.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello from LLM"

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_api_error(self, mock_client):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = True
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limited"}}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        with pytest.raises(AIError, match="LLM API error"):
            await provider.chat([{"role": "user", "content": "Hi"}])

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_deepseek_normalizes_role_type(self, mock_client):
        """DeepSeek API needs both 'role' and 'type' fields."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(provider_type="deepseek", api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        await provider.chat([{"role": "user", "content": "Hi"}])
        call_kwargs = mock_instance.post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["messages"][0]["role"] == "user"
        assert payload["messages"][0]["type"] == "user"


class TestOpenAICompatibleProviderGenerateCommand:
    @pytest.mark.asyncio
    async def test_generate_not_configured(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        result = await provider.generate_command("show my inbox", [])
        assert result is None

    @patch.object(OpenAICompatibleProvider, "chat")
    @pytest.mark.asyncio
    async def test_generate_command_json(self, mock_chat):
        mock_chat.return_value = '{"tokens": ["email", "list"], "flags": {}}'
        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        result = await provider.generate_command("show my inbox", [])
        assert result == {"tokens": ["email", "list"], "flags": {}}

    @patch.object(OpenAICompatibleProvider, "chat")
    @pytest.mark.asyncio
    async def test_generate_command_with_flags(self, mock_chat):
        mock_chat.return_value = '{"tokens": ["todo", "add", "buy milk"], "flags": {"priority": "3"}}'
        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        result = await provider.generate_command("add a todo buy milk priority 3", [])
        assert result == {"tokens": ["todo", "add", "buy milk"], "flags": {"priority": "3"}}


# ── OllamaProvider ───────────────────────────────────────────────────────────


class TestOllamaProvider:
    def test_init(self):
        cfg = _config(provider_type="ollama", api_key="", model="llama3.2")
        provider = OllamaProvider(cfg)
        assert provider.config.is_available() is True
        assert provider.model == "llama3.2"
        assert "localhost" in provider.base_url

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_client):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = False
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from Ollama"}}]
        }

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        result = await provider.chat([{"role": "user", "content": "Hi"}])
        assert result == "Hello from Ollama"

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_api_error(self, mock_client):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.is_error = True
        mock_response.status_code = 503
        mock_response.json.return_value = {"error": {"message": "Ollama not available"}}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        with pytest.raises(AIError, match="LLM API error"):
            await provider.chat([{"role": "user", "content": "Hi"}])

    @patch.object(OllamaProvider, "chat")
    @pytest.mark.asyncio
    async def test_generate_command_delegates(self, mock_chat):
        mock_chat.return_value = '{"tokens": ["email", "list"], "flags": {}}'
        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        result = await provider.generate_command("show my inbox", [])
        assert result == {"tokens": ["email", "list"], "flags": {}}

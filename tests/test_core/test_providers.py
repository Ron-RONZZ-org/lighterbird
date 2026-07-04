"""Tests for core/providers.py — OpenAICompatibleProvider, OllamaProvider, helpers."""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lighterbird.core.ai import ProviderConfig
from lighterbird.core.providers import (
    OpenAICompatibleProvider,
    OllamaProvider,
    _resolve_base_url,
    _CMD_PATTERN,
    _response_error_detail,
)

# Async tests are marked individually with @pytest.mark.asyncio
# Do NOT set pytestmark globally as it interferes with other test modules


# ── Helper tests ─────────────────────────────────────────────────────────────


class TestResolveBaseUrl:
    def test_custom_url_used(self):
        assert _resolve_base_url("openai", "https://custom.example.com/v1") == "https://custom.example.com/v1"

    def test_custom_url_strips_trailing_slash(self):
        assert _resolve_base_url("openai", "https://custom.example.com/") == "https://custom.example.com"

    def test_openai_default(self):
        assert _resolve_base_url("openai", "") == "https://api.openai.com/v1"

    def test_deepseek_default(self):
        assert _resolve_base_url("deepseek", "") == "https://api.deepseek.com"

    def test_ollama_default(self):
        assert _resolve_base_url("ollama", "") == "http://localhost:11434/v1"

    def test_unknown_provider_default(self):
        assert _resolve_base_url("unknown", "") == "https://api.openai.com/v1"


class TestResponseErrorDetail:
    @patch("httpx.Response")
    @pytest.mark.asyncio
    async def test_error_detail_json(self, mock_response):
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        detail = await _response_error_detail(mock_response)
        assert detail == "Rate limit exceeded"

    @patch("httpx.Response")
    @pytest.mark.asyncio
    async def test_error_detail_no_error_key(self, mock_response):
        mock_response.json.return_value = {"detail": "Server error"}
        detail = await _response_error_detail(mock_response)
        assert "Server error" in detail

    @patch("httpx.Response")
    @pytest.mark.asyncio
    async def test_error_detail_invalid_json(self, mock_response):
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_response.text = "Internal Server Error"
        detail = await _response_error_detail(mock_response)
        assert detail == "Internal Server Error"

    @patch("httpx.Response")
    @pytest.mark.asyncio
    async def test_error_detail_empty_text(self, mock_response):
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_response.text = ""
        detail = await _response_error_detail(mock_response)
        assert detail == "(no detail)"


class TestCMDPattern:
    def test_matches_bang_command(self):
        m = _CMD_PATTERN.search("Use `!email list` to see emails")
        assert m is not None
        assert m.group(1) == "!email list"

    def test_matches_command_with_args(self):
        m = _CMD_PATTERN.search("Run `!todo add buy milk priority 3`")
        assert m is not None
        assert "!todo" in m.group(1)

    def test_no_match_without_backtick(self):
        m = _CMD_PATTERN.search("try !email list")
        assert m is None


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
        assert provider._available is True
        assert provider.model == "gpt-4o"

    def test_init_ollama_no_key(self):
        cfg = _config(provider_type="ollama", api_key="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider._available is True  # ollama doesn't need key

    def test_init_no_key_non_ollama(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider._available is False

    def test_init_empty_model_default(self):
        cfg = _config(model="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.model == "gpt-4o"

    def test_init_custom_model(self):
        cfg = _config(model="gpt-4o-mini")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.model == "gpt-4o-mini"


class TestOpenAICompatibleProviderIsAvailable:
    def test_available_with_key(self):
        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.is_available() is True

    def test_not_available_without_key(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        assert provider.is_available() is False


class TestOpenAICompatibleProviderChat:
    @pytest.mark.asyncio
    async def test_chat_not_configured(self):
        cfg = _config(api_key="")
        provider = OpenAICompatibleProvider(cfg)
        result = await provider.chat([{"role": "user", "content": "Hi"}])
        assert "not configured" in result

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_client):
        mock_response = MagicMock()
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
        mock_response = MagicMock()
        mock_response.is_error = True
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limited"}}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(api_key="sk-test")
        provider = OpenAICompatibleProvider(cfg)
        with pytest.raises(RuntimeError, match="LLM API error"):
            await provider.chat([{"role": "user", "content": "Hi"}])

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_deepseek_normalizes_role_type(self, mock_client):
        """DeepSeek API needs both 'role' and 'type' fields."""
        mock_response = MagicMock()
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
        # The payload should have both role and type
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


class TestOpenAICompatibleProviderParseCommandResult:
    def test_parse_bare_json(self):
        result = OpenAICompatibleProvider._parse_command_result(
            '{"tokens": ["email", "list"], "flags": {}}'
        )
        assert result == {"tokens": ["email", "list"], "flags": {}}

    def test_parse_json_in_code_fence(self):
        result = OpenAICompatibleProvider._parse_command_result(
            '```json\n{"tokens": ["email", "list"], "flags": {}}\n```'
        )
        assert result == {"tokens": ["email", "list"], "flags": {}}

    def test_parse_json_in_code_fence_no_lang(self):
        result = OpenAICompatibleProvider._parse_command_result(
            '```\n{"tokens": ["email", "list"], "flags": {}}\n```'
        )
        assert result == {"tokens": ["email", "list"], "flags": {}}

    def test_parse_null(self):
        result = OpenAICompatibleProvider._parse_command_result("null")
        assert result is None

    def test_parse_fallback_to_bang_command(self):
        result = OpenAICompatibleProvider._parse_command_result(
            'Try `!email list` to see your inbox.'
        )
        assert result == {"tokens": ["email", "list"], "flags": {}}

    def test_parse_no_match(self):
        result = OpenAICompatibleProvider._parse_command_result("I don't understand")
        assert result is None

    def test_parse_empty_string(self):
        result = OpenAICompatibleProvider._parse_command_result("")
        assert result is None

    def test_parse_json_missing_tokens_key(self):
        result = OpenAICompatibleProvider._parse_command_result(
            '{"response": "hello"}'
        )
        assert result is None


# ── OllamaProvider ───────────────────────────────────────────────────────────


class TestOllamaProvider:
    def test_init(self):
        cfg = _config(provider_type="ollama", api_key="", model="llama3.2")
        provider = OllamaProvider(cfg)
        assert provider._available is True
        assert provider.model == "llama3.2"
        assert "localhost" in provider.base_url

    def test_is_available(self):
        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        assert provider.is_available() is True

    @patch("httpx.AsyncClient")
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_client):
        mock_response = MagicMock()
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
        mock_response = MagicMock()
        mock_response.is_error = True
        mock_response.status_code = 503
        mock_response.json.return_value = {"error": {"message": "Ollama not available"}}

        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        with pytest.raises(RuntimeError, match="LLM API error"):
            await provider.chat([{"role": "user", "content": "Hi"}])

    @patch.object(OpenAICompatibleProvider, "generate_command")
    @pytest.mark.asyncio
    async def test_generate_command_delegates(self, mock_generate):
        mock_generate.return_value = {"tokens": ["email", "list"], "flags": {}}
        cfg = _config(provider_type="ollama", api_key="")
        provider = OllamaProvider(cfg)
        result = await provider.generate_command("show my inbox", [])
        assert result == {"tokens": ["email", "list"], "flags": {}}

"""LLM provider implementations — OpenAI-compatible API and Ollama.

Both providers support streaming chat and command generation.
Uses the ``openai`` library for the OpenAI-compatible provider
and raw ``httpx`` for Ollama (which speaks the same API format).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from lighterbird.core.ai import LLMProvider, ProviderConfig

logger = logging.getLogger(__name__)


# ── OpenAI-compatible provider ─────────────────────────────────────────────


class OpenAICompatibleProvider:
    """Provider for any OpenAI-compatible API (OpenAI, Groq, Together, etc.)."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._available = bool(config.api_key) or config.provider_type == "ollama"
        # Resolve base URL
        if not config.base_url:
            self.base_url = "https://api.openai.com/v1"
        else:
            self.base_url = config.base_url.rstrip("/") + "/v1"
        # Resolve model
        if not config.model:
            self.model = "gpt-4o"
        else:
            self.model = config.model

    def is_available(self) -> bool:
        return self._available

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat completion request.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            stream: If True, return an async iterator of content tokens.

        Returns:
            Full response string (non-streaming) or async iterator.
        """
        if not self._available:
            return "LLM provider not configured. Use ! commands for now."

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            if stream:
                return self._stream_chat(client, headers, payload)

            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            choice = data.get("choices", [{}])[0]
            return choice.get("message", {}).get("content", "")

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Ask the LLM to generate a structured command from natural language."""
        if not self._available:
            return None

        from lighterbird.core.system_prompt import load_system_prompt

        user_prompt = load_system_prompt()
        system_prompt = (
            "You are a command parser for the lighterbird PIM. "
            "Given a user's natural language request, generate a structured "
            "command from the available command definitions.\n\n"
            "Respond with ONLY a JSON object containing 'tokens' (list of command "
            "words) and 'flags' (dict of flag values). If you cannot generate a "
            "command, respond with null."
        )

        defs_text = json.dumps(command_defs, indent=2) if command_defs else "[]"

        messages = [
            {
                "role": "system",
                "content": (
                    f"{user_prompt}\n\n"
                    f"---\n"
                    f"Command parsing instructions:\n"
                    f"{system_prompt}\n\n"
                    f"Available commands:\n{defs_text}"
                ),
            },
            {"role": "user", "content": message},
        ]

        result = await self.chat(messages, stream=False)
        if isinstance(result, str):
            result = result.strip()
            try:
                parsed = json.loads(result)
                if parsed is None:
                    return None
                if isinstance(parsed, dict) and "tokens" in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible SSE endpoint."""
        async with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


# ── Ollama provider ────────────────────────────────────────────────────────


class OllamaProvider:
    """Provider for local Ollama instances.

    Ollama speaks the same API format as OpenAI, just at a different
    base URL (default: ``http://localhost:11434``).
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._available = True  # Ollama is always "available" — connection tested on first call
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/") + "/v1"
        self.model = config.model or "llama3.2"

    def is_available(self) -> bool:
        return self._available

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat completion request to Ollama."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            if stream:
                return self._stream_chat(client, payload)

            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            choice = data.get("choices", [{}])[0]
            return choice.get("message", {}).get("content", "")

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Delegate to the same logic as OpenAI-compatible."""
        oa = OpenAICompatibleProvider(self.config)
        oa.base_url = self.base_url
        oa.model = self.model
        return await oa.generate_command(message, command_defs)

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama's SSE endpoint."""
        async with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


__all__ = [
    "OpenAICompatibleProvider",
    "OllamaProvider",
]

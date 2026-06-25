"""LLM provider implementations — OpenAI-compatible API and Ollama.

Both providers support streaming chat and command generation.
Uses the ``openai`` library for the OpenAI-compatible provider
and raw ``httpx`` for Ollama (which speaks the same API format).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from lighterbird.core.ai import LLMProvider, ProviderConfig

logger = logging.getLogger(__name__)


# Pattern to extract !commands from LLM natural language responses
_CMD_PATTERN = re.compile(r"`(![a-z0-9_-]+(?:\s+[^\s`]+)*)`")


# ── Default base URLs ─────────────────────────────────────────────────────

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",  # no /v1 prefix
    "ollama": "http://localhost:11434/v1",
}


def _resolve_base_url(provider_type: str, base_url: str) -> str:
    """Resolve the effective base URL for a provider.

    If ``base_url`` is non-empty, it's used as-is.
    Otherwise the default for the given ``provider_type`` is returned.
    """
    if base_url:
        return base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(provider_type, "https://api.openai.com/v1")


async def _response_error_detail(response: httpx.Response) -> str:
    """Extract a human-readable error detail from an API error response."""
    try:
        body = response.json()
        # OpenAI-compatible format: {"error": {"message": "..."}}
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
        return str(body)
    except (json.JSONDecodeError, ValueError):
        return response.text or "(no detail)"


# ── OpenAI-compatible provider ─────────────────────────────────────────────


class OpenAICompatibleProvider:
    """Provider for any OpenAI-compatible API (OpenAI, Groq, Together, etc.)."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._available = bool(config.api_key) or config.provider_type == "ollama"
        # Resolve base URL — provider-type-aware defaults
        self.base_url = _resolve_base_url(config.provider_type, config.base_url)
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

        if stream:
            return self._stream_chat(headers, payload)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.is_error:
                detail = await _response_error_detail(response)
                raise RuntimeError(
                    f"LLM API error (HTTP {response.status_code}): {detail}"
                ) from None
            data = response.json()
            choice = data.get("choices", [{}])[0]
            return choice.get("message", {}).get("content", "")

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
    ) -> dict | None:
        """Ask the LLM to generate a structured command from natural language.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` if a command was identified,
            ``None`` if the LLM could not generate one.
        """
        if not self._available:
            return None

        defs_text = json.dumps(command_defs, indent=2) if command_defs else "[]"

        system_prompt = (
            "You are a command parser for the lighterbird PIM. Your job is to "
            "translate the user's natural language request into a structured command.\n\n"
            "Respond with ONLY a valid JSON object — no markdown, no explanation, no extra text.\n\n"
            "If the request maps to a command, use this format:\n"
            '{"tokens": ["command", "subcommand", ...], "flags": {"--flag": "value"}}\n\n'
            "Examples:\n"
            '- "show my inbox" → {"tokens": ["email", "list"], "flags": {}}\n'
            '- "add a contact John john@example.com" → {"tokens": ["contacts", "add", "john@example.com", "John"], "flags": {}}\n'
            '- "create a todo buy milk with priority 3" → {"tokens": ["todo", "add", "buy milk"], "flags": {"priority": "3"}}\n'
            '- "send an email to bob@test.com about the meeting" → {"tokens": ["email", "send", "bob@test.com", "about the meeting"], "flags": {}}\n\n'
            "If you CANNOT map the request to any command, respond with: null\n\n"
            "Available commands:\n" + defs_text
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        result = await self.chat(messages, stream=False)
        if isinstance(result, str):
            return self._parse_command_result(result.strip())
        return None

    @staticmethod
    def _parse_command_result(text: str) -> dict | None:
        """Try to parse an LLM response as a command JSON.

        Handles both bare JSON and JSON wrapped in ``` fences.
        Also extracts !commands from plain text as a fallback.
        """
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (possibly with language hint)
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        # Try JSON parse
        try:
            parsed = json.loads(cleaned)
            if parsed is None:
                return None
            if isinstance(parsed, dict) and "tokens" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: extract !command from plain text
        match = _CMD_PATTERN.search(cleaned)
        if match:
            cmd_text = match.group(1)
            parts = cmd_text[1:].split()  # remove leading !
            if parts:
                return {"tokens": parts, "flags": {}}

        return None

    async def _stream_chat(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from an OpenAI-compatible SSE endpoint.

        Manages its own httpx client lifecycle — the client stays open
        as long as the iterator is alive, and is closed when iteration
        completes or is cancelled.
        """
        client = httpx.AsyncClient(timeout=60.0)
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.is_error:
                    detail = await _response_error_detail(response)
                    raise RuntimeError(
                        f"LLM API error (HTTP {response.status_code}): {detail}"
                    ) from None
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
        finally:
            await client.aclose()


# ── Ollama provider ────────────────────────────────────────────────────────


class OllamaProvider:
    """Provider for local Ollama instances.

    Ollama speaks the same API format as OpenAI, just at a different
    base URL (default: ``http://localhost:11434``).
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._available = True  # Ollama is always "available" — connection tested on first call
        self.base_url = _resolve_base_url(config.provider_type, config.base_url)
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

        if stream:
            return self._stream_chat(payload)

        async with httpx.AsyncClient(timeout=120.0) as client:
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
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama's SSE endpoint.

        Manages its own httpx client lifecycle.
        """
        client = httpx.AsyncClient(timeout=120.0)
        try:
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
        finally:
            await client.aclose()


__all__ = [
    "OpenAICompatibleProvider",
    "OllamaProvider",
]

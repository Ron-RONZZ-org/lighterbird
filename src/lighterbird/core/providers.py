"""LLM provider implementations — OpenAI-compatible API and Ollama.

Both providers now extend :class:`lightercore.llm.BaseLLMProvider` and
share the unified chat / command-generation infrastructure.  Only the
domain-specific system prompt and default model differ.
"""

from __future__ import annotations

from typing import Any

from lightercore.llm import BaseLLMProvider, ProviderConfig

# ── Shared prompts for lighterbird ──────────────────────────────────────


def _lighterbird_tool_prompt() -> str:
    """Return the PIM-specific system prompt for the tool-calling path.

    This is the **preferred** path used when command definitions are
    available.  The LLM receives tool definitions separately via the
    native function-calling API; this prompt provides context.
    """
    return (
        "You are a command parser for the lighterbird PIM. "
        "Translate the user's request into a command by "
        "calling the appropriate tool. The tools available "
        "correspond to PIM commands: email, contacts, calendar, "
        "todo, journal, letters, and user profiles. "
        "ALWAYS pick a tool when the user asks about their data "
        "(list, search, show, etc.) — never refuse or say you "
        "cannot do it."
    )


def _lighterbird_command_prompt(defs_text: str) -> str:
    """Return the PIM-specific system prompt for the JSON-in-prompt fallback.

    This is only used when no tool definitions are available.
    """
    return (
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


# ── Provider classes ─────────────────────────────────────────────────────


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for any OpenAI-compatible API (OpenAI, Grok, Together, etc.)."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        if not config.model:
            self.model = "gpt-4o"

    def _default_model(self) -> str:
        return "gpt-4o"

    def _command_system_prompt(self, defs_text: str) -> str:
        """JSON-in-prompt fallback — used when no tool defs available."""
        return _lighterbird_command_prompt(defs_text)

    def _command_tool_system_prompt(self) -> str:
        """Native tool-calling path (preferred)."""
        return _lighterbird_tool_prompt()


class OllamaProvider(BaseLLMProvider):
    """Provider for local Ollama instances.

    Chat uses the same API format as OpenAI (at ``/v1/chat/completions``).
    Embedding uses the native Ollama ``/api/embed`` endpoint because
    Ollama's ``/v1/embeddings`` may not be available in older versions.
    """

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        if not config.model:
            self.model = "llama3.2"

    def _default_model(self) -> str:
        return "llama3.2"

    def _command_system_prompt(self, defs_text: str) -> str:
        """JSON-in-prompt fallback — used when no tool defs available."""
        return _lighterbird_command_prompt(defs_text)

    def _command_tool_system_prompt(self) -> str:
        """Native tool-calling path (preferred)."""
        return _lighterbird_tool_prompt()

    # ── Embedding (Ollama-native /api/embed endpoint) ────────────────────

    def _embed_url(self) -> str:
        return f"{self.base_url}/api/embed"

    def _build_embed_payload(self, texts: list[str]) -> dict[str, Any]:
        return {
            "model": self.config.model or "nomic-embed-text",
            "input": texts,
        }

    def _parse_embed_response(self, data: dict[str, Any]) -> list[list[float]]:
        return data.get("embeddings", [])


__all__ = [
    "OllamaProvider",
    "OpenAICompatibleProvider",
]

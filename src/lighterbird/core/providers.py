"""LLM provider implementations — OpenAI-compatible API and Ollama.

Both providers now extend :class:`lightercore.llm.BaseLLMProvider` and
share the unified chat / command-generation infrastructure.  Only the
domain-specific system prompt and default model differ.
"""

from __future__ import annotations

from lightercore.llm import BaseLLMProvider, ProviderConfig

# ── Shared command-generation prompt for lighterbird ─────────────────────


def _lighterbird_command_prompt(defs_text: str) -> str:
    """Return the PIM-specific system prompt for command generation."""
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
        return _lighterbird_command_prompt(defs_text)


class OllamaProvider(BaseLLMProvider):
    """Provider for local Ollama instances.

    Ollama speaks the same API format as OpenAI, just at a different
    base URL (default: ``http://localhost:11434``).
    """

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        if not config.model:
            self.model = "llama3.2"

    def _default_model(self) -> str:
        return "llama3.2"

    def _command_system_prompt(self, defs_text: str) -> str:
        return _lighterbird_command_prompt(defs_text)


__all__ = [
    "OllamaProvider",
    "OpenAICompatibleProvider",
]

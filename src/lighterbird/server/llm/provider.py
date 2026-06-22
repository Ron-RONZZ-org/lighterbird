"""LLM provider abstraction — OpenAI-compatible + Ollama.

Provides a simple interface for:
- Natural language chat
- Command generation via tool calling (future)

Currently a stub returning placeholder responses.
"""

from __future__ import annotations

from typing import Any


class LLMProvider:
    """Abstract LLM provider. Stub for now."""

    def __init__(self) -> None:
        self._available = False

    def is_available(self) -> bool:
        return self._available

    async def chat(self, message: str, context: list[dict] | None = None) -> str:
        """Send a message to the LLM and return a text response."""
        return "LLM mode coming in v0.2. Use ! commands for now."

    async def generate_command(
        self, message: str, command_defs: list[dict], context: list[dict] | None = None
    ) -> dict[str, Any] | None:
        """Ask the LLM to generate a structured command from natural language.

        Returns ``{tokens: [...], flags: {...}}`` or ``None`` if no command
        could be generated.
        """
        return None


# Singleton
_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider

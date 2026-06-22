"""Command handlers for the ``!llm`` domain.

Registered paths:
    - llm.configure
    - llm.config
    - llm.reset
    - llm.prompt
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.llm.provider import get_provider


@command("llm.configure")
def llm_configure(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm configure <provider> [--api-key KEY] [--base-url URL] [--model MODEL]"""
    if not remaining:
        raise CommandValidationError(
            "Missing provider type.",
            "Usage: !llm configure openai|ollama [--api-key KEY] [--base-url URL] [--model MODEL]",
        )
    provider_type = remaining[0]
    provider = get_provider()
    provider.configure(
        provider_type=provider_type,
        api_key=flags.get("api_key", ""),
        base_url=flags.get("base_url", ""),
        model=flags.get("model", ""),
        temperature=float(flags.get("temperature", 0.7)),
        max_tokens=int(flags.get("max_tokens", 2048)),
    )
    return {
        "type": "status",
        "title": "LLM Configured",
        "data": {
            "provider": provider_type,
            "available": provider.is_available(),
        },
    }


@command("llm.config")
def llm_config(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm config — Show current LLM configuration."""
    provider = get_provider()
    cfg = provider.config
    return {
        "type": "status",
        "title": "LLM Config",
        "data": {
            "provider_type": cfg.provider_type,
            "api_key_set": bool(cfg.api_key),
            "base_url": cfg.base_url,
            "model": cfg.model,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "available": provider.is_available(),
        },
    }


@command("llm.reset")
def llm_reset(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm reset — Clear LLM provider configuration."""
    provider = get_provider()
    provider.clear_config()
    return {"type": "status", "title": "LLM Reset", "data": {"status": "cleared"}}


@command("llm.prompt")
def llm_prompt(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm prompt — Show current system prompt path."""
    from lighterbird.core.system_prompt import system_prompt_path, load_system_prompt

    path = system_prompt_path()
    content = load_system_prompt()
    return {
        "type": "status",
        "title": "System Prompt",
        "data": {
            "path": str(path),
            "length": len(content),
            "preview": content[:300] + ("..." if len(content) > 300 else ""),
        },
    }

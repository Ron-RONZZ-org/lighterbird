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


# ── Profile management ──────────────────────────────────────────────────────


@command("llm.profile.list")
def llm_profile_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile list — List saved LLM profiles."""
    provider = get_provider()
    profiles = provider.list_profiles()
    return {
        "type": "status",
        "title": "LLM Profiles",
        "data": {"profiles": profiles} if profiles else {"message": "No saved profiles."},
    }


@command("llm.profile.add")
def llm_profile_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile add <name> [--provider TYPE] [--api-key KEY] [--base-url URL] [--model MODEL]

    Save a named LLM provider profile.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !llm profile add my-profile --provider openai --api-key sk-...",
        )
    name = remaining[0]
    provider_type = flags.get("provider", "openai")
    provider = get_provider()
    provider.save_profile(
        name=name,
        provider_type=provider_type,
        api_key=flags.get("api_key", ""),
        base_url=flags.get("base_url", ""),
        model=flags.get("model", ""),
        temperature=float(flags.get("temperature", 0.7)),
        max_tokens=int(flags.get("max_tokens", 2048)),
    )
    return {
        "type": "status",
        "title": "Profile Saved",
        "data": {"name": name, "provider": provider_type},
    }


@command("llm.profile.remove")
def llm_profile_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile remove <name> — Delete a saved profile."""
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !llm profile remove my-profile",
        )
    name = remaining[0]
    provider = get_provider()
    if provider.delete_profile(name):
        return {"type": "status", "title": "Profile Removed", "data": {"removed": [name]}}
    raise CommandValidationError(f"Profile not found: {name}")


@command("llm.profile.switch")
def llm_profile_switch(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile switch <name> — Activate a saved profile."""
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !llm profile switch my-profile",
        )
    name = remaining[0]
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise CommandValidationError(f"Profile not found: {name}")
    return {
        "type": "status",
        "title": "Profile Activated",
        "data": {
            "name": name,
            "provider": config.provider_type,
            "model": config.model,
            "available": provider.is_available(),
        },
    }

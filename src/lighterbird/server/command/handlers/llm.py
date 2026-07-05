"""Command handlers for the ``!llm`` domain.

Registered paths:
    - llm
    - llm.prompt
    - llm.profile
    - llm.profile.show
    - llm.profile.new
    - llm.profile.set
    - llm.profile.clear
    - llm.profile.load
    - llm.profile.list
    - llm.profile.delete
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.llm.provider import get_provider


@command("llm")
def llm_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm — Show LLM subcommands or quick-switch to a profile by name."""
    if remaining:
        # Delegate: !llm <profile-name> → switch to that profile
        name = remaining[0]
        provider = get_provider()
        config = provider.switch_to_profile(name)
        if config is not None:
            return {
                "type": "status",
                "title": "Profile Activated",
                "data": {"name": name, "protocol": config.provider_type, "model": config.model},
            }
        raise CommandValidationError(f"Profile not found: {name}")
    # Show available subcommands
    return {
        "type": "status",
        "title": "LLM Commands",
        "data": {
            "_summary": (
                "Available !llm commands:\n"
                "  !llm prompt                    — Show system prompt\n"
                "  !llm profile                   — Show profile subcommands\n"
                "  !llm profile show              — Show current config\n"
                "  !llm profile new <protocol>    — Create config (openai, deepseek, ollama, custom)\n"
                "  !llm profile set [flags]       — Modify current settings\n"
                "  !llm profile clear             — Clear config\n"
                "  !llm profile load <name>       — Load a saved profile\n"
                "  !llm profile list              — List saved profiles\n"
                "  !llm profile delete <name>     — Delete a saved profile\n"
                "  !llm <profile-name>            — Quick switch to a profile"
            ),
        },
    }


@command("llm.prompt")
def llm_prompt(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm prompt — Show current system prompt path."""
    from lighterbird.core.system_prompt import load_system_prompt, system_prompt_path

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


@command("llm.profile")
def llm_profile_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile — List profiles (default) or switch by name."""
    if remaining:
        # !llm profile <name> → quick switch
        name = remaining[0]
        provider = get_provider()
        config = provider.switch_to_profile(name)
        if config is not None:
            return {
                "type": "status",
                "title": "Profile Activated",
                "data": {"name": name, "protocol": config.provider_type, "model": config.model},
            }
        raise CommandValidationError(f"Profile not found: {name}")
    # List profiles
    provider = get_provider()
    profiles = provider.list_profiles()
    active = provider.config
    result = {
        "_summary": "Available subcommands:\n"
        "  show               — Show current config\n"
        "  new <protocol>     — Create config (openai, deepseek, ollama, custom)\n"
        "  set [flags]        — Modify current settings\n"
        "  clear              — Clear config\n"
        "  load <name>        — Load a saved profile\n"
        "  list               — List saved profiles\n"
        "  delete <name>      — Delete a saved profile",
    }
    result["profiles"] = profiles
    result["active_profile"] = provider.active_profile_name
    if active.provider_type:
        result["active"] = {
            "protocol": active.provider_type,
            "model": active.model,
            "base_url": active.base_url,
        }
    return {"type": "status", "title": "LLM Profile", "data": result}


@command("llm.profile.show")
def llm_profile_show(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile show — Show current LLM configuration."""
    return {
        "type": "status",
        "title": "LLM Config",
        "data": {"_summary": "done"},
    }


@command("llm.profile.new")
def llm_profile_new(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile new <protocol> [--alias NAME] [--api-key KEY] [--base-url URL] [--model MODEL] [--temperature TEMP] [--max-tokens N]

    Create a new LLM provider configuration from scratch.
    Use --alias to simultaneously save as a named profile.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing protocol.",
            "Usage: !llm profile new openai|deepseek|ollama|custom [--alias my-profile] [--api-key KEY] [--base-url URL] [--model MODEL]",
        )
    protocol = remaining[0]
    provider = get_provider()
    provider.configure(
        provider_type=protocol,
        api_key=flags.get("api_key", ""),
        base_url=flags.get("base_url", ""),
        model=flags.get("model", ""),
        temperature=float(flags.get("temperature", 0.7)),
        max_tokens=int(flags.get("max_tokens", 2048)),
    )

    result: dict[str, Any] = {
        "protocol": protocol,
        "available": provider.is_available(),
    }

    # If --alias provided, also save as named profile
    if "alias" in flags:
        name = flags["alias"]
        cfg = provider.config
        provider.save_profile(
            name=name,
            provider_type=cfg.provider_type,
            api_key=cfg.api_key or "",
            base_url=cfg.base_url or "",
            model=cfg.model or "",
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        result["saved_as"] = name

    return {
        "type": "status",
        "title": "Profile Created",
        "data": result,
    }


@command("llm.profile.set")
def llm_profile_set(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile set [--protocol TYPE] [--alias NAME] [--api-key KEY] [--base-url URL] [--model MODEL] [--temperature TEMP] [--max-tokens N]

    Modify current LLM profile settings. Only provided flags are changed.
    Use --alias to save the current config as a named profile.
    """
    if not flags:
        raise CommandValidationError(
            "No settings provided.",
            "Usage: !llm profile set --model gpt-4 --api-key sk-...",
        )
    provider = get_provider()
    cfg = provider.config

    if not cfg.provider_type and "protocol" not in flags:
        raise CommandValidationError(
            "No active profile. Use !llm profile new <protocol> first, or include --protocol.",
            "Usage: !llm profile set --protocol openai --model gpt-4",
        )

    provider.configure(
        provider_type=flags.get("protocol", cfg.provider_type or "openai"),
        api_key=flags.get("api_key", cfg.api_key or ""),
        base_url=flags.get("base_url", cfg.base_url or ""),
        model=flags.get("model", cfg.model or ""),
        temperature=float(flags.get("temperature", cfg.temperature or 0.7)),
        max_tokens=int(flags.get("max_tokens", cfg.max_tokens or 2048)),
    )

    result: dict[str, Any] = {"_summary": "done"}

    # If --alias provided, also save as named profile
    if "alias" in flags:
        name = flags["alias"]
        cfg = provider.config
        provider.save_profile(
            name=name,
            provider_type=cfg.provider_type,
            api_key=cfg.api_key or "",
            base_url=cfg.base_url or "",
            model=cfg.model or "",
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        result["saved_as"] = name

    return {
        "type": "status",
        "title": "Profile Updated",
        "data": result,
    }


@command("llm.profile.clear")
def llm_profile_clear(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile clear — Clear LLM provider configuration."""
    provider = get_provider()
    provider.clear_config()
    return {"type": "status", "title": "Profile Cleared", "data": {"_summary": "done"}}


@command("llm.profile.list")
def llm_profile_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile list — List saved LLM profiles."""
    provider = get_provider()
    profiles = provider.list_profiles()
    active_name = provider.active_profile_name
    return {
        "type": "status",
        "title": "LLM Profiles",
        "data": {"profiles": profiles, "active_profile": active_name},
    }


@command("llm.profile.load")
def llm_profile_load(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile load <name> — Activate a saved profile."""
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !llm profile load my-profile",
        )
    name = remaining[0]
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise CommandValidationError(f"Profile not found: {name}")
    return {
        "type": "status",
        "title": "Profile Loaded",
        "data": {
            "name": name,
            "protocol": config.provider_type,
            "model": config.model,
            "available": provider.is_available(),
        },
    }


@command("llm.profile.delete")
def llm_profile_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!llm profile delete <name> — Delete a saved profile."""
    if not remaining:
        raise CommandValidationError(
            "Missing profile name.",
            "Usage: !llm profile delete my-profile",
        )
    name = remaining[0]
    provider = get_provider()
    if provider.delete_profile(name):
        return {"type": "status", "title": "Profile Deleted", "data": {"removed": [name]}}
    raise CommandValidationError(f"Profile not found: {name}")

"""LLM configuration REST API routes.

``GET /api/v1/llm/config`` — Get current active provider config.
``POST /api/v1/llm/configure`` — Set active provider config.
``POST /api/v1/llm/reset`` — Clear active provider config.
``POST /api/v1/llm/reload-prompt`` — Reload system prompt from disk.
``GET /api/v1/llm/prompt`` — Get current system prompt.
``GET /api/v1/llm/profiles`` — List saved named profiles.
``POST /api/v1/llm/profiles`` — Create/save a named profile.
``GET /api/v1/llm/profiles/{name}`` — Get a single profile.
``PATCH /api/v1/llm/profiles/{name}`` — Update a named profile.
``DELETE /api/v1/llm/profiles/{name}`` — Delete a named profile.
``POST /api/v1/llm/profiles/{name}/load`` — Activate a saved profile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from lighterbird.core.system_prompt import load_system_prompt, system_prompt_path
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.schemas import (
    LLMProfileCreate,
    LLMProfileUpdate,
)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


def _profile_to_response(name: str, data: dict) -> dict:
    """Convert a raw profile dict to a safe response (no API key)."""
    return {
        "name": name,
        "provider_type": data.get("provider_type", ""),
        "base_url": data.get("base_url", ""),
        "model": data.get("model", ""),
        "has_api_key": bool(data.get("api_key", "")),
    }


# ── Active config ────────────────────────────────────────────────────────


@router.get("/config")
async def llm_config() -> dict[str, Any]:
    """Get the current LLM provider configuration (redacted)."""
    provider = get_provider()
    cfg = provider.config
    return {
        "provider_type": cfg.provider_type,
        "api_key": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "available": provider.is_available(),
    }


@router.post("/configure")
async def llm_configure(data: dict[str, Any]) -> dict[str, Any]:
    """Configure the LLM provider.

    Accepts: ``provider_type``, ``api_key``, ``base_url``, ``model``,
    ``temperature``, ``max_tokens``.
    """
    provider = get_provider()
    provider_type = data.get("provider_type", "openai")
    provider.configure(
        provider_type=provider_type,
        api_key=data.get("api_key", ""),
        base_url=data.get("base_url", ""),
        model=data.get("model", ""),
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 2048),
    )
    return {
        "status": "ok",
        "provider": provider_type,
        "available": provider.is_available(),
    }


@router.post("/reset")
async def llm_reset() -> dict[str, Any]:
    """Clear the LLM provider configuration."""
    provider = get_provider()
    provider.clear_config()
    return {"status": "ok"}


@router.post("/reload-prompt")
async def llm_reload_prompt() -> dict[str, Any]:
    """Reload the system prompt from disk."""
    provider = get_provider()
    content = provider.reload_prompt()
    return {"status": "ok", "prompt_length": len(content)}


@router.get("/prompt")
async def llm_get_prompt() -> dict[str, Any]:
    """Get the current system prompt content."""
    return {
        "prompt": load_system_prompt(),
        "path": str(system_prompt_path()),
    }


# ── Named profile CRUD ────────────────────────────────────────────────────


@router.get("/profiles")
async def list_profiles() -> dict[str, Any]:
    """List all saved LLM profiles (without API keys)."""
    provider = get_provider()
    profiles = provider.list_profiles()
    return {"profiles": profiles}


@router.post("/profiles", status_code=201)
async def create_profile(data: LLMProfileCreate) -> dict[str, Any]:
    """Create/save a named LLM profile."""
    provider = get_provider()
    saved = provider.save_profile(
        name=data.name,
        provider_type=data.provider_type,
        api_key=data.api_key,
        base_url=data.base_url,
        model=data.model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
    )
    return _profile_to_response(data.name, saved)


@router.get("/profiles/{name}")
async def get_profile(name: str) -> dict[str, Any]:
    """Get a single saved profile."""
    provider = get_provider()
    profile = provider.get_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")
    return _profile_to_response(name, profile)


@router.patch("/profiles/{name}")
async def update_profile(name: str, data: LLMProfileUpdate) -> dict[str, Any]:
    """Update a saved profile (partial)."""
    provider = get_provider()
    updates = {k: v for k, v in data.model_dump(exclude_none=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    result = provider.modify_profile(name, **updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")
    return result


@router.delete("/profiles/{name}")
async def delete_profile(name: str) -> dict[str, str]:
    """Delete a saved profile."""
    provider = get_provider()
    if provider.delete_profile(name):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail=f"Profile not found: {name}")


@router.post("/profiles/{name}/load")
async def load_profile(name: str) -> dict[str, Any]:
    """Activate a saved profile as the current provider config."""
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")
    return {
        "name": name,
        "provider_type": config.provider_type,
        "model": config.model,
        "available": provider.is_available(),
    }

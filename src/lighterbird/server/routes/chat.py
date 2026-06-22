"""Chat API route — natural language interface with SSE streaming.

``POST /api/v1/chat`` — Standard response (single message).
``POST /api/v1/chat/stream`` — SSE streaming response for LLM output.
``POST /api/v1/llm/configure`` — Configure the LLM provider.
``GET /api/v1/llm/config`` — Get current LLM provider config.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lighterbird.server.command.models import CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.llm.provider import get_provider

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=CommandResponse)
async def chat_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Accept a natural language message.

    Flow:
    1. Ask the LLM to parse the user's intent into a structured command.
    2. If a command is generated → execute it, send the result to the
       LLM for a natural-language summary, and return that summary.
    3. If the LLM can't generate a command, just return its response.
    """
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM not configured. Use ! commands or configure a provider."},
        }

    # ── Phase 1: Try to parse into a command ────────────────────────────
    defs = get_definitions()
    cmd = await provider.generate_command(message, defs)

    if cmd and cmd.get("tokens"):
        # Execute the command
        try:
            raw_result = dispatch(cmd["tokens"], cmd.get("flags", {}))
        except Exception as exc:
            return {
                "type": "status",
                "title": "LLM Chat",
                "data": {
                    "message": f"I understood your request but couldn't execute it: {exc}",
                    "original": message,
                },
            }

        # ── Phase 2: Summarize the result with the LLM ─────────────────
        import json as _json

        result_summary = _json.dumps(raw_result.get("data", raw_result), indent=2, default=str)
        summary = await provider.chat(
            message=(
                f"I executed this command based on your request '{message}':\n"
                f"Command: !{' '.join(cmd['tokens'])}\n"
                f"Result:\n{result_summary}\n\n"
                f"Please summarize the result for the user in a helpful, "
                f"friendly way. Be concise but include all relevant details. "
                f"Use natural language, not JSON."
            ),
        )
        if isinstance(summary, str) and summary.strip():
            return {
                "type": "status",
                "title": "LLM Chat",
                "data": {"message": summary.strip()},
            }
        # Fallback: return raw result if LLM summarization fails
        return raw_result

    # ── Phase 3: No command — respond as plain chat ───────────────────
    response = await provider.chat(message)
    if isinstance(response, str):
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": response},
        }
    return {
        "type": "status",
        "title": "LLM Chat",
        "data": {"message": "LLM response unavailable."},
    }


@router.post("/chat/stream")
async def chat_stream(data: dict[str, Any]) -> StreamingResponse:
    """SSE streaming endpoint for LLM chat.

    Returns a ``text/event-stream`` response with tokens sent as
    ``data: {"token": "..."}`` events, terminated by ``data: [DONE]``.
    """
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()

    async def event_stream():
        if not provider.is_available():
            yield f"data: {json.dumps({'token': 'LLM not configured. Use ! commands or configure a provider.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            result = await provider.chat(message, stream=True)
            if hasattr(result, "__aiter__"):
                async for token in result:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                yield f"data: {json.dumps({'token': str(result)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'Error: {exc}'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── LLM configuration ──────────────────────────────────────────────────────


@router.post("/llm/configure")
async def llm_configure(data: dict[str, Any]) -> dict[str, Any]:
    """Configure the LLM provider.

    Accepts: ``provider_type``, ``api_key``, ``base_url``, ``model``,
    ``temperature``, ``max_tokens``.

    The configuration is persisted in the system keyring.
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


@router.get("/llm/config")
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


@router.post("/llm/reset")
async def llm_reset() -> dict[str, Any]:
    """Clear the LLM provider configuration."""
    provider = get_provider()
    provider.clear_config()
    return {"status": "ok"}


@router.post("/llm/reload-prompt")
async def llm_reload_prompt() -> dict[str, Any]:
    """Reload the system prompt from disk."""
    provider = get_provider()
    content = provider.reload_prompt()
    return {"status": "ok", "prompt_length": len(content)}


@router.get("/llm/prompt")
async def llm_get_prompt() -> dict[str, Any]:
    """Get the current system prompt content."""
    from lighterbird.core.system_prompt import load_system_prompt, system_prompt_path

    return {
        "prompt": load_system_prompt(),
        "path": str(system_prompt_path()),
    }

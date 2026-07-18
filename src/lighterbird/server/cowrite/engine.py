"""Co-writing engine — app-specific orchestration around the lightercore engine.

The core co-writing logic (protocol prompt, diff computation, response
parsing) now lives in ``lightercore.cowrite.engine``.  This module
handles lighterbird-specific wiring: provider creation, context gathering,
and style loading.

See :mod:`lightercore.cowrite.engine` for the shared implementation.
"""

from __future__ import annotations

import logging
from typing import Any

from lighterbird.core.ai import get_provider as _get_core_provider
from lighterbird.core.cowrite_style import load_cowrite_style
from lighterbird.server.cowrite.context import gather_context
from lighterbird.server.llm.provider import get_provider

logger = logging.getLogger(__name__)


async def cowrite(
    form_type: str,
    fields: dict[str, str],
    instruction: str,
    *,
    context_mode: str = "auto",
) -> dict[str, Any]:
    """Run the co-writing flow: gather context, load style, delegate to lightercore.

    Args:
        form_type: Type of form (``"email-send"``, ``"todo-add"``, etc.).
        fields: Current content ``{field_name: text}``.
        instruction: User's instruction for the LLM.
        context_mode: ``"auto"`` (normal) or ``"none"`` (skip context).

    Returns:
        Dict with ``edits``, ``revised``, ``original``, ``session_id``.
        May also return ``_embed_required`` if embedding setup is needed.

    Raises:
        RuntimeError: If LLM is not configured or call fails.
        ValueError: If LLM response is invalid.
    """
    provider = get_provider()
    if not provider.is_available():
        raise RuntimeError("LLM not configured. Use ``!llm profile`` to set up a provider.")

    # Gather context
    context = gather_context(form_type, fields) if context_mode == "auto" else {}

    # If embedding is unavailable and no samples exist, tell the frontend
    if context.get("_embed_required"):
        return {
            "_embed_required": True,
            "models": context.get("models", []),
        }

    # Load style (general + per-domain cascade)
    style_content = load_cowrite_style(form_type)

    # Get core provider (bypasses wrapper's system prompt)
    core = _get_core_provider(provider.config)

    # Delegate to lightercore
    from lightercore.cowrite.engine import cowrite as core_cowrite

    return await core_cowrite(
        form_type=form_type,
        fields=fields,
        instruction=instruction,
        chat_fn=core.chat,
        style_content=style_content,
        context=context if context else None,
    )

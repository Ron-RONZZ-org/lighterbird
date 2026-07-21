"""Lighterbird LLM tools — dedicated AI-optimised tool handlers.

Tools call domain services directly (no CLI pipeline) and use the
shared infrastructure from :mod:`lighterllm.llm.tools`.

The core decorator, registry, and dispatch live in lightercore.
This module re-exports them for internal consistency.  Domain-specific
tool modules (``email``, ``contacts``, ``calendar``, etc.) are imported
by :mod:`lighterbird.server.routes.chat` at startup, which triggers
``@llm_tool`` registration.

Usage::

    from lighterbird.server.llm.tools import llm_tool, get_llm_tools

    @llm_tool(
        name="email.find",
        description="Search emails by content, sender, or date range",
        params=[{"name": "query", "type": "string", "description": "Free-text query"}],
        permission_level=PermissionLevel.READ,
    )
    def llm_email_find(query: str = "") -> dict:
        ...
"""

from lighterllm.llm.tools import (  # noqa: F401
    _llm_registry,
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tool_names,
    get_llm_tools,
    is_llm_tool,
    llm_tool,
)

__all__ = [
    "_llm_registry",
    "dispatch_llm_tool",
    "get_llm_tool_level",
    "get_llm_tool_metadata",
    "get_llm_tool_names",
    "get_llm_tools",
    "is_llm_tool",
    "llm_tool",
]

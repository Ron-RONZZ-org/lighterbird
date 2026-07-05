"""LLM co-writing engine — protocol, diff, session management."""

from lighterbird.server.cowrite.context import gather_context
from lighterbird.server.cowrite.engine import (
    COWRITE_PROTOCOL_PROMPT,
    CowriteSession,
    compute_diffs,
    cowrite,
)

__all__ = [
    "COWRITE_PROTOCOL_PROMPT",
    "CowriteSession",
    "compute_diffs",
    "cowrite",
    "gather_context",
]

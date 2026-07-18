"""LLM co-writing engine — app orchestration around lightercore.

Re-exports the core types from ``lightercore.cowrite.engine`` for
backward compatibility.  The actual engine logic lives in lightercore.
"""

from lighterbird.server.cowrite.context import gather_context
from lighterbird.server.cowrite.engine import cowrite
from lightercore.cowrite.engine import COWRITE_PROTOCOL_PROMPT, compute_diffs

# CowriteSession was removed in the refactor — the lightercore engine
# returns plain dicts.  Keep the name for backward compat if needed.
CowriteSession = None  # noqa: F821 — placeholder for API compat

__all__ = [
    "COWRITE_PROTOCOL_PROMPT",
    "compute_diffs",
    "cowrite",
    "gather_context",
]

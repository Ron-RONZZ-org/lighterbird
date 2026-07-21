"""LLM co-writing engine — app orchestration around lighterllm.

Re-exports the core types from ``lighterllm.cowrite.engine`` and
``lightercore.text_utils`` for backward compatibility.
"""

from lighterbird.server.cowrite.context import gather_context
from lighterbird.server.cowrite.engine import cowrite
from lightercore.text_utils import compute_diffs
from lighterllm.cowrite.engine import COWRITE_PROTOCOL_PROMPT

# CowriteSession was removed in the refactor — the lighterllm engine
# returns plain dicts.  Keep the name for backward compat if needed.
CowriteSession = None  # noqa: F821 — placeholder for API compat

__all__ = [
    "COWRITE_PROTOCOL_PROMPT",
    "compute_diffs",
    "cowrite",
    "gather_context",
]

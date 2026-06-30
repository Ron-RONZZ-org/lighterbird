"""Context gatherers for LLM co-writing.

Each ``form_type`` can have a gatherer that fetches relevant user data
to provide helpful context. For v1 these are lightweight stubs —
enhancement planned for richer context (recent emails, related todos).
"""

from __future__ import annotations

from typing import Any


def gather_context(form_type: str, fields: dict[str, str]) -> dict[str, Any]:
    """Gather relevant context data for the given form type.

    Args:
        form_type: Type of form (``"email-send"``, ``"todo-add"``, etc.).
        fields: Current form field values.

    Returns:
        Dict of context data (serializable). Empty dict for v1;
        will be enhanced with real data fetchers in later iterations.
    """
    _ = form_type, fields  # reserved for future use
    return {}

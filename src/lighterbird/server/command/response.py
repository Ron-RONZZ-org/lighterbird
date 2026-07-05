"""Response normalization helpers.

``normalize_todo`` performs real work (stripping internal fields).
All other domain models now use English column names matching what
the frontend expects, so ``dict(item)`` is sufficient to create a
shallow copy.  The remaining helpers have been inlined at call sites.
"""

from __future__ import annotations

from typing import Any


def normalize_todo(todo: dict[str, Any]) -> dict[str, Any]:
    """Normalize a todo dict for frontend response.

    Removes internal-only fields (``_computed_priority``) and
    recursively normalizes children.
    """
    result = dict(todo)
    result.pop("_computed_priority", None)
    if "children" in result:
        result["children"] = [normalize_todo(c) for c in result["children"]]
    return result


def normalize_todo_for_db(todo: dict[str, Any]) -> dict[str, Any]:
    """Convert frontend-facing keys back to DB column names (legacy).

    Used only by command handlers that construct raw INSERT dicts.
    Will be removed once handlers are updated.
    """
    return todo

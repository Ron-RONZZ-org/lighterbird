"""LLM tools for system-level operations.

Currently provides one tool:
    - ``system.now`` — Current datetime in UTC and local timezone for
      temporal reasoning.
"""

from __future__ import annotations

from datetime import datetime, timezone

from lightercore.permissions import PermissionLevel

from lighterbird.server.llm.tools import llm_tool


@llm_tool(
    name="system.now",
    description=(
        "Get the current datetime in UTC and the local timezone. "
        "Use this for any temporal reasoning — determining what 'today' "
        "means, filtering by date, scheduling, or interpreting relative "
        "time references from the user."
    ),
    permission_level=PermissionLevel.READ,
)
def llm_system_now() -> dict:
    """Return the current timestamp with timezone information.

    Returns:
        ``{"success": True, "data": {"utc": ..., "local": ..., "timezone": ..., "iso": ...}}``
    """
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    return {
        "success": True,
        "data": {
            "utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local": now_local.isoformat(),
            "timezone": str(now_local.tzinfo or "UTC"),
            "iso": now_utc.isoformat(),
        },
    }

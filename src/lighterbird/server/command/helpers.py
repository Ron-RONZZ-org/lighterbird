"""Common handler boilerplate — UUID extraction, response builders, validation.

Reduces repetitive patterns across command handlers::

    from lighterbird.server.command.helpers import (
        status_response,
        require_uuid,
        require_found,
    )
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError


def require_uuid(
    remaining: list[str],
    usage_hint: str = "Usage: !<command> <uuid>",
) -> str:
    """Extract and return a UUID from the first remaining token.

    Args:
        remaining: Positional tokens after the command path.
        usage_hint: Error suggestion shown when UUID is missing.

    Returns:
        The UUID string.

    Raises:
        CommandValidationError: If no token is available.
    """
    if not remaining:
        raise CommandValidationError("Missing UUID.", usage_hint)
    return remaining[0]


def require_found(
    entity: Any,
    uuid_prefix: str,
    entity_name: str = "entry",
) -> None:
    """Raise if an entity lookup returned None.

    Args:
        entity: The result of ``svc.get(uuid)`` (may be ``None``).
        uuid_prefix: First 8 chars of the UUID (for error message).
        entity_name: Human-readable name (e.g. ``"letter"``, ``"contact"``).

    Raises:
        CommandValidationError: If *entity* is ``None``.
    """
    if entity is None:
        raise CommandValidationError(
            f"{entity_name.title()} not found: {uuid_prefix}",
        )


def status_response(
    title: str,
    summary: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``status``-type response dict with a summary string.

    Args:
        title: Tab title shown in the frontend.
        summary: Multi-line help text or result summary.
        extra: Additional data keys merged into the response.

    Returns:
        A dict with ``type``, ``title``, and ``data`` keys.
    """
    data: dict[str, Any] = {"_summary": summary}
    if extra:
        data.update(extra)
    return {"type": "status", "title": title, "data": data}

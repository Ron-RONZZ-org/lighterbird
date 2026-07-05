"""Command handlers for the ``!email spam`` domain.

Spam block management — block senders/domains, list blocks, sieve sync.

Backend lives in ``lighterbird.email.filters.spam.SpamManager``.
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.spam")
def spam_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam — Show spam subcommands."""
    return {
        "type": "status",
        "title": "Spam Commands",
        "data": {
            "_summary": (
                "Available !email spam commands:\n"
                "  !email spam list                   — List spam blocks\n"
                "  !email spam add <sender>           — Block a sender (email)\n"
                "  !email spam add @<domain>          — Block a domain\n"
                "  !email spam remove <uuid>          — Remove a block\n"
                "  !email spam sieve                  — Generate Sieve script from blocks"
            ),
        },
    }


@command("email.spam.list")
def spam_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam list — List all spam blocks."""
    svc = get_email_service()
    blocks = svc.spam.list_blocks()
    return {"type": "status", "title": "Spam Blocks", "data": {"blocks": blocks, "count": len(blocks)}}


@command("email.spam.add")
def spam_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam add <sender-or-domain>

    Blocks a sender email or domain.
    Prepend ``@`` to block a domain (e.g. ``!email spam add @spam.example.com``).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing sender or domain.",
            "Usage: !email spam add <email>         — Block a sender\n"
            "       !email spam add @<domain>        — Block a domain\n"
            "       !email spam add --sender <email>  — Block a sender\n"
            "       !email spam add --domain <name>   — Block a domain",
        )

    svc = get_email_service()
    raw = remaining[0]

    if raw.startswith("@"):
        block = svc.spam.block_domain(raw[1:])
        label = f"@{block['pattern']}"
    elif "@" in raw:
        block = svc.spam.block_sender(raw)
        label = block["pattern"]
    else:
        raise CommandValidationError(
            f"Don't know how to interpret: {raw}",
            "Use an email address to block a sender, or @domain to block a domain.\n"
            "  e.g. !email spam add spammer@example.com\n"
            "       !email spam add @spam.example.com",
        )

    return {
        "type": "status",
        "title": "Block Added",
        "data": {"uuid": block["uuid"][:8], "type": block["type"], "pattern": label},
    }


@command("email.spam.remove")
def spam_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam remove <uuid> — Remove a spam block by UUID."""
    if not remaining:
        raise CommandValidationError(
            "Missing block UUID.",
            "Usage: !email spam remove <uuid>",
        )
    svc = get_email_service()
    svc.spam.unblock(remaining[0])
    return {"type": "status", "title": "Block Removed", "data": {"uuid": remaining[0][:8]}}


@command("email.spam.sieve")
def spam_sieve(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email spam sieve — Generate Sieve script from current blocks."""
    svc = get_email_service()
    script = svc.spam.to_sieve()
    if not script:
        return {"type": "status", "title": "Sieve Script", "data": {"script": "(no blocks — empty script)"}}
    return {"type": "status", "title": "Spam Sieve Script", "data": {"script": script}}

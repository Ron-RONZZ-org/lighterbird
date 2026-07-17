"""Command handlers for the ``!email block`` domain.

Block management — block senders/domains, list blocks.
Edit/delete operations are GUI-only via the list tab (REST API).

Backend lives in ``lighterbird.email.filters.spam.SpamManager``.
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.block.list", permission_level=PermissionLevel.READ)
def block_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email block list — List all blocked senders/domains."""
    svc = get_email_service()
    blocks = svc.spam.list_blocks()
    return {
        "type": "block-list",
        "title": "Blocked Senders",
        "data": {"blocks": blocks, "total": len(blocks)},
    }


@command("email.block.add",
         params=[
             {"name": "target", "type": "string",
              "help": "Email address or @domain to block",
              "required": True},
         ],
         flags=[
             {"name": "note", "type": "string",
              "help": "Optional reason for blocking"},
             {"name": "domain", "type": "string",
              "help": "Domain to block (alternative to @domain syntax)"},
             {"name": "sender", "type": "string",
              "help": "Email address to block (explicit flag form)"},
         ],
         interactive=True)
def block_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email block add <sender-or-domain> [--note TEXT]

    Blocks a sender email or domain.
    Prepend ``@`` to block a domain (e.g. ``!email block add @spam.example.com``).
    Use ``--domain`` or ``--sender`` flags to block explicitly.
    """
    svc = get_email_service()

    note = flags.get("note", "")

    # 1. Check explicit flags first (--domain and --sender)
    domain_flag = flags.get("domain", "")
    sender_flag = flags.get("sender", "")

    if domain_flag:
        block = svc.spam.block_domain(domain_flag, note=note)
        label = f"@{block['pattern']}"
        return {
            "type": "status", "title": "Block Added",
            "data": {"uuid": block["uuid"][:8], "type": block["type"],
                     "pattern": label, "note": block.get("note", "")},
        }

    if sender_flag:
        block = svc.spam.block_sender(sender_flag, note=note)
        label = block["pattern"]
        return {
            "type": "status", "title": "Block Added",
            "data": {"uuid": block["uuid"][:8], "type": block["type"],
                     "pattern": label, "note": block.get("note", "")},
        }

    # 2. Check remaining positional args (user typed inline)
    if remaining:
        raw = remaining[0]
        if raw.startswith("@"):
            block = svc.spam.block_domain(raw[1:], note=note)
            label = f"@{block['pattern']}"
        elif "@" in raw:
            block = svc.spam.block_sender(raw, note=note)
            label = block["pattern"]
        else:
            raise CommandValidationError(
                f"Don't know how to interpret: {raw}",
                "Use an email address to block a sender, or @domain to block a domain.\n"
                "  e.g. !email block add spammer@example.com\n"
                "       !email block add @spam.example.com",
            )
        return {
            "type": "status", "title": "Block Added",
            "data": {"uuid": block["uuid"][:8], "type": block["type"],
                     "pattern": label, "note": block.get("note", "")},
        }

    # 3. No args — interactive form fallback
    return {
        "type": "form-required",
        "title": "Block Sender/Domain",
        "data": {
            "form": "email-block-add",
            "initialData": {},
        },
    }

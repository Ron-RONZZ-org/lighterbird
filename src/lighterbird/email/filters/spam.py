"""Spam block management — local blocklists + Sieve rule generation.

Forked from A-lien's ``service/retposto_spamo.py``. Provides local
spam block management (block sender, block domain) with optional
Sieve script generation.
"""

from __future__ import annotations

from typing import Any


class SpamManager:
    """Local spam blocklist management.

    Blocks are stored in the email DB (using the messages table's
    ``spamo`` flag) and optionally exported as Sieve rules.
    """

    def __init__(self, db) -> None:
        self.db = db

    # ── Block management ────────────────────────────────────────────────

    def block_sender(self, sender: str) -> dict[str, Any]:
        """Block emails from a specific sender.

        Args:
            sender: Email address to block.

        Returns:
            Block record dict.
        """
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        block = {
            "uuid": str(uuid.uuid4()),
            "type": "sender",
            "pattern": sender.strip().lower(),
            "created_at": now,
            "updated_at": now,
        }
        return self.db.execute_one(
            "INSERT INTO spam_blocks (uuid, type, pattern, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (block["uuid"], block["type"], block["pattern"], now, now),
        )

    def block_domain(self, domain: str) -> dict[str, Any]:
        """Block emails from a specific domain.

        Args:
            domain: Domain to block (e.g. ``"spam.example.com"``).

        Returns:
            Block record dict.
        """
        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        domain = domain.strip().lower()
        if domain.startswith("@"):
            domain = domain[1:]
        block = {
            "uuid": str(uuid.uuid4()),
            "type": "domain",
            "pattern": domain,
            "created_at": now,
            "updated_at": now,
        }
        return self.db.execute_one(
            "INSERT INTO spam_blocks (uuid, type, pattern, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (block["uuid"], block["type"], block["pattern"], now, now),
        )

    def unblock(self, block_uuid: str) -> None:
        """Remove a block by UUID."""
        self.db.execute("DELETE FROM spam_blocks WHERE uuid = ?", (block_uuid,))

    def list_blocks(self) -> list[dict[str, Any]]:
        """List all spam blocks."""
        return self.db.execute("SELECT * FROM spam_blocks ORDER BY created_at DESC")

    # ── Sieve export ────────────────────────────────────────────────────

    def to_sieve(self) -> str:
        """Generate a Sieve script from all active blocks.

        Returns:
            Sieve ``reject`` script as a string.
        """
        blocks = self.list_blocks()
        if not blocks:
            return ""

        lines: list[str] = [
            'require ["reject", "envelope"];',
            "",
        ]

        for block in blocks:
            pattern = block["pattern"]
            if block["type"] == "sender":
                lines.append(
                    f'if envelope :contains "from" "{pattern}" {{'
                )
                lines.append(f'    reject "Blocked sender: {pattern}";')
                lines.append("}")
            elif block["type"] == "domain":
                lines.append(
                    f'if envelope :matches "from" "*@{pattern}" {{'
                )
                lines.append(f'    reject "Blocked domain: {pattern}";')
                lines.append("}")

        return "\n".join(lines)


__all__ = ["SpamManager"]

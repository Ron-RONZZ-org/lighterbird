"""Spam block management — local blocklists + Sieve rule generation.

Forked from A-lien's ``service/retposto_spamo.py``. Provides local
spam block management (block sender, block domain) with optional
Sieve script generation.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any


class SpamManager:
    """Local spam blocklist management.

    Blocks are stored in the email DB (using the messages table's
    ``spamo`` flag) and optionally exported as Sieve rules.
    """

    def __init__(self, db) -> None:
        self.db = db

    # ── Block management ────────────────────────────────────────────────

    def block_sender(self, sender: str, note: str = "") -> dict[str, Any]:
        """Block emails from a specific sender.

        Args:
            sender: Email address to block.
            note: Optional reason for blocking.

        Returns:
            Block record dict.
        """
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        block_id = str(uuid.uuid4())
        return self.db.execute_one(
            "INSERT INTO spam_blocks (uuid, type, pattern, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
            (block_id, "sender", sender.strip().lower(), note, now, now),
        )

    def block_domain(self, domain: str, note: str = "") -> dict[str, Any]:
        """Block emails from a specific domain.

        Args:
            domain: Domain to block (e.g. ``"spam.example.com"``).
            note: Optional reason for blocking.

        Returns:
            Block record dict.
        """
        import uuid
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        domain = domain.strip().lower()
        if domain.startswith("@"):
            domain = domain[1:]
        block_id = str(uuid.uuid4())
        return self.db.execute_one(
            "INSERT INTO spam_blocks (uuid, type, pattern, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
            (block_id, "domain", domain, note, now, now),
        )

    def get_block(self, block_uuid: str) -> dict[str, Any] | None:
        """Get a single block by UUID.

        Args:
            block_uuid: Block UUID.

        Returns:
            Block record dict or None if not found.
        """
        return self.db.execute_one(
            "SELECT * FROM spam_blocks WHERE uuid = ?", (block_uuid,)
        )

    def update_block(self, block_uuid: str, note: str | None = None) -> dict[str, Any] | None:
        """Update a block's note.

        Args:
            block_uuid: Block UUID.
            note: New note text. If None, the note is not changed.

        Returns:
            Updated block record dict, or None if not found.
        """
        existing = self.get_block(block_uuid)
        if not existing:
            return None
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        new_note = note if note is not None else existing.get("note", "")
        self.db.execute(
            "UPDATE spam_blocks SET note = ?, updated_at = ? WHERE uuid = ?",
            (new_note, now, block_uuid),
        )
        return {**existing, "note": new_note, "updated_at": now}

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

"""Signature service — per-account named signature CRUD.

Replaces the single ``signature`` field on the accounts table with
multiple named signatures per account stored in the ``email_signatures``
table.  Name uniqueness is enforced per account (DB UNIQUE constraint).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

_COLS = ("uuid", "account_email", "name", "signature_text",
         "created_at", "updated_at")


class SignatureService:
    """Manage named email signatures for each account."""

    def __init__(self, db: Any):
        self.db = db

    # ── Queries ─────────────────────────────────────────────────────────

    def list_signatures(self, account_email: str | None = None) -> list[dict]:
        """List signatures, optionally filtered by account."""
        if account_email:
            rows = self.db.execute(
                "SELECT * FROM email_signatures WHERE account_email = ? "
                "ORDER BY name ASC",
                (account_email,),
            )
        else:
            rows = self.db.execute(
                "SELECT * FROM email_signatures ORDER BY account_email, name ASC"
            )
        return [dict(r) for r in rows]

    def get(self, uuid_: str) -> dict | None:
        """Get a signature by UUID."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures WHERE uuid = ?", (uuid_,)
        )
        return dict(row) if row else None

    def get_by_name(self, account_email: str, name: str) -> dict | None:
        """Get a signature by account email and name."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures WHERE account_email = ? AND name = ?",
            (account_email, name),
        )
        return dict(row) if row else None

    def get_default(self, account_email: str) -> dict | None:
        """Get the ``default`` signature for an account, or None."""
        return self.get_by_name(account_email, "default")

    def get_first(self, account_email: str) -> dict | None:
        """Get the first available signature for an account."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures WHERE account_email = ? "
            "ORDER BY created_at ASC LIMIT 1",
            (account_email,),
        )
        return dict(row) if row else None

    # ── Mutations ───────────────────────────────────────────────────────

    def create(self, account_email: str, name: str,
               signature_text: str = "") -> dict:
        """Create a new named signature.

        Raises:
            ValueError: If a signature with the same name already exists
                for this account.
        """
        now = datetime.now(UTC).isoformat()
        uid = str(uuid.uuid4())
        try:
            self.db.execute(
                "INSERT INTO email_signatures "
                "(uuid, account_email, name, signature_text, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uid, account_email, name, signature_text, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(
                    f"Signature name '{name}' already exists for {account_email}."
                )
            raise
        return {"uuid": uid, "account_email": account_email,
                "name": name, "signature_text": signature_text}

    def update(self, uuid_: str, name: str | None = None,
               signature_text: str | None = None) -> dict | None:
        """Update a signature's name and/or text.

        Returns the updated signature, or None if not found.
        """
        existing = self.get(uuid_)
        if not existing:
            return None
        now = datetime.now(UTC).isoformat()
        new_name = name if name is not None else existing["name"]
        new_text = signature_text if signature_text is not None else existing["signature_text"]
        try:
            self.db.execute(
                "UPDATE email_signatures SET name = ?, signature_text = ?, "
                "updated_at = ? WHERE uuid = ?",
                (new_name, new_text, now, uuid_),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(
                    f"Signature name '{new_name}' already exists for "
                    f"{existing['account_email']}."
                )
            raise
        return {**existing, "name": new_name, "signature_text": new_text,
                "updated_at": now}

    def delete(self, uuid_: str) -> bool:
        """Delete a signature by UUID. Returns True if deleted."""
        self.db.execute("DELETE FROM email_signatures WHERE uuid = ?", (uuid_,))
        return self.db.execute_one(
            "SELECT changes() AS cnt"
        )["cnt"] > 0

    # ── Resolution ──────────────────────────────────────────────────────

    def resolve_text(self, account_email: str,
                     name: str | None = None) -> str:
        """Resolve signature text for an account.

        Args:
            account_email: The account email.
            name: Signature name (None = use ``default``).

        Returns:
            Signature text string, or empty string if not found.
        """
        if name is not None:
            sig = self.get_by_name(account_email, name)
        else:
            sig = self.get_default(account_email)
        if not sig:
            # Fall back to the first available signature
            sig = self.get_first(account_email)
        return (sig or {}).get("signature_text", "")


__all__ = ["SignatureService"]

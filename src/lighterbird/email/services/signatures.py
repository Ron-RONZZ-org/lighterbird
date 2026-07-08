"""Signature service — global named signature CRUD (decoupled from accounts).

Signatures are global, not per-account.  Per-account defaults are stored
via ``accounts.default_signature_uuid``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

_COLS = ("uuid", "name", "signature_text", "signature_format",
         "created_at", "updated_at")


class SignatureService:
    """Manage named email signatures (global scope)."""

    def __init__(self, db: Any):
        self.db = db

    # ── Queries ─────────────────────────────────────────────────────────

    def list_signatures(self) -> list[dict]:
        """List all signatures, ordered by name."""
        rows = self.db.execute(
            "SELECT * FROM email_signatures ORDER BY name ASC"
        )
        return [dict(r) for r in rows]

    def get(self, uuid_: str) -> dict | None:
        """Get a signature by UUID."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures WHERE uuid = ?", (uuid_,)
        )
        return dict(row) if row else None

    def get_by_name(self, name: str) -> dict | None:
        """Get a signature by name (global uniqueness)."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures WHERE name = ?",
            (name,),
        )
        return dict(row) if row else None

    def get_default(self, account_email: str) -> dict | None:
        """Get the default signature for an account.

        Looks up ``accounts.default_signature_uuid``.
        Falls back to the first available signature.
        """
        row = self.db.execute_one(
            "SELECT a.default_signature_uuid FROM accounts a WHERE a.email = ?",
            (account_email,),
        )
        if row and row["default_signature_uuid"]:
            return self.get(row["default_signature_uuid"])
        # Fall back to the first signature
        return self.get_first()

    def get_first(self) -> dict | None:
        """Get the first available signature (by creation date)."""
        row = self.db.execute_one(
            "SELECT * FROM email_signatures ORDER BY created_at ASC LIMIT 1"
        )
        return dict(row) if row else None

    # ── Mutations ───────────────────────────────────────────────────────

    def create(self, name: str,
               signature_text: str = "",
               signature_format: str = "plain") -> dict:
        """Create a new named signature.

        Args:
            name: Unique signature name.
            signature_text: The signature content.
            signature_format: One of ``"plain"``, ``"html"``, ``"markdown"``.
                Defaults to ``"plain"`` for backward compatibility.

        Raises:
            ValueError: If a signature with the same name already exists,
                or *signature_format* is invalid.
        """
        if signature_format not in ("plain", "html", "markdown"):
            raise ValueError(
                f"Invalid signature format '{signature_format}'. "
                "Must be 'plain', 'html', or 'markdown'."
            )
        now = datetime.now(UTC).isoformat()
        uid = str(uuid.uuid4())
        try:
            self.db.execute(
                "INSERT INTO email_signatures "
                "(uuid, name, signature_text, signature_format, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uid, name, signature_text, signature_format, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(
                    f"Signature name '{name}' already exists."
                )
            raise
        return {"uuid": uid,
                "name": name, "signature_text": signature_text,
                "signature_format": signature_format}

    def update(self, uuid_: str, name: str | None = None,
               signature_text: str | None = None,
               signature_format: str | None = None) -> dict | None:
        """Update a signature's name, text, and/or format.

        Returns the updated signature, or None if not found.

        Args:
            uuid_: Signature UUID.
            name: New name (or None to keep current).
            signature_text: New text (or None to keep current).
            signature_format: New format (or None to keep current).
                Must be ``"plain"``, ``"html"``, or ``"markdown"``.
        """
        existing = self.get(uuid_)
        if not existing:
            return None
        if signature_format and signature_format not in ("plain", "html", "markdown"):
            raise ValueError(
                f"Invalid signature format '{signature_format}'. "
                "Must be 'plain', 'html', or 'markdown'."
            )
        now = datetime.now(UTC).isoformat()
        new_name = name if name is not None else existing["name"]
        new_text = signature_text if signature_text is not None else existing["signature_text"]
        new_fmt = signature_format if signature_format is not None else existing.get("signature_format", "plain")
        try:
            self.db.execute(
                "UPDATE email_signatures SET name = ?, signature_text = ?, "
                "signature_format = ?, updated_at = ? WHERE uuid = ?",
                (new_name, new_text, new_fmt, now, uuid_),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ValueError(
                    f"Signature name '{new_name}' already exists."
                )
            raise
        return {**existing, "name": new_name, "signature_text": new_text,
                "signature_format": new_fmt, "updated_at": now}

    def delete(self, uuid_: str) -> bool:
        """Delete a signature by UUID. Returns True if deleted."""
        self.db.execute("DELETE FROM email_signatures WHERE uuid = ?", (uuid_,))
        return self.db.execute_one(
            "SELECT changes() AS cnt"
        )["cnt"] > 0

    # ── Per-account default management ──────────────────────────────────

    def set_account_default(self, account_email: str,
                            signature_uuid: str | None) -> None:
        """Set the default signature for an account.

        Args:
            account_email: The account email.
            signature_uuid: Signature UUID, or None to clear the default.
        """
        self.db.execute(
            "UPDATE accounts SET default_signature_uuid = ? WHERE email = ?",
            (signature_uuid, account_email),
        )

    def get_account_default_uuid(self, account_email: str) -> str | None:
        """Get the default signature UUID for an account, or None."""
        row = self.db.execute_one(
            "SELECT default_signature_uuid FROM accounts WHERE email = ?",
            (account_email,),
        )
        return row["default_signature_uuid"] if row else None

    # ── Resolution ──────────────────────────────────────────────────────

    def resolve_text(self, account_email: str,
                     name: str | None = None) -> str:
        """Resolve signature text for an account.

        Args:
            account_email: The account email (used for per-account default).
            name: Signature name for explicit lookup. If None, uses
                  the account's default signature.

        Returns:
            Signature text string, or empty string if not found.
        """
        sig = self.resolve(account_email, name=name)
        return (sig or {}).get("signature_text", "")

    def resolve(self, account_email: str,
                name: str | None = None) -> dict | None:
        """Resolve the full signature dict (text + format) for an account.

        Args:
            account_email: The account email (used for per-account default).
            name: Signature name for explicit lookup. If None, uses
                  the account's default signature.

        Returns:
            Signature dict with ``signature_text`` and ``signature_format``,
            or None if no signature is configured.
        """
        if name is not None:
            sig = self.get_by_name(name)
        else:
            sig = self.get_default(account_email)
        if not sig:
            # Fall back to the first available signature
            sig = self.get_first()
        if sig:
            sig.setdefault("signature_format", "plain")
        return sig


__all__ = ["SignatureService"]

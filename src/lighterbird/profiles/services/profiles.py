"""Profile service — CRUD for user identity profiles.

Each profile stores personal info, contact details, and custom fields
for a named identity (e.g. "work", "home", "personal").
"""

from __future__ import annotations

import json
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.profiles.db import get_db


class ProfileError(Exception):
    """Validation error for profile operations."""


class ProfileService(CRUDService):
    """CRUD for user identity profiles, extending CRUDService."""

    def __init__(self) -> None:
        db = get_db()
        super().__init__(db, "user_profiles")

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_full_name(given: str = "", middle: str = "", family: str = "") -> str:
        parts = [p for p in [given, middle, family] if p]
        return " ".join(parts) if parts else ""

    @staticmethod
    def _validate_json_field(value: str, field_name: str) -> None:
        """Validate that the value is parseable JSON."""
        try:
            json.loads(value)
        except json.JSONDecodeError as e:
            raise ProfileError(f"Invalid JSON for {field_name}: {e}")

    @staticmethod
    def get_primary_email(data: dict[str, Any]) -> str:
        """Return the first email value from the emails JSON array, or empty."""
        try:
            emails = json.loads(data.get("emails", "[]"))
            if emails and isinstance(emails, list):
                return emails[0].get("value", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
        return ""

    @staticmethod
    def get_primary_phone(data: dict[str, Any]) -> str:
        """Return the first phone value from the phones JSON array, or empty."""
        try:
            phones = json.loads(data.get("phones", "[]"))
            if phones and isinstance(phones, list):
                return phones[0].get("value", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
        return ""

    # ── Overrides ─────────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        data["full_name"] = self._compute_full_name(
            data.get("given_name", ""),
            data.get("middle_names", ""),
            data.get("family_name", ""),
        )
        # Validate JSON fields
        for field in ("emails", "phones", "custom_fields"):
            if field in data:
                self._validate_json_field(data[field], field)
        return super().create(data)

    def update(self, uuid_: str, data: dict[str, Any]) -> dict[str, Any]:
        if "given_name" in data or "middle_names" in data or "family_name" in data:
            existing = self.get(uuid_)
            if existing:
                data["full_name"] = self._compute_full_name(
                    data.get("given_name", existing.get("given_name", "")),
                    data.get("middle_names", existing.get("middle_names", "")),
                    data.get("family_name", existing.get("family_name", "")),
                )
        for field in ("emails", "phones", "custom_fields"):
            if field in data:
                self._validate_json_field(data[field], field)
        return super().update(uuid_, data)

    def list(self) -> list[dict[str, Any]]:
        """List all profiles with primary email display."""
        rows = super().list(order_by="created_at", desc=False)
        result = []
        for row in rows:
            primary_email = self.get_primary_email(row)
            result.append({**row, "_primary_email": primary_email})
        return result

"""TagService — shared cross-domain tag management.

Provides a unified API for creating, listing, renaming, and deleting tags,
and for attaching/detaching them to items across any domain.

Usage::

    svc = TagService()
    svc.create_tag("urgent", color="#ff4444")
    svc.add_tag("todo", todo_uuid, "urgent")
    tags = svc.get_tags_for("todo", todo_uuid)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lighterbird.tags.db import get_db


class TagService:
    """Cross-domain tag management service.

    All tag data lives in ``tags.db``. Domains (todo, journal, etc.)
    reference tags through the ``taggings`` junction table with a
    ``domain`` discriminator.
    """

    def __init__(self, db=None):
        self.db = db or get_db()

    # ── Tag CRUD ─────────────────────────────────────────────────────────

    def list_tags(self) -> list[dict[str, Any]]:
        """List all tags ordered by name."""
        return self.db.execute("SELECT * FROM tags ORDER BY name")

    def create_tag(self, name: str, color: str = "") -> dict[str, Any]:
        """Create a new tag.

        Args:
            name: Tag name (case-insensitive unique).
            color: Optional hex color (e.g. ``"#ff4444"``).

        Returns:
            The created tag record.

        Raises:
            ValueError: If the tag already exists.
        """
        name = name.strip()
        if not name:
            raise ValueError("Tag name is required.")
        now = datetime.now(UTC).isoformat()
        try:
            return self.db.execute_one(
                "INSERT INTO tags (name, color, created_at, updated_at)"
                " VALUES (?, ?, ?, ?) RETURNING *",
                (name, color, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Tag '{name}' already exists.") from e
            raise

    def rename_tag(self, old_name: str, new_name: str) -> dict[str, Any]:
        """Rename a tag, updating all taggings.

        Args:
            old_name: Current tag name.
            new_name: New tag name.

        Returns:
            The updated tag record.

        Raises:
            ValueError: If the old tag doesn't exist or new name is taken.
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("New tag name is required.")
        now = datetime.now(UTC).isoformat()
        # Check old tag exists
        old = self.db.execute_one("SELECT * FROM tags WHERE name = ?", (old_name,))
        if not old:
            raise ValueError(f"Tag '{old_name}' not found.")
        # Insert the new tag first, then reassign taggings, then delete old.
        # This avoids FK violations during the transition.
        try:
            self.db.execute(
                "INSERT INTO tags (name, color, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (new_name, old["color"], now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Tag '{new_name}' already exists.") from e
            raise
        self.db.execute(
            "UPDATE taggings SET tag_name = ?, created_at = ? WHERE tag_name = ?",
            (new_name, now, old_name),
        )
        self.db.execute("DELETE FROM tags WHERE name = ?", (old_name,))
        return self.db.execute_one("SELECT * FROM tags WHERE name = ?", (new_name,))

    def delete_tag(self, name: str) -> None:
        """Delete a tag and all its taggings (CASCADE).

        Args:
            name: Tag name to delete.

        Raises:
            ValueError: If the tag doesn't exist.
        """
        existing = self.db.execute_one("SELECT 1 FROM tags WHERE name = ?", (name,))
        if existing is None:
            raise ValueError(f"Tag '{name}' not found.")
        self.db.execute("DELETE FROM tags WHERE name = ?", (name,))

    # ── Taggings ─────────────────────────────────────────────────────────

    def get_tags_for(self, domain: str, item_uuid: str) -> list[dict[str, Any]]:
        """Get all tags attached to an item.

        Args:
            domain: Domain name (e.g. ``"todo"``, ``"journal"``).
            item_uuid: UUID of the item.

        Returns:
            List of tag dicts (name, color).
        """
        return self.db.execute(
            "SELECT t.* FROM tags t"
            " JOIN taggings tg ON t.name = tg.tag_name"
            " WHERE tg.domain = ? AND tg.item_uuid = ?"
            " ORDER BY t.name",
            (domain, item_uuid),
        )

    def add_tag(self, domain: str, item_uuid: str, tag_name: str) -> None:
        """Attach a tag to an item.

        Creates the tag if it doesn't exist yet.
        """
        now = datetime.now(UTC).isoformat()
        # Ensure tag exists
        self.db.execute(
            "INSERT OR IGNORE INTO tags (name, color, created_at, updated_at)"
            " VALUES (?, '', ?, ?)",
            (tag_name, now, now),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO taggings (tag_name, domain, item_uuid, created_at)"
            " VALUES (?, ?, ?, ?)",
            (tag_name, domain, item_uuid, now),
        )

    def remove_tag(self, domain: str, item_uuid: str, tag_name: str) -> None:
        """Detach a tag from an item.

        Does not delete the tag itself.
        """
        self.db.execute(
            "DELETE FROM taggings"
            " WHERE tag_name = ? AND domain = ? AND item_uuid = ?",
            (tag_name, domain, item_uuid),
        )

    def set_tags(self, domain: str, item_uuid: str, tag_names: list[str]) -> None:
        """Replace all tags on an item with the given set.

        Removes any existing taggings not in *tag_names*, then adds
        any new ones. Idempotent.
        """
        now = datetime.now(UTC).isoformat()
        # Get current tags
        current = {
            row["tag_name"]
            for row in self.db.execute(
                "SELECT tag_name FROM taggings WHERE domain = ? AND item_uuid = ?",
                (domain, item_uuid),
            )
        }
        target = set(tag_names)

        # Remove stale
        stale = current - target
        for name in stale:
            self.db.execute(
                "DELETE FROM taggings WHERE tag_name = ? AND domain = ? AND item_uuid = ?",
                (name, domain, item_uuid),
            )

        # Add new
        new = target - current
        for name in new:
            self.db.execute(
                "INSERT OR IGNORE INTO tags (name, color, created_at, updated_at)"
                " VALUES (?, '', ?, ?)",
                (name, now, now),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO taggings (tag_name, domain, item_uuid, created_at)"
                " VALUES (?, ?, ?, ?)",
                (name, domain, item_uuid, now),
            )

    def list_tags_for_domain(self, domain: str) -> list[dict[str, Any]]:
        """List all tags used in a specific domain, with usage count.

        Args:
            domain: Domain name.

        Returns:
            List of dicts with keys: name, color, usage_count.
        """
        return self.db.execute(
            "SELECT t.*, COUNT(tg.item_uuid) AS usage_count"
            " FROM tags t"
            " LEFT JOIN taggings tg ON t.name = tg.tag_name AND tg.domain = ?"
            " GROUP BY t.name"
            " HAVING usage_count > 0"
            " ORDER BY t.name",
            (domain,),
        )

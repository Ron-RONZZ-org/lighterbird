"""Journal CRUD service with label management (via shared tag system)."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.core.yaml_frontmatter import unwrap, wrap
from lighterbird.tags.service import TagService


class JournalService(CRUDService):
    """CRUD service for journal (journal entries) with labels."""

    def __init__(self, db):
        super().__init__(db, "journal")

    def _tag_svc(self) -> TagService:
        svc = getattr(self, "_tag_service", None)
        if svc is None:
            svc = TagService()
            self._tag_service = svc
        return svc

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a journal entry with a default date if not provided."""
        from datetime import UTC, datetime

        data = dict(data)
        data.setdefault("date", datetime.now(UTC).date().isoformat())
        return super().create(data)

    # ── Markdown export / import ────────────────────────────────────────

    def export_md(self, uuid: str | None = None, uuids: list[str] | None = None) -> str:
        """Export one or more journal entries as a .md string with YAML frontmatter.

        Args:
            uuid: Single entry UUID.
            uuids: Multiple entry UUIDs.

        Returns:
            Full markdown string(s) concatenated with ``---`` separators.
        """
        ids: list[str] = []
        if uuids:
            ids.extend(uuids)
        if uuid:
            ids.append(uuid)

        parts: list[str] = []
        for eid in ids:
            entry = self.get(eid)
            if not entry:
                continue
            meta = {
                "uuid": entry["uuid"],
                "domain": "journal",
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "date": entry.get("date"),
                "title": entry.get("title", ""),
            }
            body = entry.get("text", "")
            parts.append(wrap(body, meta))
        return "\n---\n".join(parts)

    def import_md(self, path: str) -> list[str]:
        """Import a .md file with YAML frontmatter as journal entry(s).

        Parses the frontmatter block (``---...---``) from the file and
        creates a journal entry from the metadata and body text.

        Args:
            path: Path to the .md file.

        Returns:
            List of created UUIDs.
        """
        text = Path(path).read_text(encoding="utf-8")
        meta, body = unwrap(text)
        if not meta:
            return []

        entry_data = {
            "title": meta.get("title", ""),
            "text": body,
            "date": meta.get("date", ""),
        }
        if meta.get("created_at"):
            entry_data["created_at"] = meta["created_at"]
        if meta.get("updated_at"):
            entry_data["updated_at"] = meta["updated_at"]
        # Don't pass uuid from frontmatter — let create() generate a new one
        # so re-importing an exported file doesn't hit UNIQUE constraint.
        entry = self.create(entry_data)
        return [entry["uuid"]]

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        if not query:
            return self.list(limit=limit)
        return self.db.execute(
            "SELECT * FROM journal WHERE "
            "LOWER(title) LIKE LOWER(?) OR LOWER(text) LIKE LOWER(?) "
            "ORDER BY date DESC, created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        )

    def list_by_date(self, date_str: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM journal WHERE date = ? ORDER BY created_at ASC",
            (date_str,),
        )

    # ── Labels (via shared tag system) ──────────────────────────────────

    def add_label(self, entry_uuid: str, label_name: str) -> None:
        self._tag_svc().add_tag("journal", entry_uuid, label_name)

    def remove_label(self, entry_uuid: str, label_name: str) -> None:
        self._tag_svc().remove_tag("journal", entry_uuid, label_name)

    def get_labels(self, entry_uuid: str) -> list[dict[str, Any]]:
        return self._tag_svc().get_tags_for("journal", entry_uuid)

    def list_all_labels(self) -> list[dict[str, Any]]:
        return self._tag_svc().list_tags()

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._tag_svc().create_tag(
            name=data.get("name", ""),
            color=data.get("color", ""),
        )

    def delete_label(self, label_name: str) -> None:
        self._tag_svc().delete_tag(label_name)

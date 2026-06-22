"""Contact CRUD service with FTS5 search and VCF import/export."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class ContactService(CRUDService):
    """CRUD service for kontaktoj (contacts)."""

    def __init__(self, db):
        super().__init__(db, "kontaktoj")

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search contacts by name, email, or organization using FTS5.

        Falls back to LIKE-based search if the query is short (FTS5
        minimum token length).
        """
        if not query:
            return self.list(limit=limit)
        query = query.strip()
        # FTS5 requires at least 2 characters per token
        if len(query) >= 2:
            try:
                return self.db.execute(
                    "SELECT kontaktoj.* FROM kontaktoj "
                    "JOIN kontaktoj_fts ON kontaktoj.rowid = kontaktoj_fts.rowid "
                    "WHERE kontaktoj_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (query, limit),
                )
            except Exception:
                pass  # fall through to LIKE search
        # Fallback: LIKE search
        return self.db.execute(
            "SELECT * FROM kontaktoj WHERE "
            "LOWER(nomo) LIKE LOWER(?) OR LOWER(retposto) LIKE LOWER(?) "
            "OR LOWER(organizo) LIKE LOWER(?) "
            "ORDER BY nomo ASC LIMIT ?",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        )

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self.db.execute_one(
            "SELECT * FROM kontaktoj WHERE LOWER(retposto) = LOWER(?)",
            (email.strip(),),
        )

    # ── VCF import ───────────────────────────────────────────────────────

    def import_vcf(self, path: str) -> int:
        """Import contacts from a VCF file.

        Args:
            path: Path to .vcf file.

        Returns:
            Number of contacts imported.

        Raises:
            ImportError: If ``vobject`` library is not installed.
            FileNotFoundError: If the VCF file is not found.
        """
        try:
            import vobject
        except ImportError:
            raise ImportError(
                "vobject library required for VCF import. "
                "Install: pip install vobject"
            )

        from pathlib import Path

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"VCF file not found: {path}")

        with path_obj.open("r", encoding="utf-8") as f:
            content = f.read()

        count = 0
        for vcard in vobject.readComponents(content):
            contact = self._vcard_to_contact(vcard)
            if contact and contact.get("plena_nomo"):
                self.create(contact)
                count += 1
        return count

    def export_vcf(self, uuid: str | None = None, path: str | None = None) -> str:
        """Export contact(s) to VCF format.

        Args:
            uuid: Single contact UUID (None = export all).
            path: Optional output file path (None = return string).

        Returns:
            VCF string (if path is None).
        """
        try:
            import vobject
        except ImportError:
            raise ImportError("vobject library required for VCF export")

        contacts = [self.get(uuid)] if uuid else self.list()
        lines: list[str] = []
        for contact in contacts:
            if not contact:
                continue
            lines.append(self._contact_to_vcard(contact))

        vcf_text = "\n".join(lines)
        if path:
            from pathlib import Path
            Path(path).write_text(vcf_text, encoding="utf-8")
        return vcf_text

    # ── VCF conversion helpers ───────────────────────────────────────────

    @staticmethod
    def _vcard_to_contact(vcard: Any) -> dict[str, Any]:
        """Convert a vobject vCard to a contact dict."""
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        contact: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "kreita_je": now,
            "modifita_je": now,
        }

        given = ""
        family = ""
        if hasattr(vcard, "n"):
            given = str(vcard.n.value.given) if vcard.n.value.given else ""
            family = str(vcard.n.value.family) if vcard.n.value.family else ""
            contact["nomo"] = given
            contact["familia_nomo"] = family
            contact["plena_nomo"] = f"{given} {family}".strip()

        if hasattr(vcard, "fn"):
            fn_val = str(vcard.fn.value) if vcard.fn.value else ""
            if not contact.get("plena_nomo"):
                contact["plena_nomo"] = fn_val
            if not contact.get("nomo") and not contact.get("familia_nomo"):
                contact["nomo"] = fn_val

        if hasattr(vcard, "email"):
            for email in vcard.contents.get("email", []):
                addr = str(email.value) if email.value else ""
                if addr and not contact.get("retposto"):
                    contact["retposto"] = addr

        if hasattr(vcard, "tel"):
            for tel in vcard.contents.get("tel", []):
                num = str(tel.value) if tel.value else ""
                if num and not contact.get("telefonnumero"):
                    contact["telefonnumero"] = num

        if hasattr(vcard, "org"):
            org_val = str(vcard.org.value) if vcard.org.value else ""
            if org_val:
                contact["organizo"] = org_val

        if hasattr(vcard, "categories"):
            cats = str(vcard.categories.value) if vcard.categories.value else ""
            if cats:
                contact["kategorio"] = ",".join(c.strip() for c in cats.split(","))

        if hasattr(vcard, "note"):
            note_val = str(vcard.note.value) if vcard.note.value else ""
            if note_val:
                contact["notoj"] = note_val

        return contact

    @staticmethod
    def _contact_to_vcard(contact: dict[str, Any]) -> str:
        """Convert a contact dict to vCard 3.0 string."""
        try:
            import vobject
        except ImportError:
            raise ImportError("vobject library required for VCF export")

        card = vobject.vCard()
        card.add("n")
        family = contact.get("familia_nomo", "")
        given = contact.get("nomo", "")
        card.n.value = vobject.vcard.Name(family=family, given=given)

        card.add("fn")
        card.fn.value = contact.get("plena_nomo", "") or f"{given} {family}".strip()

        email = contact.get("retposto", "")
        if email:
            card.add("email")
            card.email.value = email
            card.email.type_param = "INTERNET"

        phone = contact.get("telefonnumero", "")
        if phone:
            card.add("tel")
            card.tel.value = phone
            card.tel.type_param = "VOICE"

        org = contact.get("organizo", "")
        if org:
            card.add("org")
            card.org.value = [org]

        categories = contact.get("kategorio", "")
        if categories:
            card.add("categories")
            card.categories.value = categories

        note = contact.get("notoj", "")
        if note:
            card.add("note")
            card.note.value = note

        return card.serialize()

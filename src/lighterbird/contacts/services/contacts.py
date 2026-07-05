"""Contact CRUD service with FTS5 search and VCF import/export."""

from __future__ import annotations

import json
from typing import Any

from lighterbird.core.crud import CRUDService


class ContactService(CRUDService):
    """CRUD service for contacts (contacts)."""

    def __init__(self, db):
        super().__init__(db, "contacts")

    # ── Hooks ───────────────────────────────────────────────────────────

    def _compute_full_name(self, data: dict[str, Any]) -> str:
        parts = [data.get("given_name", ""), data.get("middle_names", ""), data.get("family_name", "")]
        return " ".join(p for p in parts if p).strip()

    def _validate_email_json(self, emails: Any) -> list[dict[str, str]]:
        if isinstance(emails, str):
            emails = json.loads(emails)
        if not isinstance(emails, list):
            raise ValueError("emails must be a JSON array")
        for item in emails:
            if not isinstance(item, dict) or "value" not in item:
                raise ValueError("Each email entry must have a 'value' key")
            item.setdefault("tag", "")
        return emails

    def _validate_phone_json(self, phones: Any) -> list[dict[str, str]]:
        if isinstance(phones, str):
            phones = json.loads(phones)
        if not isinstance(phones, list):
            raise ValueError("phones must be a JSON array")
        for item in phones:
            if not isinstance(item, dict) or "value" not in item:
                raise ValueError("Each phone entry must have a 'value' key")
            item.setdefault("tag", "")
        return phones

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        self._validate_email_json(result.get("emails", "[]"))
        self._validate_phone_json(result.get("phones", "[]"))

    def _post_update(
        self, uuid: str, old_data: dict[str, Any] | None, new_data: dict[str, Any]
    ) -> None:
        for fld in ("emails", "phones"):
            val = new_data.get(fld)
            if val is not None:
                (self._validate_email_json if fld == "emails" else self._validate_phone_json)(val)

    # ── Override create/update to ensure full_name is computed ──────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a contact, auto-computing full_name from given/middle/family."""
        data = dict(data)
        if not data.get("full_name"):
            data["full_name"] = self._compute_full_name(data)
        return super().create(data)

    def update(self, pk: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a contact, auto-computing full_name when name fields change."""
        data = dict(data)
        name_fields = {"given_name", "middle_names", "family_name"}
        if not data.get("full_name") and name_fields & data.keys():
            # Merge with existing data so we don't lose fields not in the update
            old = self.get(pk)
            merged = {**(old or {}), **data}
            computed = self._compute_full_name(merged)
            if computed:
                data["full_name"] = computed
        return super().update(pk, data)

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def get_primary_email(contact: dict[str, Any]) -> str:
        """Return the primary email (tagged 'primary') or the first one."""
        raw = contact.get("emails", "[]")
        if isinstance(raw, str):
            raw = json.loads(raw) if raw else []
        if not raw:
            return ""
        for entry in raw:
            if entry.get("tag", "").lower() == "primary":
                return entry.get("value", "")
        return raw[0].get("value", "")

    @staticmethod
    def get_primary_phone(contact: dict[str, Any]) -> str:
        """Return the primary phone (tagged 'primary') or the first one."""
        raw = contact.get("phones", "[]")
        if isinstance(raw, str):
            raw = json.loads(raw) if raw else []
        if not raw:
            return ""
        for entry in raw:
            if entry.get("tag", "").lower() == "primary":
                return entry.get("value", "")
        return raw[0].get("value", "")

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search contacts by name, email, phone, or organization using FTS5.

        Falls back to LIKE-based search if the query is short (FTS5
        minimum token length).
        """
        if not query:
            return self.list(limit=limit)
        query = query.strip()
        if len(query) >= 2:
            try:
                return self.db.execute(
                    "SELECT contacts.* FROM contacts "
                    "JOIN contacts_fts ON contacts.rowid = contacts_fts.rowid "
                    "WHERE contacts_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (query, limit),
                )
            except Exception:
                pass
        like_q = f"%{query}%"
        return self.db.execute(
            "SELECT * FROM contacts WHERE "
            "LOWER(given_name) LIKE LOWER(?) OR LOWER(family_name) LIKE LOWER(?) "
            "OR LOWER(emails) LIKE LOWER(?) OR LOWER(phones) LIKE LOWER(?) "
            "OR LOWER(organization) LIKE LOWER(?) OR LOWER(notes) LIKE LOWER(?) "
            "ORDER BY given_name ASC LIMIT ?",
            (like_q, like_q, like_q, like_q, like_q, like_q, limit),
        )

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self.db.execute_one(
            "SELECT * FROM contacts WHERE LOWER(emails) LIKE LOWER(?)",
            (f"%{email.strip()}%",),
        )

    # ── VCF import ──────────────────────────────────────────────────────

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
            if contact and contact.get("full_name"):
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

    # ── VCF conversion helpers ──────────────────────────────────────────

    @staticmethod
    def _vcard_to_contact(vcard: Any) -> dict[str, Any]:
        """Convert a vobject vCard to a contact dict."""
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        contact: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "created_at": now,
            "updated_at": now,
            "emails": "[]",
            "phones": "[]",
        }

        given = ""
        middle = ""
        family = ""
        if hasattr(vcard, "n"):
            given = str(vcard.n.value.given) if vcard.n.value.given else ""
            middle = str(vcard.n.value.additional) if vcard.n.value.additional else ""
            family = str(vcard.n.value.family) if vcard.n.value.family else ""
            contact["given_name"] = given
            contact["middle_names"] = middle
            contact["family_name"] = family
            full = " ".join(p for p in (given, middle, family) if p)
            contact["full_name"] = full

        if hasattr(vcard, "fn"):
            fn_val = str(vcard.fn.value) if vcard.fn.value else ""
            if not contact.get("full_name"):
                contact["full_name"] = fn_val
            if not contact.get("given_name") and not contact.get("family_name"):
                contact["given_name"] = fn_val

        emails: list[dict[str, str]] = []
        if hasattr(vcard, "email"):
            for email in vcard.contents.get("email", []):
                addr = str(email.value) if email.value else ""
                if addr:
                    tag = ""
                    if hasattr(email, "type_param") and email.type_param:
                        tag = email.type_param.lower()
                    elif hasattr(email, "params") and email.params.get("TYPE"):
                        types = email.params["TYPE"]
                        if isinstance(types, list):
                            tag = types[0].lower()
                        else:
                            tag = str(types).lower()
                    emails.append({"tag": tag, "value": addr})
        if emails:
            contact["emails"] = json.dumps(emails)

        phones: list[dict[str, str]] = []
        if hasattr(vcard, "tel"):
            for tel in vcard.contents.get("tel", []):
                num = str(tel.value) if tel.value else ""
                if num:
                    tag = ""
                    if hasattr(tel, "type_param") and tel.type_param:
                        tag = tel.type_param.lower()
                    elif hasattr(tel, "params") and tel.params.get("TYPE"):
                        types = tel.params["TYPE"]
                        if isinstance(types, list):
                            tag = types[0].lower()
                        else:
                            tag = str(types).lower()
                    phones.append({"tag": tag, "value": num})
        if phones:
            contact["phones"] = json.dumps(phones)

        if hasattr(vcard, "org"):
            # vobject stores ORG as a list, e.g. ["Acme Corp"]
            org_raw = vcard.org.value if vcard.org.value else []
            org_val = str(org_raw[0]) if isinstance(org_raw, list) and org_raw else ""
            if not org_val:
                org_val = str(org_raw) if org_raw else ""
            if org_val:
                contact["organization"] = org_val

        if hasattr(vcard, "title"):
            title_val = str(vcard.title.value) if vcard.title.value else ""
            if title_val:
                contact["position"] = title_val

        if hasattr(vcard, "adr"):
            adr = vcard.adr.value
            parts = []
            if hasattr(adr, "street") and adr.street:
                parts.append(str(adr.street))
            if hasattr(adr, "city") and adr.city:
                parts.append(str(adr.city))
            if hasattr(adr, "region") and adr.region:
                parts.append(str(adr.region))
            if hasattr(adr, "code") and adr.code:
                contact["post_code"] = str(adr.code)
            if parts:
                contact["address"] = ", ".join(parts)
            if hasattr(adr, "country") and adr.country:
                if contact.get("address"):
                    contact["address"] += ", " + str(adr.country)
                else:
                    contact["address"] = str(adr.country)

        if hasattr(vcard, "bday"):
            bday_val = str(vcard.bday.value) if vcard.bday.value else ""
            if bday_val:
                contact["date_of_birth"] = bday_val

        if hasattr(vcard, "categories"):
            cats = str(vcard.categories.value) if vcard.categories.value else ""
            if cats:
                contact["category"] = ",".join(c.strip() for c in cats.split(","))

        if hasattr(vcard, "note"):
            note_val = str(vcard.note.value) if vcard.note.value else ""
            if note_val:
                contact["notes"] = note_val

        return contact

    @staticmethod
    def _contact_to_vcard(contact: dict[str, Any]) -> str:
        """Convert a contact dict to vCard 3.0 string."""
        try:
            import vobject
        except ImportError:
            raise ImportError("vobject library required for VCF export")
        import json as _json

        card = vobject.vCard()
        card.add("n")
        family = contact.get("family_name", "")
        given = contact.get("given_name", "")
        middle = contact.get("middle_names", "")
        card.n.value = vobject.vcard.Name(family=family, given=given, additional=middle)

        card.add("fn")
        card.fn.value = contact.get("full_name", "") or " ".join(p for p in (given, middle, family) if p)

        raw_emails = contact.get("emails", "[]")
        if isinstance(raw_emails, str):
            raw_emails = _json.loads(raw_emails) if raw_emails else []
        for entry in raw_emails:
            addr = entry.get("value", "")
            if addr:
                card.add("email")
                card.email.value = addr
                tag = entry.get("tag", "").upper() or "INTERNET"
                card.email.type_param = tag

        raw_phones = contact.get("phones", "[]")
        if isinstance(raw_phones, str):
            raw_phones = _json.loads(raw_phones) if raw_phones else []
        for entry in raw_phones:
            num = entry.get("value", "")
            if num:
                card.add("tel")
                card.tel.value = num
                tag = entry.get("tag", "").upper() or "VOICE"
                card.tel.type_param = tag

        org = contact.get("organization", "")
        if org:
            card.add("org")
            card.org.value = [org]

        position = contact.get("position", "")
        if position:
            card.add("title")
            card.title.value = position

        address = contact.get("address", "")
        post_code = contact.get("post_code", "")
        if address or post_code:
            card.add("adr")
            card.adr.value = vobject.vcard.Address(
                street=address, city="", region="", code=post_code, country="",
                box="", extended="",
            )

        categories = contact.get("category", "")
        if categories:
            card.add("categories")
            card.categories.value = categories

        note = contact.get("notes", "")
        if note:
            card.add("note")
            card.note.value = note

        return card.serialize()

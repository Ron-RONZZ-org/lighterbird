"""VCF conversion utilities for ContactService."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any


def _vcard_to_contact(vcard: Any) -> dict[str, Any]:
    """Convert a vobject vCard to a contact dict."""
    import uuid
    from datetime import datetime

    now = datetime.now(UTC).isoformat()
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

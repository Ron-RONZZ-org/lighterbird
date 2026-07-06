"""Duplicate detection and merging for ContactService."""

from __future__ import annotations

import json as _json
from typing import Any


def _find_duplicate_groups(all_contacts: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Find groups of contacts that appear to be duplicates.

    Two-phase detection:
    1. **Email match** — contacts sharing the same email address.
    2. **Name + Org match** — contacts with the same ``(given_name,
       family_name, organization)`` combo (ignoring empty strings).

    Args:
        all_contacts: Full list of contact dicts, sorted by ``created_at``.

    Returns:
        List of groups, each being 2+ contacts sorted by created_at.
    """
    groups: list[list[dict[str, Any]]] = []
    seen_emails: dict[str, list[str]] = {}
    seen_name_org: dict[tuple[str, str, str], list[str]] = {}

    for c in all_contacts:
        uuid_ = c["uuid"]
        # Phase 1: Email match
        raw_emails = c.get("emails", "[]")
        if isinstance(raw_emails, str):
            raw_emails = _json.loads(raw_emails) if raw_emails else []
        for entry in raw_emails:
            addr = (entry.get("value") or "").strip().lower()
            if addr:
                seen_emails.setdefault(addr, []).append(uuid_)

        # Phase 2: Name + Org match
        given = (c.get("given_name") or "").strip().lower()
        family = (c.get("family_name") or "").strip().lower()
        org = (c.get("organization") or "").strip().lower()
        if given or family:
            key = (given, family, org)
            seen_name_org.setdefault(key, []).append(uuid_)

    # Build groups from email matches
    for addr, uuids in seen_emails.items():
        if len(uuids) > 1:
            group = [dict(c) for c in all_contacts if c["uuid"] in uuids]
            groups.append(group)

    # Build groups from name+org matches (avoiding duplicate groups)
    used: set[str] = set()
    for key, uuids in seen_name_org.items():
        if len(uuids) > 1:
            if not any(u in used for u in uuids):
                group = [dict(c) for c in all_contacts if c["uuid"] in uuids]
                groups.append(group)
                used.update(uuids)

    return groups


def _merge_contacts_data(
    keep: dict[str, Any],
    removals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge data from removal contacts into the keep contact.

    Combines unique emails, phones, and notes.  Does **not** perform any
    database operations — returns the updates dict to be applied by the caller.

    Args:
        keep: The contact dict to keep.
        removals: List of contact dicts to merge data from.

    Returns:
        Dict of field updates (``emails``, ``phones``, optionally ``notes``).
    """
    keep_emails: list[dict] = _json.loads(keep.get("emails", "[]") or "[]")
    keep_phones: list[dict] = _json.loads(keep.get("phones", "[]") or "[]")
    merged_notes: list[str] = []
    if keep.get("notes"):
        merged_notes.append(keep["notes"])

    for rem in removals:
        rem_emails: list[dict] = _json.loads(rem.get("emails", "[]") or "[]")
        rem_phones: list[dict] = _json.loads(rem.get("phones", "[]") or "[]")
        # Merge unique emails/phones
        seen = {e["value"] for e in keep_emails}
        for e in rem_emails:
            if e.get("value") not in seen:
                keep_emails.append(e)
                seen.add(e["value"])
        seen_p = {p["value"] for p in keep_phones}
        for p in rem_phones:
            if p.get("value") not in seen_p:
                keep_phones.append(p)
                seen_p.add(p["value"])
        if rem.get("notes"):
            merged_notes.append(rem["notes"])

    updates: dict[str, Any] = {
        "emails": _json.dumps(keep_emails, ensure_ascii=False),
        "phones": _json.dumps(keep_phones, ensure_ascii=False),
    }
    if merged_notes:
        updates["notes"] = "\n---\n".join(merged_notes)
    return updates

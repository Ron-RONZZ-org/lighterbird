"""Response normalization helpers for command handlers.

Translates raw DB records (Esperanto column names) into
English keys that the frontend popups expect.
"""

from __future__ import annotations

from typing import Any


def normalize_account(acct: dict[str, Any]) -> dict[str, Any]:
    """Translate raw kontoj record -> frontend-friendly dict."""
    return {
        "email": acct.get("retposto", ""),
        "name": acct.get("nomo", ""),
        "imap_server": acct.get("imap_servilo", ""),
        "smtp_server": acct.get("smtp_servilo", ""),
        "created_at": acct.get("kreita_je", ""),
    }


def normalize_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Translate raw mesagoj record -> frontend-friendly dict."""
    import json
    to_raw = msg.get("al", "[]")
    if isinstance(to_raw, str):
        try:
            to_list = json.loads(to_raw) if to_raw.strip() else []
        except (json.JSONDecodeError, TypeError):
            to_list = []
    else:
        to_list = to_raw or []
    return {
        "uuid": msg.get("uuid", ""),
        "account_email": msg.get("konto_id", ""),
        "from": msg.get("de", ""),
        "to": to_list,
        "subject": msg.get("subjekto", ""),
        "body": msg.get("korpo", ""),
        "html_body": msg.get("html_korpo", ""),
        "message_id": msg.get("message_id", ""),
        "in_reply_to": msg.get("in_reply_to", ""),
        "references": msg.get("references", ""),
        "is_read": bool(msg.get("legita", 0)),
        "received_at": msg.get("ricevita_je", ""),
        "created_at": msg.get("kreita_je", ""),
    }


def normalize_calendar(cal: dict[str, Any]) -> dict[str, Any]:
    """Translate raw kalendaroj record -> frontend-friendly dict."""
    return {
        "uuid": cal.get("uuid", ""),
        "url": cal.get("url", ""),
        "remote": bool(cal.get("remote", 1)),
    }


def normalize_event(evt: dict[str, Any]) -> dict[str, Any]:
    """Translate raw eventoj record -> frontend-friendly dict."""
    return {
        "uuid": evt.get("uuid", ""),
        "calendar_uuid": evt.get("kalendaro_uuid", ""),
        "title": evt.get("titolo", ""),
        "start": evt.get("komenco", ""),
        "end": evt.get("fino", ""),
        "location": evt.get("loko", ""),
        "description": evt.get("priskribo", ""),
        "category": evt.get("kategorio", ""),
    }


def normalize_contact(contact: dict[str, Any]) -> dict[str, Any]:
    """Translate raw kontaktoj record -> frontend-friendly dict."""
    return {
        "uuid": contact.get("uuid", ""),
        "name": contact.get("nomo", ""),
        "email": contact.get("retposto", ""),
        "phone": contact.get("telefonnumero", ""),
        "organization": contact.get("organizo", ""),
        "notes": contact.get("notoj", ""),
    }


def normalize_todo(todo: dict[str, Any]) -> dict[str, Any]:
    """Translate raw taskoj record -> frontend-friendly dict."""
    result = {
        "uuid": todo.get("uuid", ""),
        "title": todo.get("titolo", ""),
        "description": todo.get("priskribo", ""),
        "priority": todo.get("prioritato", 5),
        "status": todo.get("stato", "pending"),
        "due": todo.get("limdato", ""),
        "created_at": todo.get("kreita_je", ""),
        "parent_uuid": todo.get("parent_uuid", None),
        "sort_order": todo.get("sort_order", 0),
        "template_uuid": todo.get("shablono_uuid", None),
    }
    # Tree metadata from flatten_tree()
    if "_depth" in todo:
        result["_depth"] = todo["_depth"]
    if "_has_children" in todo:
        result["_has_children"] = todo["_has_children"]
    # Nested children from get_tree()
    if "children" in todo:
        result["children"] = [normalize_todo(c) for c in todo["children"]]
    return result


def normalize_journal_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Translate raw taglibro record -> frontend-friendly dict."""
    return {
        "uuid": entry.get("uuid", ""),
        "title": entry.get("titolo", ""),
        "text": entry.get("teksto", ""),
        "date": entry.get("dato", ""),
        "created_at": entry.get("kreita_je", ""),
    }

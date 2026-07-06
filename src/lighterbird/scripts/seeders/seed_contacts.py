"""Seed contacts.db with test contacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


def _seed_contacts(data_dir: Path) -> None:
    """Seed contacts.db with test contacts."""
    from lighterbird.contacts.db import get_db

    db_path = data_dir / "contacts.db"
    db = get_db(db_path)

    now = _now()
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    contact_toml_path = project_root / "test-contact.toml"

    # Contact 1: from test-contact.toml or default
    contact_data: dict[str, Any] = {
        "uuid": _gen_uuid(),
        "given_name": "Jane",
        "middle_names": "",
        "family_name": "Doe",
        "full_name": "Jane Doe",
        "emails": json.dumps([{"tag": "work", "value": "jane@test.com"}]),
        "phones": json.dumps([{"tag": "mobile", "value": "+1234567890"}]),
        "organization": "Test Corp",
        "position": "Engineer",
        "address": "123 Test St",
        "post_code": "12345",
        "date_of_birth": "1990-01-01",
        "place_of_birth": "Testville",
        "notes": "test contact 1",
        "category": "test",
        "custom_fields": "{}",
        "created_at": now,
        "updated_at": now,
    }

    if contact_toml_path.exists():
        try:
            import tomllib
            raw = tomllib.loads(contact_toml_path.read_text(encoding="utf-8"))
            if raw.get("first-name"):
                contact_data["given_name"] = raw["first-name"]
                contact_data["full_name"] = f"{raw['first-name']} {raw.get('last-name', '')}".strip()
            if raw.get("last-name"):
                contact_data["family_name"] = raw["last-name"]
            if raw.get("email"):
                contact_data["emails"] = json.dumps([{"tag": "work", "value": raw["email"]}])
            if raw.get("phone"):
                contact_data["phones"] = json.dumps([{"tag": "mobile", "value": raw["phone"]}])
            if raw.get("dob"):
                contact_data["date_of_birth"] = raw["dob"]
        except Exception:
            pass

    cols = list(contact_data.keys())
    vals = list(contact_data.values())
    placeholders = ", ".join("?" for _ in cols)
    db.execute(
        f"INSERT OR IGNORE INTO contacts ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(vals),
    )

    # Contact 2: second test email address
    contact_data2 = {
        "uuid": _gen_uuid(),
        "given_name": "Test",
        "middle_names": "",
        "family_name": "Account",
        "full_name": "Test Account",
        "emails": json.dumps([{"tag": "work", "value": "test@ronzz.org"}]),
        "phones": json.dumps([]),
        "organization": "",
        "position": "",
        "address": "",
        "post_code": "",
        "date_of_birth": "",
        "place_of_birth": "",
        "notes": "test contact 2 — second seeded account",
        "category": "test",
        "custom_fields": "{}",
        "created_at": now,
        "updated_at": now,
    }
    cols2 = list(contact_data2.keys())
    vals2 = list(contact_data2.values())
    db.execute(
        f"INSERT OR IGNORE INTO contacts ({', '.join(cols2)}) VALUES ({placeholders})",
        tuple(vals2),
    )

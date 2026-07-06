"""Seed profiles.db with a test user profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


def _seed_profiles(data_dir: Path) -> None:
    """Seed profiles.db with a test user profile."""
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)

    from lighterbird.profiles import db as profiles_db
    profiles_db.reset_db()

    db = profiles_db.get_db()

    now = _now()
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    profile_toml_path = project_root / "test-profile.toml"

    profile_data: dict[str, Any] = {
        "uuid": _gen_uuid(),
        "profile_name": "default",
        "given_name": "Test",
        "middle_names": "",
        "family_name": "User",
        "full_name": "Test User",
        "date_of_birth": "2000-01-01",
        "place_of_birth": "",
        "emails": "[]",
        "phones": "[]",
        "address": "",
        "post_code": "",
        "organization": "",
        "position": "",
        "custom_fields": "{}",
        "notes": "test profile 1 — from seed",
        "created_at": now,
        "updated_at": now,
    }

    if profile_toml_path.exists():
        try:
            import tomllib
            raw = tomllib.loads(profile_toml_path.read_text(encoding="utf-8"))
            if raw.get("profile-name"):
                profile_data["profile_name"] = raw["profile-name"]
            if raw.get("first-name"):
                profile_data["given_name"] = raw["first-name"]
            if raw.get("middle-names"):
                profile_data["middle_names"] = raw["middle-names"]
            if raw.get("last-name"):
                profile_data["family_name"] = raw["last-name"]
            fn = f"{profile_data['given_name']} {profile_data['middle_names']} {profile_data['family_name']}".replace("  ", " ").strip()
            if fn:
                profile_data["full_name"] = fn
            if raw.get("dob"):
                profile_data["date_of_birth"] = raw["dob"]
            if raw.get("email"):
                profile_data["emails"] = json.dumps([{"tag": "work", "value": raw["email"]}])
            if raw.get("phone"):
                profile_data["phones"] = json.dumps([{"tag": "mobile", "value": raw["phone"]}])
        except Exception:
            pass

    cols = list(profile_data.keys())
    vals = list(profile_data.values())
    placeholders = ", ".join("?" for _ in cols)
    db.execute(
        f"INSERT OR IGNORE INTO user_profiles ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(vals),
    )

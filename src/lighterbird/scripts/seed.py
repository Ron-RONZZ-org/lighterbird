"""Seed lighterbird databases with test data from ``.dev`` credentials.

Usage::

    from lighterbird.scripts.seed import seed_data_dir
    seed_data_dir("/tmp/lighterbird-test")

This creates all eight database files (email, calendar, contacts, todo,
journal, letters, profiles, user_commands) and populates them with
test accounts, contacts, entries, and configurations.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_dot_dev(dot_dev_path: str | Path | None) -> dict[str, str]:
    """Parse the ``.dev`` file into a dict of key→value."""
    result: dict[str, str] = {}
    if dot_dev_path is None:
        # Auto-discover from project root
        candidate = Path(__file__).resolve().parent.parent.parent.parent / ".dev"
        if not candidate.exists():
            return result
        dot_dev_path = candidate

    path = Path(dot_dev_path)
    if not path.exists():
        return result

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


# ── Domain seeders ──────────────────────────────────────────────────────────


def _seed_email(data_dir: Path, creds: dict[str, str]) -> None:
    """Seed email.db with a test account from .dev credentials."""
    from lighterbird.email.db import get_db, _SCHEMA_STATEMENTS

    db_path = data_dir / "email.db"
    db = get_db(db_path)
    # Schema is auto-initialized by get_db()

    email = creds.get("TEST_EMAIL_1", "test@example.com")
    password = creds.get("TEST_EMAIL_1_PASS", "")
    name = email.split("@")[0]

    # Detect IMAP/SMTP servers — import the detection function
    from lighterbird.email.server_detect import detect_servers
    try:
        detected = detect_servers(email)
    except Exception:
        detected = {"imap": f"imap.{email.split('@')[1]}", "smtp": f"smtp.{email.split('@')[1]}"}

    now = _now()
    db.execute(
        """INSERT OR IGNORE INTO accounts
           (email, sort_order, name, imap_server, imap_port, imap_use_ssl,
            smtp_server, smtp_port, smtp_use_tls,
            imap_username, smtp_username,
            managesieve_host, managesieve_port, managesieve_use_tls,
            signature, auth_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email,
            0,
            name,
            detected.get("imap", f"imap.{email.split('@')[1]}"),
            993,
            1,
            detected.get("smtp", f"smtp.{email.split('@')[1]}"),
            587,
            1,
            email,
            email,
            detected.get("managesieve_host", ""),
            detected.get("managesieve_port", 4190),
            1,
            "",
            "password",
            now,
            now,
        ),
    )

    # Store password in system keyring
    if password:
        from lighterbird.email.keyring import set_password
        set_password(email, password)

    # Create INBOX folder
    db.execute(
        "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (email, "INBOX", now, now),
    )
    db.execute(
        "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (email, "Sent", now, now),
    )


def _seed_calendar(data_dir: Path, creds: dict[str, str]) -> None:
    """Seed calendar.db with a test calendar from .dev credentials."""
    from lighterbird.calendar.db import get_db

    db_path = data_dir / "calendar.db"
    db = get_db(db_path)

    url = creds.get("TEST_CALENDAR_URL", "")
    username = creds.get("TEST_CALENDAR_USERNAME", "")
    password = creds.get("TEST_CALENDAR_PASSWORD", "")

    if not url:
        return  # No calendar to seed

    now = _now()
    cal_uuid = _gen_uuid()
    db.execute(
        """INSERT OR IGNORE INTO calendars (uuid, url, username, remote, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cal_uuid, url, username, 1, now, now),
    )

    # Store calendar password in keyring (pattern: lighterbird/calendar/{uuid}/password)
    if password:
        from lighterbird.core.keyring import set_password
        set_password(f"lighterbird/calendar/{cal_uuid}", "password", password)

    # Add a sample event
    from datetime import timedelta
    event_start = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    event_end = event_start + timedelta(hours=1)
    db.execute(
        """INSERT OR IGNORE INTO events
           (uuid, calendar_uuid, title, start, end, category, location, description, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _gen_uuid(),
            cal_uuid,
            "Test Event (from seed)",
            event_start.isoformat(),
            event_end.isoformat(),
            "meeting",
            "Office",
            "Auto-generated test event from seed script.",
            now,
            now,
        ),
    )


def _seed_contacts(data_dir: Path) -> None:
    """Seed contacts.db with a test contact."""
    from lighterbird.contacts.db import get_db

    db_path = data_dir / "contacts.db"
    db = get_db(db_path)

    now = _now()

    # Try to import contact from test-contact.toml if it exists
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    contact_toml_path = project_root / "test-contact.toml"

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
        "notes": "Test contact from seed.",
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
            pass  # Fall back to default

    cols = list(contact_data.keys())
    vals = list(contact_data.values())
    placeholders = ", ".join("?" for _ in cols)
    db.execute(
        f"INSERT OR IGNORE INTO contacts ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(vals),
    )


def _seed_todo(data_dir: Path) -> None:
    """Seed todo.db with sample tasks."""
    from lighterbird.todo.db import get_db

    db_path = data_dir / "todo.db"
    db = get_db(db_path)

    now = _now()
    tasks = [
        {
            "uuid": _gen_uuid(),
            "title": "Buy milk",
            "description": "Get 2% milk from the grocery store",
            "priority": "3",
            "status": "pending",
            "due_date": None,
            "sort_order": 0,
            "created_at": now,
            "updated_at": now,
        },
        {
            "uuid": _gen_uuid(),
            "title": "Review PR #42",
            "description": "Code review for the new API endpoint",
            "priority": "1",
            "status": "pending",
            "due_date": None,
            "sort_order": 1,
            "created_at": now,
            "updated_at": now,
        },
        {
            "uuid": _gen_uuid(),
            "title": "Write documentation",
            "description": "Document the new CLI commands",
            "priority": "5",
            "status": "completed",
            "due_date": None,
            "sort_order": 2,
            "created_at": now,
            "updated_at": now,
        },
    ]

    for t in tasks:
        cols = list(t.keys())
        vals = list(t.values())
        placeholders = ", ".join("?" for _ in cols)
        db.execute(
            f"INSERT OR IGNORE INTO tasks ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(vals),
        )


def _seed_journal(data_dir: Path) -> None:
    """Seed journal.db with a sample journal entry."""
    from lighterbird.journal.db import get_db

    db_path = data_dir / "journal.db"
    db = get_db(db_path)

    now = _now()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db.execute(
        """INSERT OR IGNORE INTO journal
           (uuid, title, text, date, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            _gen_uuid(),
            "First Entry",
            "This is a test journal entry created by the seed script.",
            today,
            now,
            now,
        ),
    )


def _seed_letters(data_dir: Path) -> None:
    """Seed letters.db with a sample letter."""
    from lighterbird.letter.db import get_db

    db_path = data_dir / "letters.db"
    db = get_db(db_path)

    now = _now()
    db.execute(
        """INSERT OR IGNORE INTO letters
           (uuid, direction, object, body_path, body_format,
            sender_profile, sender_manual, recipient_contact, recipient_manual,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _gen_uuid(),
            "sent",
            "Test Letter",
            "",
            "html",
            None,
            "sender@test.com",
            None,
            "recipient@test.com",
            now,
            now,
        ),
    )


def _seed_profiles(data_dir: Path) -> None:
    """Seed profiles.db with a test user profile."""
    # profiles/db.py computes _DB_PATH at module level from data_dir().
    # We set the env var, then reset the singleton before calling get_db().
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)

    # Reset the singleton so get_db() reinitializes from the new path
    from lighterbird.profiles import db as profiles_db
    profiles_db.reset_db()

    db = profiles_db.get_db()

    now = _now()

    # Try to load from test-profile.toml
    project_root = Path(__file__).resolve().parent.parent.parent.parent
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
        "notes": "Auto-generated test profile.",
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


def _seed_user_commands(data_dir: Path) -> None:
    """Seed user_commands.db is intentionally left empty for seed."""
    # user_commands/db.py computes _DB_PATH at module level from data_dir().
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)

    from lighterbird.user_commands import db as uc_db
    uc_db.reset_db()
    uc_db.get_db()


def _seed_llm_config(creds: dict[str, str]) -> None:
    """Configure the LLM provider from .dev credentials if not already set."""
    from lighterbird.core.keyring import get_password, set_password

    api_key = creds.get("TEST_DEEPSEEK_APIKEY", "")
    if not api_key:
        return

    # Check if already configured
    configured = get_password("lighterbird-llm", "active-provider")
    if configured:
        return

    config = {
        "provider_type": "openai",
        "api_key": api_key,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    set_password("lighterbird-llm", "active-provider", json.dumps(config))


def _seed_backup_config(data_dir: Path) -> None:
    """Create a basic backup config so backup commands don't error."""
    from lighterbird.core.backup import save_config, BackupStrategy
    from dataclasses import asdict

    strategy = BackupStrategy(
        id="default",
        label="Default",
        interval_minutes=0,
        max_copies=10,
        target="local",
        enabled=True,
    )
    save_config({"version": 3, "strategies": [asdict(strategy)]})


# ── Public API ──────────────────────────────────────────────────────────────


def seed_data_dir(
    target_dir: str | Path,
    dot_dev_path: str | Path | None = None,
) -> None:
    """Initialize and populate all lighterbird databases in *target_dir*.

    Creates eight database files (email, calendar, contacts, todo, journal,
    letters, profiles, user_commands) with schemas initialized and minimal
    seed data inserted.

    Passwords for the test email account are stored in the system keyring.
    The LLM provider is auto-configured from ``.dev`` if not already set.

    Args:
        target_dir: Directory to create database files in (created if missing).
        dot_dev_path: Path to the ``.dev`` file with test credentials.
            If ``None``, auto-discovers from the project root.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    creds = _parse_dot_dev(dot_dev_path)

    # Set env so singletons (profiles, user_commands) resolve correctly
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(target)
    os.environ["LIGHTERBIRD_CONFIG_DIR"] = str(target / "config")

    _seed_email(target, creds)
    _seed_calendar(target, creds)
    _seed_contacts(target)
    _seed_todo(target)
    _seed_journal(target)
    _seed_letters(target)
    _seed_profiles(target)
    _seed_user_commands(target)
    _seed_llm_config(creds)
    _seed_backup_config(target)

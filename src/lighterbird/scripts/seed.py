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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _parse_dot_dev(dot_dev_path: str | Path | None) -> dict[str, str]:
    """Parse the ``.dev`` file into a dict of key→value."""
    result: dict[str, str] = {}
    if dot_dev_path is None:
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


def _ts(days_ago: int = 0, hours_ago: int = 0) -> str:
    """Return an ISO timestamp offset from now."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return dt.isoformat()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


# ── Helpers ─────────────────────────────────────────────────────────────────


def _create_account(db, email: str, password: str, sort_order: int,
                    creds: dict[str, str], now: str) -> None:
    """Insert a single email account and its folders."""
    from lighterbird.email.server_detect import detect_servers

    name = email.split("@")[0]
    try:
        detected = detect_servers(email)
    except Exception:
        detected = {"imap": f"imap.{email.split('@')[1]}", "smtp": f"smtp.{email.split('@')[1]}"}

    domain = email.split("@")[1]
    db.execute(
        """INSERT OR IGNORE INTO accounts
           (email, sort_order, name, imap_server, imap_port, imap_use_ssl,
            smtp_server, smtp_port, smtp_use_tls,
            imap_username, smtp_username,
            managesieve_host, managesieve_port, managesieve_use_tls,
            signature, auth_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email, sort_order, name,
            detected.get("imap", f"imap.{domain}"), 993, 1,
            detected.get("smtp", f"smtp.{domain}"), 587, 1,
            email, email,
            detected.get("managesieve_host", ""),
            detected.get("managesieve_port", 4190), 1,
            "", "password", now, now,
        ),
    )

    if password:
        from lighterbird.email.keyring import set_password
        set_password(email, password)

    for folder in ("INBOX", "Sent"):
        db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (email, folder, now, now),
        )


# ── Domain seeders ──────────────────────────────────────────────────────────


def _seed_email(data_dir: Path, creds: dict[str, str]) -> None:
    """Seed email.db with both test accounts from .dev credentials."""
    from lighterbird.email.db import get_db

    db_path = data_dir / "email.db"
    db = get_db(db_path)

    now = _now()

    # ── Account 1 ────────────────────────────────────────────────────────
    email1 = creds.get("TEST_EMAIL_1", "test1@example.com")
    pw1 = creds.get("TEST_EMAIL_1_PASS", "")
    _create_account(db, email1, pw1, 0, creds, now)

    # ── Account 2 ────────────────────────────────────────────────────────
    email2 = creds.get("TEST_EMAIL_2", "test2@example.com")
    pw2 = creds.get("TEST_EMAIL_2_PASS", "")
    _create_account(db, email2, pw2, 1, creds, now)

    # ── Sample messages ──────────────────────────────────────────────────
    _seed_email_messages(db, email1, email2, now)


def _seed_email_messages(db, email1: str, email2: str, now: str) -> None:
    """Create a conversation thread between the two seeded accounts.

    Thread::

        1. email1 → email2              (original, subject: "test email 1")
        2. email2 → email1              (reply,   subject: "Re: test email 1")
        3. email1 → third@party.com     (forward, subject: "Fwd: test email 1",
                   cc: email2                     body quotes original)
        4. email2 → email1              (reply-all, subject: "Re: Fwd: test email 1",
                   cc: third@party.com             references previous)
    """
    domain1 = email1.split("@")[1]
    domain2 = email2.split("@")[1]

    # Message 1: original from email1 → email2
    msg1_uuid = _gen_uuid()
    msg1_id = "<test-001@" + domain1 + ">"
    db.execute(
        """INSERT OR IGNORE INTO messages
           (uuid, account_email, folder_name, message_id, in_reply_to,
            from_addr, to_recipients, cc_recipients,
            subject, body, html_body, priority, is_read,
            received_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg1_uuid, email1, "INBOX", msg1_id, "",
            email1, json.dumps([email2]), json.dumps([]),
            "test email 1", "this is the 1st test email", "", 5, 1,
            _ts(days_ago=5), now, now,
        ),
    )

    # Message 2: reply from email2 → email1
    msg2_uuid = _gen_uuid()
    msg2_id = "<test-002@" + domain2 + ">"
    db.execute(
        """INSERT OR IGNORE INTO messages
           (uuid, account_email, folder_name, message_id, in_reply_to,
            from_addr, to_recipients, cc_recipients,
            subject, body, html_body, priority, is_read,
            received_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg2_uuid, email2, "INBOX", msg2_id, msg1_id,
            email2, json.dumps([email1]), json.dumps([]),
            "Re: test email 1", "this is the 2nd test email — reply to test email 1", "", 5, 0,
            _ts(days_ago=4, hours_ago=12), now, now,
        ),
    )

    # Message 3: email1 forwards msg1 to third@party.com, cc email2
    msg3_uuid = _gen_uuid()
    msg3_id = "<test-003@" + domain1 + ">"
    third_party = "third@party.com"
    forwarded_body = (
        "this is the 3rd test email — forward of test email 1\n\n"
        "---------- Forwarded message ---------\n"
        f"From: {email1}\n"
        f"Subject: test email 1\n"
        f"Date: {_ts(days_ago=5)}\n\n"
        "this is the 1st test email"
    )
    db.execute(
        """INSERT OR IGNORE INTO messages
           (uuid, account_email, folder_name, message_id, in_reply_to,
            from_addr, to_recipients, cc_recipients,
            subject, body, html_body, priority, is_read,
            received_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg3_uuid, email1, "INBOX", msg3_id, "",
            email1, json.dumps([third_party]), json.dumps([email2]),
            "Fwd: test email 1", forwarded_body, "", 5, 1,
            _ts(days_ago=3), now, now,
        ),
    )

    # Message 4: reply-all from email2 → email1 + third@party.com (cc)
    msg4_uuid = _gen_uuid()
    msg4_id = "<test-004@" + domain2 + ">"
    db.execute(
        """INSERT OR IGNORE INTO messages
           (uuid, account_email, folder_name, message_id, in_reply_to,
            from_addr, to_recipients, cc_recipients,
            subject, body, html_body, priority, is_read,
            received_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg4_uuid, email2, "INBOX", msg4_id, msg3_id,
            email2, json.dumps([email1, third_party]), json.dumps([]),
            "Re: Fwd: test email 1",
            "this is the 4th test email — reply-all to forward", "", 5, 0,
            _ts(days_ago=2, hours_ago=6), now, now,
        ),
    )


def _seed_calendar(data_dir: Path, creds: dict[str, str]) -> None:
    """Seed calendar.db with a test calendar from .dev credentials + filler events."""
    from lighterbird.calendar.db import get_db

    db_path = data_dir / "calendar.db"
    db = get_db(db_path)

    url = creds.get("TEST_CALENDAR_URL", "")
    username = creds.get("TEST_CALENDAR_USERNAME", "")
    password = creds.get("TEST_CALENDAR_PASSWORD", "")

    if not url:
        return

    now = _now()
    cal_uuid = _gen_uuid()
    db.execute(
        """INSERT OR IGNORE INTO calendars (uuid, url, username, remote, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cal_uuid, url, username, 1, now, now),
    )

    if password:
        from lighterbird.core.keyring import set_password
        set_password(f"lighterbird/calendar/{cal_uuid}", "password", password)

    # Filler events
    base = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    for i in range(3):
        start = base + timedelta(days=1 + i)
        end = start + timedelta(hours=1)
        db.execute(
            """INSERT OR IGNORE INTO events
               (uuid, calendar_uuid, title, start, end, category, location, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _gen_uuid(), cal_uuid,
                f"test event {i+1}",
                start.isoformat(), end.isoformat(),
                "meeting", "Office",
                f"this is the {i+1}{'st' if i==0 else 'nd' if i==1 else 'rd'} test event",
                now, now,
            ),
        )


def _seed_contacts(data_dir: Path) -> None:
    """Seed contacts.db with test contacts."""
    from lighterbird.contacts.db import get_db

    db_path = data_dir / "contacts.db"
    db = get_db(db_path)

    now = _now()
    project_root = Path(__file__).resolve().parent.parent.parent.parent
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


def _seed_todo(data_dir: Path) -> None:
    """Seed todo.db with filler tasks."""
    from lighterbird.todo.db import get_db

    db_path = data_dir / "todo.db"
    db = get_db(db_path)

    now = _now()
    tasks = [
        {
            "uuid": _gen_uuid(),
            "title": f"test todo {i+1}",
            "description": f"this is the {i+1}{'st' if i==0 else 'nd' if i==1 else 'rd'} test todo",
            "priority": str(5 - i if i < 5 else i - 3),
            "status": status,
            "due_date": None,
            "sort_order": i,
            "created_at": now,
            "updated_at": now,
        }
        for i, status in enumerate(["pending", "pending", "completed", "pending", "pending"])
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
    """Seed journal.db with filler entries."""
    from lighterbird.journal.db import get_db

    db_path = data_dir / "journal.db"
    db = get_db(db_path)

    now = _now()

    for i in range(3):
        day = datetime.now(timezone.utc) - timedelta(days=2 - i)
        db.execute(
            """INSERT OR IGNORE INTO journal
               (uuid, title, text, date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                _gen_uuid(),
                f"test journal entry {i+1}",
                f"this is the {i+1}{'st' if i==0 else 'nd' if i==1 else 'rd'} test journal entry",
                day.strftime("%Y-%m-%d"),
                now, now,
            ),
        )


def _seed_letters(data_dir: Path) -> None:
    """Seed letters.db with a real cover letter example."""
    from lighterbird.letter.db import get_db

    db_path = data_dir / "letters.db"
    db = get_db(db_path)

    now = _now()

    # Try to load a real cover letter from ronCV project
    cover_letter_path = Path("/home/rongzhou/kodo/ronCV/lettre-de-motivation/DVUC-001-3/DVUC-001-3.md")
    body = ""
    if cover_letter_path.exists():
        try:
            body = cover_letter_path.read_text(encoding="utf-8")
        except Exception:
            body = ""
    if not body:
        body = "this is the 1st test letter"

    db.execute(
        """INSERT OR IGNORE INTO letters
           (uuid, direction, object, body_path, body_format,
            sender_profile, sender_manual, recipient_contact, recipient_manual,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _gen_uuid(),
            "sent",
            "Candidature DVUC-001-3",
            "",
            "markdown",
            None,
            "rong.zhou6@etu.univ-lorraine.fr",
            None,
            "Naomie JACQ <naomie.jacq@univ-lorraine.fr>",
            now,
            now,
        ),
    )


def _seed_profiles(data_dir: Path) -> None:
    """Seed profiles.db with a test user profile."""
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)

    from lighterbird.profiles import db as profiles_db
    profiles_db.reset_db()

    db = profiles_db.get_db()

    now = _now()
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


def _seed_user_commands(data_dir: Path) -> None:
    """Seed user_commands.db is intentionally left empty for seed."""
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
    letters, profiles, user_commands) with schemas initialized and seed
    data inserted.

    Passwords for test accounts are stored in the system keyring.
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


def seed_test_seed_7z(output_path: str | Path) -> Path:
    """Generate a test-seed.7z archive from .dev credentials.

    Uses a temporary directory to generate all seed data, then creates a
    7z archive containing the databases.  Cleans up the temp dir.
    """
    import shutil
    import tempfile

    from lighterbird.core.backup import BackupStrategy
    from lighterbird.core.backup import _create_strategy_archive as _create_archive
    from dataclasses import asdict

    tmp = Path(tempfile.mkdtemp(prefix="lighterbird-seed-"))
    data_tmp = tmp / "data"
    config_tmp = tmp / "config"
    data_tmp.mkdir(parents=True, exist_ok=True)
    config_tmp.mkdir(parents=True, exist_ok=True)

    try:
        seed_data_dir(data_tmp)
        strategy = asdict(BackupStrategy(id="default", label="Default"))
        archive = _create_archive(strategy)
        if archive:
            dst = Path(output_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(archive), str(dst))
            return dst
        raise RuntimeError("Seed archive creation returned None")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

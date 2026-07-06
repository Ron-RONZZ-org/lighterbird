"""Seed calendar.db with a test calendar from .dev credentials + filler events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


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
    base = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
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

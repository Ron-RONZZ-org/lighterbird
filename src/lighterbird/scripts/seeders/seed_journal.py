"""Seed journal.db with filler entries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


def _seed_journal(data_dir: Path) -> None:
    """Seed journal.db with filler entries."""
    from lighterbird.journal.db import get_db

    db_path = data_dir / "journal.db"
    db = get_db(db_path)

    now = _now()

    for i in range(3):
        day = datetime.now(UTC) - timedelta(days=2 - i)
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

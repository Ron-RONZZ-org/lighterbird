"""Seed todo.db with filler tasks."""

from __future__ import annotations

from pathlib import Path

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


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

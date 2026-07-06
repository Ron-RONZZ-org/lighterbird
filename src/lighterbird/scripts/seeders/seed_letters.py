"""Seed letters.db with a real cover letter example."""

from __future__ import annotations

import os
from pathlib import Path

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


def _seed_letters(data_dir: Path) -> None:
    """Seed letters.db with a real cover letter example."""
    from lighterbird.letter.db import get_db

    db_path = data_dir / "letters.db"
    db = get_db(db_path)

    now = _now()

    # Try to load a real cover letter from env-optional path,
    # fall back to a simple example.
    cover_letter_path = Path(os.environ.get("COVER_LETTER_PATH", ""))
    body = ""
    if cover_letter_path.is_file():
        try:
            body = cover_letter_path.read_text(encoding="utf-8")
        except Exception:
            body = ""
    if not body:
        body = "this is the 1st test letter"

    letter_uuid = _gen_uuid()
    db.execute(
        """INSERT OR IGNORE INTO letters
           (uuid, direction, object, body_path, body_format,
            sender_profile, sender_manual, recipient_contact, recipient_manual,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            letter_uuid,
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

    # Store the body content so it's available for viewing/export/print
    if body:
        from lighterbird.letter.services.letters import LetterService
        svc = LetterService(db)
        html_body = svc.convert_to_html(body, "markdown")
        svc.store_body(letter_uuid, html_body)

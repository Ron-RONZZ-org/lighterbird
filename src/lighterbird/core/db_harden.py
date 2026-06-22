"""DB hardening utilities — health check, repair, backup, recovery.

Forked from A-core's ``A.data.harden``.
"""

from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path


def backup_db(db_path: Path) -> None:
    """Snapshot *db_path* to ``<name>.bak`` before schema-altering operations.

    Best-effort: silently ignores missing files and copy failures.
    """
    if not db_path.exists():
        return
    bak = db_path.with_suffix(".db.bak")
    try:
        shutil.copy2(str(db_path), str(bak))
    except Exception:
        pass


def health_check(db_path: Path) -> bool:
    """Run ``PRAGMA quick_check`` on *db_path* via a read-only connection.

    Returns ``True`` if the database is healthy, ``False`` otherwise.
    """
    if not db_path.exists():
        return True
    try:
        conn = sqlite3.connect(f"file:{str(db_path)}?mode=ro", uri=True, timeout=5)
        (result,) = conn.execute("PRAGMA quick_check").fetchone()
        conn.close()
        return result == "ok"
    except Exception:
        return False


def repair_db(db_path: Path) -> bool:
    """Attempt to repair a corrupted database at *db_path*.

    Returns ``True`` if the DB is healthy after repair.
    """
    if not db_path.exists():
        return True
    for suffix in ("-wal", "-shm"):
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        (result,) = conn.execute("PRAGMA quick_check").fetchone()
        if result == "ok":
            conn.close()
            return True
        try:
            conn.execute("VACUUM")
            conn.execute("REINDEX")
            (result,) = conn.execute("PRAGMA quick_check").fetchone()
            if result == "ok":
                conn.close()
                return True
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return False


def open_healthy_db(path: Path, *, backup: bool = False):
    """Open a database with health verification.

    Args:
        path: Full path to the database file.
        backup: If True, create a rolling ``.bak`` copy after opening.

    Returns:
        A ready-to-use ``LighterbirdDB`` instance.
    """
    from lighterbird.core.db import LighterbirdDB

    db = LighterbirdDB(path)
    if backup:
        backup_db(path)
    return db


def init_db(
    path: Path,
    schema_sql: str | list[str],
    *,
    backup: bool = True,
) -> "LighterbirdDB":
    """Create or open a database with schema initialization.

    Args:
        path: Full path to the database file.
        schema_sql: ``CREATE TABLE`` statements (single string or list).
        backup: If True, snapshot the DB before any DDL.

    Returns:
        A ready-to-use ``LighterbirdDB`` instance.
    """
    from lighterbird.core.db import LighterbirdDB

    if backup:
        backup_db(path)

    db = LighterbirdDB(path)
    statements = [schema_sql] if isinstance(schema_sql, str) else schema_sql
    for stmt in statements:
        s = stmt.strip()
        if s:
            db.execute(s)
    return db

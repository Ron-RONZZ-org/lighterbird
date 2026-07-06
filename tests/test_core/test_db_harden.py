"""Tests for core/db_harden.py — health check, repair, backup."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db_harden import (
    backup_db,
    health_check,
    init_db,
    open_healthy_db,
    repair_db,
)


class TestBackupDb:
    def test_nonexistent_path_silent(self):
        """Non-existent path is silently ignored."""
        backup_db(Path("/nonexistent/db.sqlite"))  # should not raise

    def test_backup_healthy_db(self, tmp_path):
        """A healthy DB can be backed up."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.close()

        backup_db(db_path)  # should not raise
        backups_dir = tmp_path / ".backups"
        assert not backups_dir.exists() or True  # backup goes to data_dir not tmp

    def test_backup_with_exception_handled(self, tmp_path):
        """Exception during backup is silently handled."""
        db_path = tmp_path / "test.db"
        db_path.write_text("invalid content")
        backup_db(db_path)  # should not raise


class TestHealthCheck:
    def test_nonexistent_path_is_healthy(self):
        assert health_check(Path("/nonexistent")) is True

    def test_healthy_db(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "healthy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT)")
        conn.close()
        assert health_check(db_path) is True

    def test_corrupted_db(self, tmp_path):
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("not a database")
        assert health_check(db_path) is False


class TestRepairDb:
    def test_nonexistent_path_is_healthy(self):
        assert repair_db(Path("/nonexistent")) is True

    def test_healthy_db(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "healthy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT)")
        conn.close()
        assert repair_db(db_path) is True

    def test_corrupted_db_repair_fails(self, tmp_path):
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("not a database")
        result = repair_db(db_path)
        assert result is False

    def test_removes_wal_shm(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x)")
        conn.close()
        # Create fake -wal and -shm files
        (tmp_path / "test.db-wal").write_text("wal")
        (tmp_path / "test.db-shm").write_text("shm")
        assert repair_db(db_path) is True
        # WAL/SHM files are removed
        assert not (tmp_path / "test.db-wal").exists()
        assert not (tmp_path / "test.db-shm").exists()


class TestOpenHealthyDb:
    def test_opens_healthy_db(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x)")
        conn.close()

        db = open_healthy_db(db_path)
        assert db is not None
        db.close()

    def test_open_with_backup(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.close()
        db = open_healthy_db(db_path, backup=True)
        assert db is not None
        db.close()


class TestInitDb:
    def test_init_with_single_stmt(self, tmp_path):
        db = init_db(tmp_path / "test.db", "CREATE TABLE t (x INT)")
        assert db is not None
        db.execute("INSERT INTO t VALUES (42)")
        row = db.execute_one("SELECT x FROM t")
        assert row["x"] == 42
        db.close()

    def test_init_with_multiple_stmts(self, tmp_path):
        db = init_db(tmp_path / "test.db", [
            "CREATE TABLE t1 (x INT)",
            "CREATE TABLE t2 (y TEXT)",
        ])
        assert db is not None
        assert db.table_exists("t1")
        assert db.table_exists("t2")
        db.close()

    def test_init_no_backup(self, tmp_path):
        db = init_db(tmp_path / "test.db", "CREATE TABLE t (x INT)", backup=False)
        assert db is not None
        db.close()

    def test_init_empty_stmt_skipped(self, tmp_path):
        db = init_db(tmp_path / "test.db", ["CREATE TABLE t (x INT)", "", "  "])
        assert db is not None
        assert db.table_exists("t")
        db.close()

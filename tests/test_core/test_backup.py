"""Tests for lighterbird.core.backup — timestamped backups, export/import, config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lighterbird.core.backup import (
    _known_db_paths,
    _sha256,
    backup_all,
    backup_database,
    backup_config_files,
    copy_to_external,
    export_data,
    import_data,
    list_backups,
    list_backups_for,
    load_config,
    prune_backups,
    restore_latest,
    save_config,
)


class TestBackupDatabase:
    def test_backup_nonexistent_file(self):
        """backup_database returns None for missing files."""
        result = backup_database(Path("/nonexistent/path.db"))
        assert result is None

    def test_backup_creates_file(self, tmp_data_dir: Path, tmp_path: Path):
        """backup_database creates a timestamped copy in .backups/."""
        db_path = tmp_path / "test.db"
        db_path.write_text("hello")
        result = backup_database(db_path, retention=0)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".db"
        # parent dir should be under tmp_data_dir /.backups
        assert ".backups" in str(result.parent)

    def test_backup_checksum_verified(self, tmp_data_dir: Path, tmp_path: Path):
        """Backup content matches source (SHA-256 verified)."""
        db_path = tmp_path / "verify.db"
        db_path.write_text("some data here 123")
        orig_hash = _sha256(db_path)
        result = backup_database(db_path, retention=0)
        assert result is not None
        assert _sha256(result) == orig_hash

    def test_backup_timestamp_in_filename(self, tmp_data_dir: Path, tmp_path: Path):
        """Filename contains stem + timestamp."""
        db_path = tmp_path / "email.db"
        db_path.write_text("data")
        result = backup_database(db_path, retention=0)
        assert result is not None
        assert result.name.startswith("email_")
        assert "T" in result.stem  # ISO timestamp separator

    def test_backup_adds_to_list(self, tmp_data_dir: Path, tmp_path: Path):
        """After backup, list_backups returns the new file."""
        db_path = tmp_path / "calendar.db"
        db_path.write_text("data")
        assert len(list_backups()) == 0
        backup_database(db_path, retention=0)
        assert len(list_backups()) >= 1


class TestBackupAll:
    def test_backup_all_no_dbs(self, tmp_data_dir: Path):
        """backup_all returns empty list when no DBs exist."""
        assert backup_all() == []

    def test_backup_all_with_dbs(self, tmp_data_dir: Path, tmp_path: Path):
        """backup_all backs up all known DB paths that exist."""
        # Create "real" DB files in the data dir pointed to by tmp_data_dir
        for name in ["email.db", "todo.db"]:
            (tmp_data_dir / name).write_text(f"{name} content")
        results = backup_all(retention=0)
        assert len(results) == 2
        names = [p.name for p in results]
        assert any("email_" in n for n in names)
        assert any("todo_" in n for n in names)


class TestListBackups:
    def test_list_empty(self, tmp_data_dir: Path):
        """list_backups returns [] when no backups exist."""
        assert list_backups() == []

    def test_list_after_backup(self, tmp_data_dir: Path, tmp_path: Path):
        """list_backups returns backup metadata dicts."""
        db_path = tmp_path / "journal.db"
        db_path.write_text("data")
        backup_database(db_path, retention=0)
        backups = list_backups()
        assert len(backups) >= 1
        entry = backups[0]
        assert "path" in entry
        assert "timestamp" in entry
        assert "size_bytes" in entry
        assert "stem" in entry
        assert entry["size_bytes"] > 0
        assert entry["stem"] == "journal"

    def test_list_for_stem(self, tmp_data_dir: Path, tmp_path: Path):
        """list_backups_for filters by stem."""
        db_path = tmp_path / "email.db"
        db_path.write_text("data")
        backup_database(db_path, retention=0)
        email_backups = list_backups_for("email")
        assert len(email_backups) == 1
        cal_backups = list_backups_for("calendar")
        assert len(cal_backups) == 0

    def test_list_newest_first(self, tmp_data_dir: Path, tmp_path: Path):
        """list_backups returns newest-first order."""
        db_path = tmp_path / "test.db"
        db_path.write_text("v1")
        backup_database(db_path, retention=0)
        db_path.write_text("v2")
        backup_database(db_path, retention=0)
        backups = list_backups()
        # The most recent should be first
        assert len(backups) >= 2
        ts_values = [b["timestamp"] for b in backups]
        assert ts_values == sorted(ts_values, reverse=True)


class TestPrune:
    def test_prune_retains_n(self, tmp_data_dir: Path, tmp_path: Path):
        """prune_backups keeps only the N newest."""
        db_path = tmp_path / "prune.db"
        for i in range(5):
            db_path.write_text(f"version-{i}")
            backup_database(db_path, retention=0)
        assert len(list_backups()) == 5
        deleted = prune_backups(retention=2)
        assert deleted == 3
        assert len(list_backups()) == 2

    def test_prune_invalid_retention(self):
        """prune_backups with retention < 1 raises ValueError."""
        with pytest.raises(ValueError, match="retention must be >= 1"):
            prune_backups(retention=0)

    def test_prune_empty_dir(self, tmp_data_dir: Path):
        """prune_backups on empty backup dir returns 0."""
        assert prune_backups(retention=5) == 0


class TestRestoreLatest:
    def test_restore_latest(self, tmp_data_dir: Path, tmp_path: Path):
        """restore_latest restores the latest backup to target dir."""
        db_path = tmp_data_dir / "email.db"
        db_path.write_text("content")
        backup_database(db_path, retention=0)
        db_path.unlink()
        restored = restore_latest(str(tmp_data_dir))
        assert len(restored) >= 1
        assert (tmp_data_dir / "email.db").exists()
        assert (tmp_data_dir / "email.db").read_text() == "content"

    def test_restore_no_backups(self, tmp_data_dir: Path):
        """restore_latest raises FileNotFoundError if no backups."""
        with pytest.raises(FileNotFoundError, match="No backups found"):
            restore_latest(str(tmp_data_dir))


class TestCopyToExternal:
    def test_copy_to_external(self, tmp_data_dir: Path, tmp_path: Path):
        """copy_to_external copies backup files to external dir."""
        db_path = tmp_path / "ext.db"
        db_path.write_text("data")
        result = backup_database(db_path, retention=0)
        assert result is not None
        ext_dir = tmp_path / "external"
        copied = copy_to_external(str(ext_dir), backup_paths=[result])
        assert len(copied) == 1
        assert copied[0].exists()
        assert copied[0].read_text() == "data"

    def test_copy_creates_target_dir(self, tmp_data_dir: Path, tmp_path: Path):
        """copy_to_external creates the target directory if missing."""
        db_path = tmp_path / "ext2.db"
        db_path.write_text("data")
        result = backup_database(db_path, retention=0)
        assert result is not None
        ext_dir = tmp_path / "nested" / "dir" / "backups"
        copied = copy_to_external(str(ext_dir), backup_paths=[result])
        assert copied[0].parent.exists()


class TestBackupConfig:
    def test_load_default_config(self, tmp_data_dir: Path, monkeypatch):
        """load_config returns defaults when no config file exists."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        cfg = load_config()
        assert cfg["external_dir"] == ""
        assert cfg["retention"] == 10
        assert cfg["auto_interval_minutes"] == 0

    def test_save_and_load(self, tmp_data_dir: Path, monkeypatch):
        """save_config persists and load_config retrieves."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        cfg = {"external_dir": "/some/path", "retention": 5, "auto_interval_minutes": 30}
        save_config(cfg)
        loaded = load_config()
        assert loaded["external_dir"] == "/some/path"
        assert loaded["retention"] == 5
        assert loaded["auto_interval_minutes"] == 30

    def test_save_config_rejects_unknown_keys(self, tmp_data_dir: Path, monkeypatch):
        """save_config raises ValueError on unknown keys."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        with pytest.raises(ValueError, match="Unknown backup config key"):
            save_config({"external_dir": "/x", "bogus": "y"})

    def test_save_config_rejects_wrong_type(self, tmp_data_dir: Path, monkeypatch):
        """save_config raises ValueError on wrong value type."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        with pytest.raises(ValueError, match="must be int"):
            save_config({"retention": "not-a-number"})

    def test_load_config_sanitizes_corrupt_json(self, tmp_data_dir: Path, monkeypatch):
        """load_config returns defaults on corrupt JSON."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        cfg_path = tmp_data_dir / "backup.json"
        cfg_path.write_text("{invalid json}", encoding="utf-8")
        cfg = load_config()
        assert cfg["external_dir"] == ""
        assert cfg["retention"] == 10
        assert cfg["auto_interval_minutes"] == 0

    def test_load_config_strips_unknown_keys(self, tmp_data_dir: Path, monkeypatch):
        """load_config strips unknown keys and fills defaults."""
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
        cfg_path = tmp_data_dir / "backup.json"
        cfg_path.write_text(
            json.dumps({"external_dir": "/path", "nonsense": 42, "retention": 3}),
            encoding="utf-8",
        )
        cfg = load_config()
        assert "nonsense" not in cfg
        assert cfg["external_dir"] == "/path"
        assert cfg["retention"] == 3
        assert cfg["auto_interval_minutes"] == 0  # default filled


class TestExportImport:
    def test_export_creates_directory(self, tmp_data_dir: Path, tmp_path: Path):
        """export_data creates a timestamped export dir with manifest."""
        # Create a couple of real DB files
        for name in ["email.db", "todo.db"]:
            (tmp_data_dir / name).write_text(f"{name} data")
        export_dir = export_data(str(tmp_path))
        assert export_dir.exists()
        assert export_dir.is_dir()
        assert (export_dir / "manifest.json").exists()
        assert (export_dir / "email.db").exists()
        assert (export_dir / "todo.db").exists()

    def test_export_manifest_valid(self, tmp_data_dir: Path, tmp_path: Path):
        """Export manifest.json contains valid metadata."""
        (tmp_data_dir / "email.db").write_text("data")
        export_dir = export_data(str(tmp_path))
        manifest = json.loads((export_dir / "manifest.json").read_text())
        assert "exported_at" in manifest
        assert "files" in manifest
        assert "email.db" in manifest["files"]
        assert manifest["files"]["email.db"]["size"] == 4

    def test_import_restores_files(self, tmp_data_dir: Path, tmp_path: Path):
        """import_data copies files from export dir to data dir."""
        (tmp_data_dir / "email.db").write_text("original")
        export_dir = export_data(str(tmp_path))
        # Remove originals
        (tmp_data_dir / "email.db").unlink()
        result = import_data(str(export_dir), force=True)
        assert "email.db" in result["imported"]
        assert (tmp_data_dir / "email.db").exists()
        assert (tmp_data_dir / "email.db").read_text() == "original"

    def test_import_skips_existing(self, tmp_data_dir: Path, tmp_path: Path):
        """import_data skips files that already exist (without --force)."""
        (tmp_data_dir / "email.db").write_text("original")
        export_dir = export_data(str(tmp_path))
        result = import_data(str(export_dir))
        assert "email.db" in result["skipped"]

    def test_import_force_overwrites(self, tmp_data_dir: Path, tmp_path: Path):
        """import_data with --force overwrites existing files."""
        (tmp_data_dir / "email.db").write_text("original")
        export_dir = export_data(str(tmp_path))
        # Modify the export copy
        (export_dir / "email.db").write_text("overwritten")
        result = import_data(str(export_dir), force=True)
        assert "email.db" in result["imported"]
        assert (tmp_data_dir / "email.db").read_text() == "overwritten"

    def test_import_missing_manifest(self, tmp_data_dir: Path, tmp_path: Path):
        """import_data raises FileNotFoundError without manifest."""
        empty_dir = tmp_path / "not-an-export"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="manifest.json"):
            import_data(str(empty_dir))


class TestKnownDbPaths:
    def test_known_db_paths_only_existing(self, tmp_data_dir: Path):
        """_known_db_paths only returns paths that exist."""
        (tmp_data_dir / "email.db").write_text("")
        paths = _known_db_paths()
        names = [p.name for p in paths]
        assert "email.db" in names
        assert "todo.db" not in names  # not created

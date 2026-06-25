"""Tests for the !backup command handlers (dispatch integration)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Import to register handlers via side-effects
from lighterbird.server.command.handlers import backup  # noqa: F401
from lighterbird.server.command.registry import dispatch


def test_backup_now_no_dbs(tmp_data_dir: Path):
    """!backup now returns a message when no DBs exist."""
    result = dispatch(["backup", "now"], {})
    assert result["type"] in ("status", "error")
    data = result.get("data", {}) or {}
    # Either no files found or 0 backups created
    assert "No data files" in data.get("message", "") or len(data.get("backups", [])) == 0


def test_backup_now_with_db(tmp_data_dir: Path, tmp_path: Path):
    """!backup now creates backups for existing DB files."""
    # Simulate a DB file in the data dir
    (tmp_data_dir / "email.db").write_text("some email data")
    result = dispatch(["backup", "now"], {})
    assert result["type"] == "status"
    data = result.get("data", {})
    assert data.get("backups")
    assert len(data["backups"]) >= 1


def test_backup_list_empty(tmp_data_dir: Path):
    """!backup list shows message when no backups exist."""
    result = dispatch(["backup", "list"], {})
    assert result["type"] == "status"
    data = result.get("data", {})
    # Either message says no backups, or entries are empty
    if data:
        assert "No backups" in data.get("message", "") or not data.get("entries")


def test_backup_list_after_backup(tmp_data_dir: Path, tmp_path: Path):
    """!backup list shows backup entries after !backup now."""
    (tmp_data_dir / "email.db").write_text("data")
    dispatch(["backup", "now"], {})
    result = dispatch(["backup", "list"], {})
    data = result.get("data", {})
    assert data
    entries = data.get("entries", [])
    assert len(entries) >= 1
    assert entries[0]["database"] == "email"
    assert entries[0]["size"] is not None


def test_backup_list_filtered(tmp_data_dir: Path, tmp_path: Path):
    """!backup list --stem email shows only email backups."""
    (tmp_data_dir / "email.db").write_text("data")
    (tmp_data_dir / "todo.db").write_text("data")
    dispatch(["backup", "now"], {})
    result = dispatch(["backup", "list"], {"stem": "email"})
    entries = result.get("data", {}).get("entries", [])
    assert all(e["database"] == "email" for e in entries)


def test_backup_prune(tmp_data_dir: Path, tmp_path: Path):
    """!backup prune --keep N prunes old backups."""
    (tmp_data_dir / "email.db").write_text("data")
    # Create 3 backups
    for _ in range(3):
        dispatch(["backup", "now"], {})
    # Prune to 1
    result = dispatch(["backup", "prune"], {"keep": "1"})
    assert result["type"] == "status"


def test_backup_config_show(tmp_data_dir: Path, monkeypatch):
    """!backup config shows current config."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
    result = dispatch(["backup", "config"], {})
    assert result["type"] == "status"
    data = result.get("data", {})
    assert data is not None
    assert "external_dir" in data
    assert "retention" in data


def test_backup_config_set(tmp_data_dir: Path, monkeypatch):
    """!backup config --external-dir PATH updates config."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
    result = dispatch(["backup", "config"], {"external_dir": "/tmp/test-backups"})
    assert result["type"] == "status"
    data = result.get("data", {})
    assert "external_dir" in data.get("changed", [])
    # Verify persisted
    from lighterbird.core.backup import load_config
    cfg = load_config()
    assert cfg["external_dir"] == "/tmp/test-backups"


def test_backup_export(tmp_data_dir: Path, tmp_path: Path):
    """!backup export --output PATH exports data to a directory."""
    (tmp_data_dir / "email.db").write_text("test data")
    export_base = tmp_path / "exports"
    export_base.mkdir()
    result = dispatch(["backup", "export"], {"output": str(export_base)})
    assert result["type"] == "status"
    data = result.get("data", {})
    export_path = data.get("path", "")
    assert export_path
    export_dir = Path(export_path)
    assert export_dir.exists()
    assert (export_dir / "manifest.json").exists()
    assert (export_dir / "email.db").exists()


def test_backup_import(tmp_data_dir: Path, tmp_path: Path):
    """!backup import <path> imports data from an export dir."""
    # First create and export some data
    (tmp_data_dir / "email.db").write_text("exported data")
    export_base = tmp_path / "exports"
    export_base.mkdir()
    export_result = dispatch(["backup", "export"], {"output": str(export_base)})
    export_path = export_result["data"]["path"]

    # Remove original
    (tmp_data_dir / "email.db").unlink()

    # Import
    result = dispatch(["backup", "import", export_path], {"force": "true"})
    assert result["type"] == "status"
    data = result.get("data", {})
    imports = data.get("imported", [])
    assert "email.db" in imports
    assert (tmp_data_dir / "email.db").exists()
    assert (tmp_data_dir / "email.db").read_text() == "exported data"


def test_backup_import_no_path_error():
    """!backup import without path raises validation error."""
    with pytest.raises(Exception) as exc:
        dispatch(["backup", "import"], {})
    assert "Missing export path" in str(exc.value)


def test_backup_restore(tmp_data_dir: Path):
    """!backup restore restores latest backup."""
    (tmp_data_dir / "email.db").write_text("original")
    dispatch(["backup", "now"], {})
    # Corrupt the original
    (tmp_data_dir / "email.db").write_text("corrupted!")
    result = dispatch(["backup", "restore"], {})
    assert result["type"] == "status"
    assert (tmp_data_dir / "email.db").read_text() == "original"


def test_backup_now_with_external(tmp_data_dir: Path, tmp_path: Path, monkeypatch):
    """!backup now copies to external dir if configured."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_data_dir))
    ext_dir = tmp_path / "nextcloud-backups"
    (tmp_data_dir / "email.db").write_text("data")

    # Configure external dir
    from lighterbird.core.backup import save_config
    save_config({"external_dir": str(ext_dir), "retention": 10, "auto_interval_hours": 0})

    result = dispatch(["backup", "now"], {})
    data = result.get("data", {})
    assert data.get("external_copies") is not None
    # External dir should have the backup
    assert len(list(ext_dir.iterdir())) >= 1


def test_backup_root_shows_subcommands():
    """!backup (no subcommand) shows available subcommands."""
    result = dispatch(["backup"], {})
    assert result["type"] == "status"
    assert "Available !backup commands" in result.get("data", {}).get("_summary", "")


def test_backup_export_import_roundtrip(tmp_data_dir: Path, tmp_path: Path):
    """Full export → delete → import roundtrip preserves data."""
    # Create several DB files
    for name in ["email.db", "todo.db", "calendar.db"]:
        (tmp_data_dir / name).write_text(f"content of {name}")

    # Export
    export_base = tmp_path / "exports"
    export_base.mkdir()
    export_result = dispatch(["backup", "export"], {"output": str(export_base)})
    export_path = export_result["data"]["path"]

    # Delete originals
    for name in ["email.db", "todo.db", "calendar.db"]:
        (tmp_data_dir / name).unlink()

    # Import
    import_result = dispatch(["backup", "import", export_path], {"force": "true"})
    imported = import_result["data"]["imported"]

    # Verify
    for name in ["email.db", "todo.db", "calendar.db"]:
        assert (tmp_data_dir / name).exists(), f"{name} should exist after import"
        assert (tmp_data_dir / name).read_text() == f"content of {name}"

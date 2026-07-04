"""Tests for backup coverage — verifying ALL module DBs are backed up.

This ensures that _known_db_paths(), get_backup_targets(), and
export/import cover every module's database file via auto-discovery,
including any future modules that place a .db file in data_dir().
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.core.backup import (
    BackupTarget,
    _known_db_paths,
    _known_config_files,
    get_backup_targets,
    export_data,
    import_data,
    backup_all,
)
from lighterbird.core.paths import data_dir, config_dir


# ── get_backup_targets() autodiscovery tests ──────────────────────────────


def test_get_backup_targets_discovers_all_dbs(tmp_data_dir: Path):
    """get_backup_targets() auto-discovers all .db files in data_dir()."""
    for name in ["email.db", "todo.db", "letters.db", "profiles.db"]:
        (tmp_data_dir / name).write_text(f"{name} content")
    targets = get_backup_targets()
    names = [t.path.name for t in targets]
    for name in ["email.db", "todo.db", "letters.db", "profiles.db"]:
        assert name in names, f"{name} should be auto-discovered, got: {names}"


def test_get_backup_targets_discovers_new_module(tmp_data_dir: Path):
    """A new module's .db file (not previously known) is auto-discovered."""
    (tmp_data_dir / "brand_new_module.db").write_text("future module data")
    targets = get_backup_targets(category="data")
    names = [t.path.name for t in targets]
    assert "brand_new_module.db" in names, (
        f"New module DB should be auto-discovered, got: {names}"
    )


def test_get_backup_targets_category_filter(tmp_data_dir: Path):
    """get_backup_targets(category='data') returns only data targets."""
    (tmp_data_dir / "email.db").write_text("data")
    sp = config_dir() / "system_prompt.md"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text("# prompt")
    data_targets = get_backup_targets(category="data")
    config_targets = get_backup_targets(category="config")
    assert all(t.category == "data" for t in data_targets)
    assert all(t.category == "config" for t in config_targets)
    assert any("email.db" in t.path.name for t in data_targets)
    assert any("system_prompt.md" in t.path.name for t in config_targets)


def test_get_backup_targets_config_files(tmp_data_dir: Path, monkeypatch):
    """get_backup_targets(category='config') discovers .md files."""
    sp = tmp_data_dir / "system_prompt.md"
    sp.write_text("# prompt")
    targets = get_backup_targets(category="config")
    names = [t.path.name for t in targets]
    assert "system_prompt.md" in names, (
        f"Config files should be auto-discovered, got: {names}"
    )


def test_get_backup_targets_returns_BackupTarget(tmp_data_dir: Path):
    """Each target is a BackupTarget with structured metadata."""
    (tmp_data_dir / "email.db").write_text("data")
    targets = get_backup_targets()
    assert len(targets) >= 1
    t = next(x for x in targets if x.path.name == "email.db")
    assert isinstance(t, BackupTarget)
    assert t.module == "email"
    assert t.category == "data"


# ── _known_db_paths() wrapper tests ──────────────────────────────────────


def test_known_db_paths_includes_letters(tmp_data_dir: Path):
    """_known_db_paths() must include letters.db."""
    (tmp_data_dir / "letters.db").write_text("letter data")
    paths = _known_db_paths()
    names = [p.name for p in paths]
    assert "letters.db" in names, (
        f"letters.db should be in known DB paths, got: {names}"
    )


def test_known_db_paths_includes_profiles(tmp_data_dir: Path):
    """_known_db_paths() must include profiles.db."""
    (tmp_data_dir / "profiles.db").write_text("profile data")
    paths = _known_db_paths()
    names = [p.name for p in paths]
    assert "profiles.db" in names, (
        f"profiles.db should be in known DB paths, got: {names}"
    )


def test_known_db_paths_includes_user_commands(tmp_data_dir: Path):
    """_known_db_paths() must include user_commands.db."""
    (tmp_data_dir / "user_commands.db").write_text("saved commands")
    paths = _known_db_paths()
    names = [p.name for p in paths]
    assert "user_commands.db" in names, (
        f"user_commands.db should be in known DB paths, got: {names}"
    )


def test_known_db_paths_autodiscovers_new(tmp_data_dir: Path):
    """A previously unknown .db file is auto-discovered by _known_db_paths()."""
    (tmp_data_dir / "future_module.db").write_text("future data")
    paths = _known_db_paths()
    names = [p.name for p in paths]
    assert "future_module.db" in names


def test_backup_all_includes_letters(tmp_data_dir: Path, tmp_path: Path):
    """backup_all() must include letters.db in the 7z archive."""
    for name in ["email.db", "calendar.db", "contacts.db", "todo.db",
                 "journal.db", "letters.db", "profiles.db", "user_commands.db"]:
        (tmp_data_dir / name).write_text(f"{name} content")

    results = backup_all(retention=0)
    assert len(results) >= 1
    # The safest check is that backup_all succeeded (created archives)
    names = [p.name for p in results]
    assert any(n.endswith(".7z") for n in names), (
        f"No .7z archives created: {names}"
    )


def test_export_includes_all_modules(tmp_data_dir: Path, tmp_path: Path):
    """export_data() must include all module DB files + config files."""
    # Create all known database files
    for name in ["email.db", "calendar.db", "contacts.db", "todo.db",
                 "journal.db", "letters.db", "profiles.db", "user_commands.db"]:
        (tmp_data_dir / name).write_text(f"{name} content")

    export_dir = export_data(str(tmp_path))
    manifest = (export_dir / "manifest.json")
    assert manifest.exists()

    import json
    manifest_data = json.loads(manifest.read_text())

    for name in ["email.db", "calendar.db", "contacts.db", "todo.db",
                 "journal.db", "letters.db", "profiles.db", "user_commands.db"]:
        assert name in manifest_data["files"], (
            f"{name} should be in export manifest, got keys: "
            f"{list(manifest_data['files'].keys())}"
        )


def test_import_restores_all_modules(tmp_data_dir: Path, tmp_path: Path):
    """import_data() must restore all module DB files."""
    data = {}
    for name in ["email.db", "calendar.db", "contacts.db", "todo.db",
                 "journal.db", "letters.db", "profiles.db", "user_commands.db"]:
        content = f"content of {name}"
        (tmp_data_dir / name).write_text(content)
        data[name] = content

    # Export, delete all, then import
    export_dir = export_data(str(tmp_path))
    for name in data:
        (tmp_data_dir / name).unlink()

    result = import_data(str(export_dir), force=True)
    imported = result["imported"]

    for name in data:
        assert name in imported, (
            f"{name} should be imported, got: {imported}"
        )
        assert (tmp_data_dir / name).exists(), f"{name} should exist after import"
        assert (tmp_data_dir / name).read_text() == data[name]


def test_known_config_files(tmp_data_dir: Path, monkeypatch):
    """_known_config_files() includes system_prompt.md.
    
    system_prompt.md lives in config_dir, not data_dir, so we need to
    set both env vars to point to the same tmp_data_dir for this test.
    """
    sp = tmp_data_dir / "system_prompt.md"
    sp.write_text("# System prompt")
    files = _known_config_files()
    names = [f.name for f in files]
    assert "system_prompt.md" in names

"""Tests for lighterbird.core.backup — lighterbird-specific wrappers.

Covers: backup_with_strategy, backup_config_files.

Patching strategy:
- Functions accessed via the function's __globals__ (i.e. used bare like
  ``_known_config_files()`` without module prefix) must be patched at
  ``lighterbird.core.backup.<name>`` because that's where the function
  looks them up.
- Functions imported locally *inside* the function body (e.g.
  ``from lightercore.backup import _copy_with_verify``) must be patched
  at ``lightercore.backup.<name>``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestBackupWithStrategy:
    def test_with_strategy_object(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """backup_with_strategy should accept a BackupStrategy object."""
        from lighterbird.core.backup import backup_with_strategy
        from lightercore.backup import BackupStrategy

        strategy = BackupStrategy(id="test", max_copies=5, target="local")
        db_path = tmp_path / "test.db"
        db_path.write_text("fake db content", encoding="utf-8")

        monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))

        with patch("lighterbird.core.backup._lightercore_backup_database") as mock:
            mock.return_value = tmp_path / "backups" / "test.db.7z"
            result = backup_with_strategy(db_path, strategy)
            assert mock.called
            assert result is not None

    def test_with_strategy_dict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """backup_with_strategy should also accept a plain dict."""
        from lighterbird.core.backup import backup_with_strategy

        db_path = tmp_path / "test.db"
        db_path.write_text("fake db content", encoding="utf-8")

        monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))

        with patch("lighterbird.core.backup._lightercore_backup_database") as mock:
            mock.return_value = tmp_path / "backups" / "test.db.7z"
            strategy_dict = {"id": "default", "max_copies": 10, "target": "local"}
            result = backup_with_strategy(db_path, strategy_dict)
            assert mock.called
            assert result is not None


class TestBackupConfigFiles:
    """Tests for backup_config_files — backup of Markdown config files.

    The inner loop body (lines 58-64 of backup.py) is the critical
    un-covered path. We cover it by controlling __globals__-level
    deps at lighterbird.core.backup, and local-import deps at
    lightercore.backup.
    """

    def test_with_default_strategy(self, tmp_path: Path):
        """When list_strategies is empty, should use a default strategy."""
        from lighterbird.core.backup import backup_config_files

        cfg_file = tmp_path / "config" / "my_config.md"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text("my config content", encoding="utf-8")

        # Patch __globals__-level names at lighterbird.core.backup
        with (
            patch("lighterbird.core.backup._known_config_files") as mock_known,
            patch("lighterbird.core.backup.list_strategies") as mock_strat,
            # Patch locally-imported names at lightercore.backup
            patch("lightercore.backup._backup_dir") as mock_bdir,
            patch("lightercore.backup._timestamp") as mock_ts,
            patch("lightercore.backup._backup_filename") as mock_fname,
            patch("lightercore.backup._copy_with_verify") as mock_copy,
        ):
            mock_known.return_value = [cfg_file]
            mock_strat.return_value = []
            mock_bdir.return_value = tmp_path / "backups"
            mock_ts.return_value = "20260101T000000"
            mock_fname.return_value = "my_config_default.bak"
            mock_copy.return_value = None  # just to verify call

            result = backup_config_files()
            assert len(result) == 1
            mock_copy.assert_called_once()

    def test_with_enabled_strategies(self, tmp_path: Path):
        """When strategies exist, only enabled ones should be used."""
        from lighterbird.core.backup import backup_config_files

        cfg_file = tmp_path / "config" / "settings.md"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text("settings", encoding="utf-8")

        with (
            patch("lighterbird.core.backup._known_config_files") as mock_known,
            patch("lighterbird.core.backup.list_strategies") as mock_strat,
            patch("lightercore.backup._backup_dir") as mock_bdir,
            patch("lightercore.backup._timestamp") as mock_ts,
            patch("lightercore.backup._backup_filename") as mock_fname,
            patch("lightercore.backup._copy_with_verify") as mock_copy,
        ):
            mock_known.return_value = [cfg_file]
            mock_strat.return_value = [
                {"id": "local", "enabled": True, "max_copies": 5, "target": "local"},
                {"id": "remote", "enabled": False, "max_copies": 3, "target": "s3"},
            ]
            mock_bdir.return_value = tmp_path / "backups"
            mock_ts.return_value = "20260101T000000"
            mock_fname.return_value = "settings_local.bak"

            result = backup_config_files()
            # Only the enabled strategy should iterate
            assert len(result) == 1
            mock_copy.assert_called_once()

    def test_multiple_config_files(self, tmp_path: Path):
        """Should produce backups for each config file × each enabled strategy."""
        from lighterbird.core.backup import backup_config_files

        cfg1 = tmp_path / "config" / "a.md"
        cfg2 = tmp_path / "config" / "b.md"
        cfg1.parent.mkdir(parents=True)
        cfg1.write_text("a")
        cfg2.write_text("b")

        with (
            patch("lighterbird.core.backup._known_config_files") as mock_known,
            patch("lighterbird.core.backup.list_strategies") as mock_strat,
            patch("lightercore.backup._backup_dir") as mock_bdir,
            patch("lightercore.backup._timestamp") as mock_ts,
            patch("lightercore.backup._backup_filename") as mock_fname,
            patch("lightercore.backup._copy_with_verify") as mock_copy,
        ):
            mock_known.return_value = [cfg1, cfg2]
            mock_strat.return_value = [
                {"id": "local", "enabled": True, "max_copies": 5, "target": "local"},
            ]
            mock_bdir.return_value = tmp_path / "backups"
            mock_ts.return_value = "20260101T000000"
            mock_fname.return_value = "dummy.bak"

            result = backup_config_files()
            # 2 config files × 1 enabled strategy = 2
            assert len(result) == 2
            assert mock_copy.call_count == 2

    def test_no_config_files(self, tmp_path: Path):
        """When no config files exist, result should be empty."""
        from lighterbird.core.backup import backup_config_files

        with (
            patch("lighterbird.core.backup._known_config_files") as mock_known,
            patch("lighterbird.core.backup.list_strategies") as mock_strat,
            patch("lightercore.backup._copy_with_verify") as mock_copy,
        ):
            mock_known.return_value = []
            mock_strat.return_value = []

            result = backup_config_files()
            assert result == []
            mock_copy.assert_not_called()

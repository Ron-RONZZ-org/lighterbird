"""Tests for lighterbird.core.backup — lighterbird-specific wrappers.

Covers: backup_with_strategy (with BackupStrategy object and dict).

Note: backup_config_files is excluded here due to complex mocking
interactions with lightercore's internal imports. It is already partially
covered by existing tests (test_backup.py).
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

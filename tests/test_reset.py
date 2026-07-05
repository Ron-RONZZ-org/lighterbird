"""Unit tests for the ``!reset`` command and ``core/reset.py``.

Tests:
- ``reset_to_fresh_state()`` with and without backup path
- ``reset_to_fresh_state()`` keyring cleanup
- ``!reset`` command handler dispatch
- ``!reset --no-backup`` form-required response
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from lighterbird.core.reset import reset_to_fresh_state
from lighterbird.server.app import create_app

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_env():
    """Create an isolated lighterbird environment with seeded data.

    Sets env vars for data/config/cache/state dirs pointing to a temp
    directory, seeds it with test data, then yields.
    """
    tmp = Path(tempfile.mkdtemp(prefix="lighterbird-test-reset-"))
    old_data = os.environ.get("LIGHTERBIRD_DATA_DIR", "")
    old_config = os.environ.get("LIGHTERBIRD_CONFIG_DIR", "")
    old_cache = os.environ.get("LIGHTERBIRD_CACHE_DIR", "")
    old_state = os.environ.get("LIGHTERBIRD_STATE_DIR", "")

    data = tmp / "data"
    config = tmp / "config"
    cache = tmp / "cache"
    state = tmp / "state"
    data.mkdir(parents=True, exist_ok=True)
    config.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)

    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data)
    os.environ["LIGHTERBIRD_CONFIG_DIR"] = str(config)
    os.environ["LIGHTERBIRD_CACHE_DIR"] = str(cache)
    os.environ["LIGHTERBIRD_STATE_DIR"] = str(state)

    # Seed test data
    from lighterbird.scripts.seed import seed_data_dir
    seed_data_dir(data)

    yield data, config, tmp

    # Restore env
    if old_data:
        os.environ["LIGHTERBIRD_DATA_DIR"] = old_data
    else:
        os.environ.pop("LIGHTERBIRD_DATA_DIR", None)
    if old_config:
        os.environ["LIGHTERBIRD_CONFIG_DIR"] = old_config
    else:
        os.environ.pop("LIGHTERBIRD_CONFIG_DIR", None)
    if old_cache:
        os.environ["LIGHTERBIRD_CACHE_DIR"] = old_cache
    else:
        os.environ.pop("LIGHTERBIRD_CACHE_DIR", None)
    if old_state:
        os.environ["LIGHTERBIRD_STATE_DIR"] = old_state
    else:
        os.environ.pop("LIGHTERBIRD_STATE_DIR", None)

    # Clean up
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def client(isolated_env):
    """FastAPI test client pointing at the isolated env."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Tests: core/reset.py ───────────────────────────────────────────────────


class TestResetToFreshState:
    """Tests for the core reset function."""

    def test_reset_with_backup(self, isolated_env):
        """Backup at path + reset should create archive and clear all DBs."""
        data_dir_path, config_dir_path, tmp = isolated_env
        backup_path = tmp / "my-backup.7z"

        # Verify DBs exist before reset
        dbs_before = list(data_dir_path.glob("*.db"))
        assert len(dbs_before) >= 5, f"Expected multiple DBs, got {dbs_before}"

        result = reset_to_fresh_state(backup_path=str(backup_path))

        # Backup was created
        assert result["backup_path"] is not None
        assert "my-backup.7z" in result["backup_path"]
        assert backup_path.exists(), f"Backup not found at {backup_path}"
        assert backup_path.stat().st_size > 100, "Backup archive is too small"

        # All DBs removed (from disk, before schema re-creation)
        assert len(result["databases_removed"]) >= 5

        # Schemas recreated — empty (but initialised) DBs exist again
        assert len(result["schema_recreated"]) >= 5
        dbs_after = list(data_dir_path.glob("*.db"))
        assert len(dbs_after) >= 5, "DBs should be recreated as empty files"

    def test_reset_auto_generates_filename_for_directory(self, isolated_env):
        """If backup_path is a directory, auto-generate filename."""
        data_dir_path, config_dir_path, tmp = isolated_env
        backup_dir = tmp / "backups"
        backup_dir.mkdir()

        result = reset_to_fresh_state(backup_path=str(backup_dir))

        assert result["backup_path"] is not None
        assert result["backup_path"].endswith(".7z")
        assert Path(result["backup_path"]).exists()

    def test_reset_clears_keyring(self, isolated_env):
        """Keyring entries should be cleared for known accounts."""
        data_dir_path, config_dir_path, tmp = isolated_env

        # Store a test password in keyring
        from lighterbird.core.keyring import set_password
        set_password("lighterbird-llm", "active-provider", json.dumps({"key": "val"}))
        set_password("lighterbird/email/test@example.com", "password", "secret123")

        with patch("lighterbird.core.reset.delete_password", return_value=True):
            result = reset_to_fresh_state(backup_path=None)
            assert result["credentials_cleared"] >= 1

    def test_reset_backup_archive_contains_data(self, isolated_env):
        """The backup 7z archive should contain the .db files."""
        data_dir_path, config_dir_path, tmp = isolated_env
        backup_path = tmp / "reset.7z"

        # Get expected DB names before reset
        {p.name for p in data_dir_path.glob("*.db")}

        reset_to_fresh_state(backup_path=str(backup_path))
        assert backup_path.exists()

        # Extract and verify contents
        import py7zr
        extract_dir = tmp / "_extracted"
        extract_dir.mkdir()
        with py7zr.SevenZipFile(backup_path, mode="r") as arc:
            arc.extractall(path=extract_dir)

        extracted_files = set()
        for p in extract_dir.iterdir():
            if p.suffix == ".db":
                extracted_files.add(p.name)
        # Should contain at least a subset of the expected DBs
        assert len(extracted_files) >= 3, f"Expected at least 3 DBs in archive, got {extracted_files}"


# ── Tests: !reset command dispatch ────────────────────────────────────────


class TestResetCommandHandler:
    """Tests for the !reset command dispatch."""

    def test_reset_no_args_returns_error(self):
        """!reset with no args should return a validation error."""
        from lighterbird.server.command.errors import CommandValidationError
        from lighterbird.server.command.handlers.reset import reset_cmd

        with pytest.raises(CommandValidationError, match="provide either"):
            reset_cmd([], {})

    def test_reset_conflicting_args_returns_error(self):
        """!reset /path --no-backup should return validation error."""
        from lighterbird.server.command.errors import CommandValidationError
        from lighterbird.server.command.handlers.reset import reset_cmd

        with pytest.raises(CommandValidationError, match="Cannot specify both"):
            reset_cmd(["/tmp/x.7z"], {"no-backup": ""})

    def test_reset_no_backup_returns_form_required(self):
        """!reset --no-backup should return form-required."""
        from lighterbird.server.command.handlers.reset import reset_cmd

        result = reset_cmd([], {"no-backup": ""})
        assert result["type"] == "form-required"
        assert result["data"]["form"] == "reset-no-backup"

    def test_reset_no_backup_with_confirmed_executes(self, isolated_env):
        """!reset --no-backup --confirmed should execute the reset."""
        from lighterbird.server.command.handlers.reset import reset_cmd

        result = reset_cmd([], {"no-backup": "", "confirmed": "true"})
        assert result["type"] == "status"
        assert "Reset Complete" in result["title"]

    def test_reset_with_backup_path_executes(self, isolated_env):
        """!reset /path/to/backup.7z should execute with backup."""
        data_dir_path, config_dir_path, tmp = isolated_env
        from lighterbird.server.command.handlers.reset import reset_cmd

        backup_path = str(tmp / "backup.7z")
        result = reset_cmd([backup_path], {})

        assert result["type"] == "status"
        assert "Reset Complete" in result["title"]
        assert result["data"]["backup_path"] is not None

    def test_reset_via_api_no_args(self, client):
        """POST /api/v1/command with !reset and no args returns error."""
        resp = client.post("/api/v1/command", json={
            "tokens": ["reset"],
            "flags": {},
        })
        assert resp.status_code == 400
        data = resp.json()
        assert "provide either" in str(data).lower()

    def test_reset_via_api_no_backup(self, client, isolated_env):
        """POST /api/v1/command !reset --no-backup returns form-required."""
        resp = client.post("/api/v1/command", json={
            "tokens": ["reset"],
            "flags": {"no-backup": ""},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
        assert data["data"]["form"] == "reset-no-backup"

    def test_reset_via_api_no_backup_with_confirmed(self, client, isolated_env):
        """POST /api/v1/command !reset --no-backup --confirmed executes."""
        resp = client.post("/api/v1/command", json={
            "tokens": ["reset"],
            "flags": {"no-backup": "", "confirmed": "true"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "Reset Complete" in data["title"]

    def test_reset_via_api_with_path(self, client, isolated_env):
        """POST /api/v1/command !reset /tmp/backup.7z executes backup+reset."""
        data_dir_path, config_dir_path, tmp = isolated_env
        backup_path = str(tmp / "backup.7z")

        resp = client.post("/api/v1/command", json={
            "tokens": ["reset", backup_path],
            "flags": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        assert "Reset Complete" in data["title"]
        # Backup file was created
        assert Path(backup_path).exists()

    def test_reset_conflicting_via_api(self, client):
        """POST /api/v1/command !reset path --no-backup returns error."""
        resp = client.post("/api/v1/command", json={
            "tokens": ["reset"],
            "flags": {"no-backup": ""},
            # path in remaining tokens
        })
        # Actually the test above uses path in tokens, so adjust:
        resp = client.post("/api/v1/command", json={
            "tokens": ["reset", "/tmp/x.7z"],
            "flags": {"no-backup": ""},
        })
        assert resp.status_code == 400
        data = resp.json()
        assert "Cannot specify both" in str(data)

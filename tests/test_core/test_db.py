"""Tests for lighterbird.core.db — LighterDB."""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.core.db import LighterDB
from lighterbird.core.exceptions import ProtectedPathError
from lighterbird.core.paths import protect_directory, safe_rmtree, safe_unlink


class TestLighterDB:
    def test_creates_file(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = LighterDB(db_path)
        db.execute("CREATE TABLE t (x INTEGER)")
        db.execute("INSERT INTO t VALUES (42)")
        assert db_path.exists()

    def test_per_thread_connections(self, tmp_path: Path):
        db = LighterDB(tmp_path / "threads.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        db.execute("INSERT INTO t VALUES (1)")

        results = []
        import threading

        def worker():
            r = db.execute("SELECT x FROM t")
            results.extend(r)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert len(results) == 1
        assert results[0]["x"] == 1

    def test_execute_one_returns_none(self, tmp_path: Path):
        db = LighterDB(tmp_path / "empty.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        assert db.execute_one("SELECT * FROM t") is None

    def test_execute_one_returns_row(self, tmp_path: Path):
        db = LighterDB(tmp_path / "single.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        db.execute("INSERT INTO t VALUES (99)")
        row = db.execute_one("SELECT * FROM t")
        assert row is not None
        assert row["x"] == 99

    def test_transaction_commit(self, tmp_path: Path):
        db = LighterDB(tmp_path / "txn.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        with db.transaction() as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            conn.execute("INSERT INTO t VALUES (2)")
        rows = db.execute("SELECT x FROM t ORDER BY x")
        assert len(rows) == 2

    def test_transaction_rollback(self, tmp_path: Path):
        db = LighterDB(tmp_path / "rollback.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        try:
            with db.transaction() as conn:
                conn.execute("INSERT INTO t VALUES (1)")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        rows = db.execute("SELECT x FROM t")
        assert len(rows) == 0

    def test_init_schema(self, tmp_path: Path):
        db = LighterDB(tmp_path / "schema.db")
        schema = {
            "users": "CREATE TABLE users (uuid TEXT PRIMARY KEY, name TEXT)",
            "posts": "CREATE TABLE posts (uuid TEXT PRIMARY KEY, title TEXT)",
        }
        db.init_schema(schema)
        assert db.table_exists("users")
        assert db.table_exists("posts")

    def test_init_schema_idempotent(self, tmp_path: Path):
        db = LighterDB(tmp_path / "idemp.db")
        schema = {"t": "CREATE TABLE t (x INTEGER)"}
        db.init_schema(schema)
        db.init_schema(schema)  # Second call should not fail
        assert db.table_exists("t")

    def test_execute_many(self, tmp_path: Path):
        db = LighterDB(tmp_path / "many.db")
        db.execute("CREATE TABLE t (x INTEGER)")
        db.execute_many("INSERT INTO t VALUES (?)", [(1,), (2,), (3,)])
        rows = db.execute("SELECT x FROM t ORDER BY x")
        assert [r["x"] for r in rows] == [1, 2, 3]

    def test_get_pragma_table_info(self, tmp_path: Path):
        db = LighterDB(tmp_path / "pragma.db")
        db.execute("CREATE TABLE t (uuid TEXT PRIMARY KEY, name TEXT NOT NULL, age INTEGER)")
        info = db.get_pragma_table_info("t")
        columns = {r["name"]: r for r in info}
        assert columns["uuid"]["type"] == "TEXT"
        assert columns["uuid"]["pk"] == 1
        assert columns["name"]["notnull"] == 1
        assert columns["age"]["type"] == "INTEGER"


class TestPaths:
    @pytest.mark.no_isolation
    def test_data_dir_default(self):
        from lighterbird.core.paths import data_dir

        assert "unknownlighterapp" in str(data_dir())

    def test_data_dir_override(self, monkeypatch):
        from lighterbird.core.paths import data_dir

        monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", "/tmp/lbtest/data")
        assert str(data_dir()) == "/tmp/lbtest/data"

    @pytest.mark.no_isolation
    def test_lighterbird_dir_override(self, monkeypatch):
        from lighterbird.core.paths import data_dir

        monkeypatch.setenv("LIGHTERBIRD_DIR", "/tmp/lbroot")
        assert str(data_dir()) == "/tmp/lbroot/data"

    def test_ensure_dirs_creates_dirs(self, monkeypatch, tmp_path):
        from lighterbird.core.paths import (
            cache_dir,
            config_dir,
            data_dir,
            ensure_dirs,
            state_dir,
        )

        monkeypatch.setenv("LIGHTERBIRD_DIR", str(tmp_path / "lb"))
        ensure_dirs()
        assert data_dir().is_dir()
        assert config_dir().is_dir()
        assert cache_dir().is_dir()
        assert state_dir().is_dir()

    def test_sentinel_protection(self, tmp_path: Path):
        d = tmp_path / "protected"
        protect_directory(d)
        from lighterbird.core.paths import is_protected

        assert is_protected(d)

    def test_safe_rmtree_raises_on_protected(self, tmp_path: Path):
        d = tmp_path / "nuke"
        protect_directory(d)
        (d / "file.txt").write_text("data")
        with pytest.raises(ProtectedPathError):
            safe_rmtree(d)

    def test_safe_rmtree_works_with_force(self, tmp_path: Path):
        d = tmp_path / "force"
        protect_directory(d)
        (d / "file.txt").write_text("data")
        safe_rmtree(d, force=True)  # Should not raise
        assert not d.exists()

    def test_safe_unlink_raises_on_protected(self, tmp_path: Path):
        d = tmp_path / "unlink"
        protect_directory(d)
        f = d / "secret.txt"
        f.write_text("data")
        with pytest.raises(ProtectedPathError):
            safe_unlink(f)

    def test_safe_unlink_works_with_force(self, tmp_path: Path):
        d = tmp_path / "unlink_force"
        protect_directory(d)
        f = d / "secret.txt"
        f.write_text("data")
        safe_unlink(f, force=True)
        assert not f.exists()


class TestKeyring:
    def test_get_none_for_unknown_key(self):
        # For a key that was never stored, returns None
        import uuid

        from lighterbird.core.keyring import get_password
        pw = get_password(f"unknown_svc_{uuid.uuid4().hex}", "not_stored")
        assert pw is None

    def test_set_password_behavior(self):
        from lighterbird.core.keyring import set_password

        result = set_password("test_service", "test_key", "sekret")
        # Returns a bool indicating success (True) or keyring unavailable (False)
        assert isinstance(result, bool)


class TestCRUDService:
    @pytest.fixture
    def db(self, tmp_path: Path):
        d = LighterDB(tmp_path / "crud.db")
        d.execute(
            "CREATE TABLE items ("
            "uuid TEXT PRIMARY KEY, name TEXT, value INTEGER, "
            "created_at TEXT, updated_at TEXT)"
        )
        return d

    @pytest.fixture
    def service(self, db):
        from lighterbird.core.crud import CRUDService

        return CRUDService(db, "items")

    def test_create_and_get(self, service):
        entry = service.create({"name": "test", "value": 42})
        assert "uuid" in entry
        assert entry["name"] == "test"
        assert "created_at" in entry
        assert "updated_at" in entry

        fetched = service.get(entry["uuid"])
        assert fetched is not None
        assert fetched["value"] == 42

    def test_list(self, service):
        service.create({"name": "a", "value": 1})
        service.create({"name": "b", "value": 2})
        # Default is DESC — last created first
        entries = service.list(order_by="value", desc=False)
        assert len(entries) == 2
        assert entries[0]["value"] == 1

    def test_list_with_limit_and_offset(self, service):
        for i in range(10):
            service.create({"name": f"item{i}", "value": i})
        entries = service.list(order_by="value", desc=False, limit=3, offset=5)
        assert len(entries) == 3
        assert entries[0]["value"] == 5

    def test_update(self, service):
        entry = service.create({"name": "old", "value": 1})
        updated = service.update(entry["uuid"], {"name": "new", "value": 2})
        assert updated["name"] == "new"
        assert updated["value"] == 2

    def test_delete(self, service):
        entry = service.create({"name": "delete_me", "value": 0})
        assert service.delete(entry["uuid"]) is True
        assert service.get(entry["uuid"]) is None

    def test_delete_nonexistent(self, service):
        assert service.delete("nonexistent") is False

    def test_find_by_uuid_prefix(self, service):
        entry = service.create({"name": "prefix_test", "value": 1})
        results = service.find_by_uuid_prefix(entry["uuid"][:8])
        assert len(results) >= 1

    def test_search(self, service):
        service.create({"name": "hello world", "value": 1})
        service.create({"name": "goodbye", "value": 2})
        results = service.search("name", "hello")
        assert len(results) == 1
        assert results[0]["name"] == "hello world"

    def test_count(self, service):
        assert service.count() == 0
        service.create({"name": "a", "value": 1})
        service.create({"name": "b", "value": 2})
        assert service.count() == 2

    def test_post_create_hook(self, db):
        from lighterbird.core.crud import CRUDService

        calls = []

        class TestService(CRUDService):
            def _post_create(self, data, result):
                calls.append(("create", data["name"]))

        s = TestService(db, "items")
        s.create({"name": "hook_test", "value": 99})
        assert len(calls) == 1
        assert calls[0] == ("create", "hook_test")

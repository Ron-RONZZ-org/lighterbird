"""Tests for lighterbird.core.storage — AttachmentStore.

Covers: store, retrieve, list_for_message, delete_all, total_size,
safe_filename edge cases.

Data directory isolation is provided by the root conftest's
autouse ``auto_isolate_data_dir`` fixture.
"""

from __future__ import annotations

import pytest

from lighterbird.core.storage import AttachmentStore


class TestAttachmentStore:
    def test_store_and_retrieve(self):
        store = AttachmentStore()
        path = store.store("msg-1", "attach-1", b"hello world")
        assert path.exists()
        assert path.read_bytes() == b"hello world"
        assert store.retrieve("msg-1", "attach-1") == b"hello world"

    def test_store_multiple_attachments(self):
        store = AttachmentStore()
        store.store("msg-1", "a1", b"data1")
        store.store("msg-1", "a2", b"data2")
        files = store.list_for_message("msg-1")
        assert len(files) == 2

    def test_list_empty_message(self):
        store = AttachmentStore()
        assert store.list_for_message("nonexistent-msg") == []

    def test_delete_all(self):
        store = AttachmentStore()
        store.store("msg-1", "a1", b"data1")
        store.store("msg-1", "a2", b"data2")
        store.delete_all("msg-1")
        assert store.list_for_message("msg-1") == []

    def test_delete_nonexistent_message(self):
        store = AttachmentStore()
        store.delete_all("nonexistent-msg")

    def test_total_size(self):
        store = AttachmentStore()
        store.store("msg-1", "a1", b"12345")
        store.store("msg-1", "a2", b"123")
        assert store.total_size("msg-1") == 8

    def test_total_size_empty_message(self):
        store = AttachmentStore()
        assert store.total_size("nonexistent") == 0

    def test_safe_filename_strips_path_components(self):
        """Path components and dangerous chars are removed from content_id."""
        store = AttachmentStore()
        # Directory traversal attempts are neutralized
        assert store._safe_filename("../../etc/passwd") == "passwd"
        # Mixed path separators: `/` is stripped by Path.name, `\` replaced
        result = store._safe_filename("a/b\\c")
        assert result == "b_c"
        assert "/" not in result

    def test_store_creates_base_dir(self):
        store = AttachmentStore()
        from lighterbird.core.paths import data_dir
        # Base dir is created lazily on first store()
        assert not (data_dir() / "attachments").is_dir()
        store.store("msg-uuid", "cid", b"data")
        assert (data_dir() / "attachments").is_dir()

    def test_retrieve_nonexistent_raises(self):
        store = AttachmentStore()
        with pytest.raises(FileNotFoundError):
            store.retrieve("msg-none", "att-none")

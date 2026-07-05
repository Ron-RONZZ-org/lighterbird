"""Tests for letter/services/letters.py — LetterService CRUD, list sorting, search."""

from __future__ import annotations

import pytest

from lighterbird.letter.services.letters import LetterService


@pytest.fixture
def svc(monkeypatch, tmp_path):
    """Return a fresh LetterService with isolated temp DB."""
    from lighterbird.letter import db as letter_db
    monkeypatch.setattr(letter_db, "_letter_db_path", lambda: tmp_path / "letters.db")
    db = letter_db.get_db()
    return LetterService(db)


# ── Create ───────────────────────────────────────────────────────────────────


class TestCreate:
    def test_create_minimal(self, svc):
        letter = svc.create({
            "direction": "sent",
            "object": "Hello",
            "sender_manual": "Alice",
            "recipient_manual": "Bob",
        })
        assert letter["uuid"]
        assert letter["direction"] == "sent"
        assert letter["object"] == "Hello"
        assert letter["sender_manual"] == "Alice"
        assert letter["recipient_manual"] == "Bob"
        assert letter.get("created_at")
        assert letter.get("updated_at")

    def test_create_received(self, svc):
        letter = svc.create({
            "direction": "received",
            "object": "Reply",
            "sender_manual": "Charlie",
            "recipient_manual": "Alice",
        })
        assert letter["direction"] == "received"

    def test_create_invalid_direction(self, svc):
        with pytest.raises(Exception):
            svc.create({"direction": "invalid", "object": "x"})

# ── Get ──────────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_nonexistent(self, svc):
        assert svc.get("nonexistent") is None

    def test_get_returns_letter(self, svc):
        created = svc.create({
            "direction": "sent", "object": "Test",
            "sender_manual": "A", "recipient_manual": "B",
        })
        fetched = svc.get(created["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]
        assert fetched["object"] == "Test"


# ── Update ───────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_fields(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "Original",
            "sender_manual": "A", "recipient_manual": "B",
        })
        updated = svc.update(letter["uuid"], {"object": "Updated"})
        assert updated["object"] == "Updated"

    def test_update_nonexistent_returns_none(self, svc):
        result = svc.update("nonexistent", {"object": "X"})
        assert result is None

    def test_mark_as_sent(self, svc):
        """Update direction to mark a received letter as sent."""
        letter = svc.create({
            "direction": "received", "object": "Incoming",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        updated = svc.update(letter["uuid"], {"direction": "sent"})
        assert updated["direction"] == "sent"

    def test_mark_as_received(self, svc):
        """Update direction to mark a sent letter as received."""
        letter = svc.create({
            "direction": "sent", "object": "Outgoing",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        updated = svc.update(letter["uuid"], {"direction": "received"})
        assert updated["direction"] == "received"


# ── Delete ───────────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_existing(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "ToDelete",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.delete(letter["uuid"])
        assert svc.get(letter["uuid"]) is None

    def test_delete_nonexistent(self, svc):
        svc.delete("nonexistent")  # Should not raise


# ── List ─────────────────────────────────────────────────────────────────────


class TestList:
    def test_list_empty(self, svc):
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        svc.create({
            "direction": "sent", "object": "A",
            "sender_manual": "S", "recipient_manual": "R",
        })
        svc.create({
            "direction": "received", "object": "B",
            "sender_manual": "S2", "recipient_manual": "R2",
        })
        results = svc.list(limit=10)
        assert len(results) == 2

    def test_list_default_sort_order_desc(self, svc):
        """Default sort is DESC by created_at — newer items first."""
        letter_a = svc.create({
            "direction": "sent", "object": "First",
            "sender_manual": "A", "recipient_manual": "B",
        })
        letter_b = svc.create({
            "direction": "sent", "object": "Second",
            "sender_manual": "A", "recipient_manual": "B",
        })
        results = svc.list(limit=10)
        assert results[0]["uuid"] == letter_b["uuid"]
        assert results[1]["uuid"] == letter_a["uuid"]

    def test_list_asc_order(self, svc):
        """Explicit ASC order — older items first."""
        letter_a = svc.create({
            "direction": "sent", "object": "First",
            "sender_manual": "A", "recipient_manual": "B",
        })
        letter_b = svc.create({
            "direction": "sent", "object": "Second",
            "sender_manual": "A", "recipient_manual": "B",
        })
        results = svc.list(limit=10, desc=False)
        assert results[0]["uuid"] == letter_a["uuid"]
        assert results[1]["uuid"] == letter_b["uuid"]

    def test_list_filter_direction(self, svc):
        svc.create({
            "direction": "sent", "object": "A",
            "sender_manual": "S", "recipient_manual": "R",
        })
        svc.create({
            "direction": "received", "object": "B",
            "sender_manual": "S2", "recipient_manual": "R2",
        })
        results = svc.list(direction="sent")
        assert len(results) == 1
        assert results[0]["object"] == "A"

    def test_list_filter_object_query(self, svc):
        svc.create({
            "direction": "sent", "object": "Hello World",
            "sender_manual": "S", "recipient_manual": "R",
        })
        svc.create({
            "direction": "sent", "object": "Goodbye",
            "sender_manual": "S", "recipient_manual": "R",
        })
        results = svc.list(object_query="hello")
        assert len(results) == 1
        assert results[0]["object"] == "Hello World"

    def test_list_with_limit(self, svc):
        for i in range(5):
            svc.create({
                "direction": "sent", "object": f"Letter {i}",
                "sender_manual": "A", "recipient_manual": "B",
            })
        results = svc.list(limit=3)
        assert len(results) == 3

    def test_list_with_offset(self, svc):
        uuids = []
        for i in range(5):
            letter = svc.create({
                "direction": "sent", "object": f"Letter {i}",
                "sender_manual": "A", "recipient_manual": "B",
            })
            uuids.append(letter["uuid"])
        # Offset 3 → skip the 3 newest, get the last 2
        results = svc.list(limit=10, offset=3)
        assert len(results) == 2


# ── Search ───────────────────────────────────────────────────────────────────


class TestSearch:
    def test_search_by_object(self, svc):
        svc.create({
            "direction": "sent", "object": "Special Letter",
            "sender_manual": "A", "recipient_manual": "B",
        })
        results = svc.search("special")
        assert len(results) == 1

    def test_search_by_sender(self, svc):
        svc.create({
            "direction": "sent", "object": "Letter",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        results = svc.search("alice")
        assert len(results) == 1

    def test_search_by_recipient(self, svc):
        svc.create({
            "direction": "sent", "object": "Letter",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        results = svc.search("bob")
        assert len(results) == 1

    def test_search_empty_query_returns_list(self, svc):
        svc.create({
            "direction": "sent", "object": "A",
            "sender_manual": "S", "recipient_manual": "R",
        })
        results = svc.search("")
        assert len(results) == 1

    def test_search_no_match(self, svc):
        svc.create({
            "direction": "sent", "object": "Hello",
            "sender_manual": "A", "recipient_manual": "B",
        })
        results = svc.search("nonexistent")
        assert results == []

    def test_search_result_order_desc(self, svc):
        """Search results are sorted by created_at DESC."""
        letter_a = svc.create({
            "direction": "sent", "object": "Searchable",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        letter_b = svc.create({
            "direction": "sent", "object": "Searchable",
            "sender_manual": "Alice", "recipient_manual": "Charlie",
        })
        results = svc.search("searchable")
        assert len(results) == 2
        assert results[0]["uuid"] == letter_b["uuid"]
        assert results[1]["uuid"] == letter_a["uuid"]

    def test_search_case_insensitive(self, svc):
        svc.create({
            "direction": "sent", "object": "UPPERCASE Title",
            "sender_manual": "Admin", "recipient_manual": "User",
        })
        results = svc.search("uppercase")
        assert len(results) == 1

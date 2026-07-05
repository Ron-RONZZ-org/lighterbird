"""Tests for letter/services/letters.py — LetterService CRUD, tags, export/import."""

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


class TestList:
    def test_list_empty(self, svc):
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        svc.create({"direction": "sent", "object": "A", "sender_manual": "S", "recipient_manual": "R"})
        svc.create({"direction": "received", "object": "B", "sender_manual": "S2", "recipient_manual": "R2"})
        results = svc.list(limit=10)
        assert len(results) == 2

    def test_list_filter_direction(self, svc):
        svc.create({"direction": "sent", "object": "A", "sender_manual": "S", "recipient_manual": "R"})
        svc.create({"direction": "received", "object": "B", "sender_manual": "S2", "recipient_manual": "R2"})
        results = svc.list(direction="sent")
        assert len(results) == 1
        assert results[0]["object"] == "A"

    def test_list_filter_object_query(self, svc):
        svc.create({"direction": "sent", "object": "Hello World", "sender_manual": "S", "recipient_manual": "R"})
        svc.create({"direction": "sent", "object": "Goodbye", "sender_manual": "S", "recipient_manual": "R"})
        results = svc.list(object_query="hello")
        assert len(results) == 1
        assert results[0]["object"] == "Hello World"


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


class TestTags:
    def test_set_and_get_tags(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "Tagged",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.set_tags(letter["uuid"], ["urgent", "personal"])
        tags = svc.get_tags(letter["uuid"])
        assert sorted(tags) == ["personal", "urgent"]

    def test_add_tags_merges(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "Merged",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.set_tags(letter["uuid"], ["urgent"])
        svc.add_tags(letter["uuid"], ["personal"])
        tags = svc.get_tags(letter["uuid"])
        assert sorted(tags) == ["personal", "urgent"]

    def test_remove_tags(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "Remove",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.set_tags(letter["uuid"], ["urgent", "personal", "fyi"])
        svc.remove_tags(letter["uuid"], ["urgent"])
        tags = svc.get_tags(letter["uuid"])
        assert sorted(tags) == ["fyi", "personal"]

    def test_normalize_tags(self, svc):
        result = LetterService.normalize_tags(["Urgent", "  personal ", "urgent"])
        assert result == ["urgent", "personal"]  # deduplicated, lowercased, stripped

    def test_normalize_tags_comma_separated(self, svc):
        result = LetterService.normalize_tags(["a,b", "c"])
        assert sorted(result) == ["a", "b", "c"]

    def test_list_includes_tags(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "WithTags",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.set_tags(letter["uuid"], ["favorite"])
        results = svc.list()
        assert len(results) == 1
        assert results[0].get("tags") == ["favorite"]

    def test_tag_filter_in_list(self, svc):
        l1 = svc.create({"direction": "sent", "object": "A", "sender_manual": "S", "recipient_manual": "R"})
        l2 = svc.create({"direction": "sent", "object": "B", "sender_manual": "S", "recipient_manual": "R"})
        svc.set_tags(l1["uuid"], ["urgent"])
        svc.set_tags(l2["uuid"], ["normal"])
        results = svc.list(tags=["urgent"])
        assert len(results) == 1
        assert results[0]["object"] == "A"


class TestSearch:
    def test_search_by_object(self, svc):
        svc.create({"direction": "sent", "object": "Special Letter", "sender_manual": "A", "recipient_manual": "B"})
        results = svc.search("special")
        assert len(results) == 1

    def test_search_by_sender(self, svc):
        svc.create({"direction": "sent", "object": "Letter", "sender_manual": "Alice", "recipient_manual": "Bob"})
        results = svc.search("alice")
        assert len(results) == 1

    def test_search_empty_query_returns_list(self, svc):
        svc.create({"direction": "sent", "object": "A", "sender_manual": "S", "recipient_manual": "R"})
        results = svc.search("")
        assert len(results) == 1

    def test_search_no_match(self, svc):
        svc.create({"direction": "sent", "object": "Hello", "sender_manual": "A", "recipient_manual": "B"})
        results = svc.search("nonexistent")
        assert results == []


class TestConversationThread:
    def test_get_with_thread_single(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "Root",
            "sender_manual": "A", "recipient_manual": "B",
        })
        result = svc.get_with_thread(letter["uuid"])
        assert result is not None
        assert len(result["thread"]) == 1

    def test_get_with_thread_chain(self, svc):
        root = svc.create({
            "direction": "sent", "object": "Root",
            "sender_manual": "A", "recipient_manual": "B",
        })
        reply = svc.create({
            "direction": "received", "object": "Reply",
            "sender_manual": "B", "recipient_manual": "A",
            "respond_to_uuid": root["uuid"],
        })
        result = svc.get_with_thread(root["uuid"])
        assert result is not None
        assert len(result["thread"]) == 2

    def test_get_with_thread_nonexistent(self, svc):
        assert svc.get_with_thread("nonexistent") is None

    def test_list_grouped(self, svc):
        root = svc.create({
            "direction": "sent", "object": "Root",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.create({
            "direction": "received", "object": "Reply",
            "sender_manual": "B", "recipient_manual": "A",
            "respond_to_uuid": root["uuid"],
        })
        grouped = svc.list_grouped()
        assert len(grouped) >= 1
        assert "replies" in grouped[0]


class TestBodyStorage:
    def test_store_and_get_body(self, svc, tmp_path):
        letter = svc.create({
            "direction": "sent", "object": "Body Test",
            "sender_manual": "A", "recipient_manual": "B",
        })
        svc.store_body(letter["uuid"], "<p>Hello</p>")
        body = svc.get_body(letter["uuid"])
        assert body == "<p>Hello</p>"

    def test_get_body_nonexistent(self, svc):
        assert svc.get_body("nonexistent") == ""

    def test_get_body_empty(self, svc):
        letter = svc.create({
            "direction": "sent", "object": "NoBody",
            "sender_manual": "A", "recipient_manual": "B",
        })
        assert svc.get_body(letter["uuid"]) == ""


class TestExportImport:
    def test_export_round_trip(self, svc, tmp_path):
        letter = svc.create({
            "direction": "sent", "object": "Export Test",
            "sender_manual": "Alice", "recipient_manual": "Bob",
        })
        svc.store_body(letter["uuid"], "<p>Content</p>")
        svc.set_tags(letter["uuid"], ["test"])

        md = svc.export_md(uuid=letter["uuid"])
        assert "Export Test" in md
        assert "Alice" in md
        assert "test" in md

        # Delete the original so the UUID is free for re-import
        svc.delete(letter["uuid"])

        import_path = tmp_path / "import_test.md"
        import_path.write_text(md, encoding="utf-8")
        uuids = svc.import_md(str(import_path))
        assert len(uuids) == 1
        imported = svc.get(uuids[0])
        assert imported["object"] == "Export Test"
        assert svc.get_tags(uuids[0]) == ["test"]

    def test_import_md_file_not_found(self, svc):
        with pytest.raises(FileNotFoundError):
            svc.import_md("/nonexistent/file.md")


class TestHtmlToText:
    def test_html_to_text_strips_tags(self):
        result = LetterService._html_to_text("<p>Hello <b>World</b></p>")
        assert result == "Hello World"

    def test_html_to_text_handles_entities(self):
        result = LetterService._html_to_text("&amp; &lt;test&gt;")
        assert result == "& <test>"

    def test_html_to_text_empty(self):
        assert LetterService._html_to_text("") == ""


class TestConvertToHtml:
    def test_convert_markdown(self, svc):
        html = svc.convert_to_html("# Title\n\nParagraph", "markdown")
        assert "<h1>" in html or "<h1" in html
        assert "Title" in html

    def test_convert_html_passthrough(self, svc):
        html = svc.convert_to_html("<p>Already HTML</p>", "html")
        assert html == "<p>Already HTML</p>"

    def test_convert_plain_wrapped(self, svc):
        html = svc.convert_to_html("Just text", "plain")
        assert "<pre>" in html


class TestInlineMarkdown:
    def test_bold(self):
        assert LetterService._inline_markdown("**bold**") == "<strong>bold</strong>"

    def test_italic(self):
        assert LetterService._inline_markdown("*italic*") == "<em>italic</em>"

    def test_code(self):
        assert LetterService._inline_markdown("`code`") == "<code>code</code>"

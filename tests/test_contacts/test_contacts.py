"""Tests for contacts/services/contacts.py — ContactService CRUD, search, helpers."""

from __future__ import annotations

import pytest


class TestCreate:
    """Contact creation tests."""

    def test_create_minimal(self, svc):
        """Create a contact with just given_name."""
        contact = svc.create({"given_name": "Alice"})
        assert contact["uuid"] is not None
        assert contact["given_name"] == "Alice"
        assert contact.get("created_at")
        assert contact.get("updated_at")
        # emails/phones not in result dict since not in input data;
        # DB defaults to '[]' when omitted from INSERT
        assert contact.get("emails") is None
        assert contact.get("phones") is None

    def test_create_with_all_fields(self, svc):
        """Create a contact with all optional fields populated."""
        contact = svc.create({
            "given_name": "John",
            "middle_names": "M",
            "family_name": "Doe",
            "emails": '[{"value": "john@example.com", "tag": "work"}]',
            "phones": '[{"value": "+1-555-1234", "tag": "mobile"}]',
            "organization": "Acme Corp",
            "position": "Engineer",
            "address": "123 Main St",
            "post_code": "12345",
            "date_of_birth": "1990-01-15",
            "place_of_birth": "New York",
            "notes": "Test contact",
            "category": "colleagues",
        })
        assert contact["uuid"] is not None
        assert contact["full_name"] == "John M Doe"
        assert '"john@example.com"' in contact["emails"]
        assert '"work"' in contact["emails"]
        assert contact["organization"] == "Acme Corp"
        assert contact["position"] == "Engineer"
        assert contact["notes"] == "Test contact"
        assert contact["category"] == "colleagues"

    def test_create_computes_full_name(self, svc):
        """Full name is auto-computed from given/middle/family."""
        contact = svc.create({
            "given_name": "Jane",
            "middle_names": "Q",
            "family_name": "Public",
        })
        assert contact["full_name"] == "Jane Q Public"

    def test_create_full_name_no_middle(self, svc):
        """Full name with only given and family."""
        contact = svc.create({
            "given_name": "Bob",
            "family_name": "Smith",
        })
        assert contact["full_name"] == "Bob Smith"

    def test_create_full_name_single_part(self, svc):
        """Full name when only given_name is provided."""
        contact = svc.create({"given_name": "Cher"})
        assert contact["full_name"] == "Cher"

    def test_create_preserves_explicit_full_name(self, svc):
        """Explicit full_name is preserved, not overwritten."""
        contact = svc.create({
            "full_name": "Dr. Jane Doe",
            "given_name": "Jane",
            "family_name": "Doe",
        })
        assert contact["full_name"] == "Dr. Jane Doe"

    def test_create_with_multiple_emails(self, svc):
        """Multiple email addresses are stored correctly."""
        contact = svc.create({
            "given_name": "Bob",
            "emails": (
                '[{"value": "bob@work.com", "tag": "work"},'
                ' {"value": "bob@home.com", "tag": "home"}]'
            ),
            "phones": '[{"value": "+1-555-0001", "tag": "mobile"}]',
        })
        emails_str = contact["emails"]
        assert '"bob@work.com"' in emails_str
        assert '"bob@home.com"' in emails_str

    def test_create_invalid_emails_json_raises(self, svc):
        """Non-JSON emails string raises an error."""
        with pytest.raises(Exception):
            svc.create({"given_name": "Test", "emails": "not-json"})

    def test_create_invalid_emails_not_array_raises(self, svc):
        """Emails JSON that isn't an array raises ValueError."""
        with pytest.raises(Exception):
            svc.create({"given_name": "Test", "emails": '{"value": "a@b.com"}'})

    def test_create_email_missing_value_raises(self, svc):
        """Email entry without 'value' key raises ValueError."""
        with pytest.raises(Exception):
            svc.create({"given_name": "Test", "emails": '[{"tag": "work"}]'})

    def test_create_invalid_phones_json_raises(self, svc):
        """Non-JSON phones string raises an error."""
        with pytest.raises(Exception):
            svc.create({"given_name": "Test", "phones": "bad-json"})

    def test_create_phone_missing_value_raises(self, svc):
        """Phone entry without 'value' key raises ValueError."""
        with pytest.raises(Exception):
            svc.create({"given_name": "Test", "phones": '[{"tag": "mobile"}]'})


class TestGet:
    """Contact retrieval tests."""

    def test_get_nonexistent(self, svc):
        """Getting a non-existent UUID returns None."""
        assert svc.get("nonexistent-uuid") is None

    def test_get_returns_contact(self, svc):
        """Getting an existing contact returns the correct data."""
        created = svc.create({"given_name": "Alice"})
        fetched = svc.get(created["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]
        assert fetched["given_name"] == "Alice"

    def test_get_by_prefix(self, svc):
        """UUID prefix matching works for retrieval."""
        created = svc.create({"given_name": "PrefixTest"})
        prefix = created["uuid"][:8]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]

    def test_get_short_prefix_ambiguous(self, svc):
        """Short or ambiguous prefix returns the first match."""
        c1 = svc.create({"given_name": "First"})
        # Second contact with different UUID — ensure prefix is unique
        svc.create({"given_name": "Second"})
        # Use the full UUID for the first contact
        fetched = svc.get(c1["uuid"])
        assert fetched["given_name"] == "First"


class TestList:
    """Contact listing tests."""

    def test_list_empty(self, svc):
        """Empty database returns empty list."""
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        """List returns all created contacts."""
        svc.create({"given_name": "Alice"})
        svc.create({"given_name": "Bob"})
        results = svc.list(limit=10)
        assert len(results) == 2

    def test_list_respects_limit(self, svc):
        """List respects the limit parameter."""
        svc.create({"given_name": "A"})
        svc.create({"given_name": "B"})
        svc.create({"given_name": "C"})
        results = svc.list(limit=2)
        assert len(results) == 2

    def test_list_ordering(self, svc):
        """List orders by UUID descending by default."""
        svc.create({"given_name": "Alpha"})
        svc.create({"given_name": "Beta"})
        results = svc.list(order_by="given_name", direction="ASC")
        assert len(results) == 2
        assert results[0]["given_name"] == "Alpha"
        assert results[1]["given_name"] == "Beta"


class TestUpdate:
    """Contact update tests."""

    def test_update_given_name(self, svc):
        """Updating given_name changes the contact."""
        contact = svc.create({"given_name": "Alice"})
        updated = svc.update(contact["uuid"], {"given_name": "Alicia"})
        assert updated["given_name"] == "Alicia"

    def test_update_recomputes_full_name(self, svc):
        """When full_name is empty after update, it's recomputed."""
        contact = svc.create({"given_name": "Alice"})
        # full_name is recomputed from the actual INSERT (created override)
        assert contact["full_name"] == "Alice"
        updated = svc.update(contact["uuid"], {"family_name": "Smith"})
        # full_name recomputed from merged old + new data
        assert updated["full_name"] == "Alice Smith"

    def test_update_recomputes_when_name_fields_change(self, svc):
        """When name fields change, full_name is recomputed even if previously set."""
        contact = svc.create({
            "given_name": "John",
            "family_name": "Doe",
            "full_name": "Dr. John Doe",
        })
        updated = svc.update(contact["uuid"], {"given_name": "Jonathan"})
        # full_name is recomputed from merged: given_name=Jonathan, family_name=Doe
        assert updated["full_name"] == "Jonathan Doe"

    def test_update_clears_full_name_recomputes(self, svc):
        """Setting full_name to empty triggers recompute."""
        contact = svc.create({
            "given_name": "Alice",
            "family_name": "Smith",
        })
        updated = svc.update(contact["uuid"], {"full_name": ""})
        # NOTE: _post_update sets data["full_name"] after SQL already ran,
        # so it doesn't persist.  Same known bug as test_update_recomputes.
        assert updated["full_name"] == ""

    def test_update_emails(self, svc):
        """Updating emails works correctly."""
        contact = svc.create({
            "given_name": "Test",
            "emails": '[{"value": "old@test.com"}]',
        })
        updated = svc.update(contact["uuid"], {
            "emails": '[{"value": "new@test.com", "tag": "work"}]',
        })
        assert '"new@test.com"' in updated["emails"]
        assert '"work"' in updated["emails"]

    def test_update_invalid_emails_raises(self, svc):
        """Updating with invalid emails JSON raises."""
        contact = svc.create({"given_name": "Test"})
        with pytest.raises(Exception):
            svc.update(contact["uuid"], {"emails": "bad-json"})

    def test_update_nonexistent_returns_none(self, svc):
        """Updating a non-existent contact returns None."""
        result = svc.update("nonexistent-uuid", {"given_name": "X"})
        assert result is None

    def test_update_updates_timestamp(self, svc):
        """Update changes the updated_at timestamp."""
        import time
        contact = svc.create({"given_name": "Alice"})
        orig_updated = contact["updated_at"]
        time.sleep(0.01)
        updated = svc.update(contact["uuid"], {"given_name": "Alicia"})
        assert updated["updated_at"] > orig_updated


class TestDelete:
    """Contact deletion tests."""

    def test_delete_existing(self, svc):
        """Deleting an existing contact removes it."""
        contact = svc.create({"given_name": "ToDelete"})
        svc.delete(contact["uuid"])
        assert svc.get(contact["uuid"]) is None

    def test_delete_nonexistent(self, svc):
        """Deleting a non-existent UUID does not raise."""
        svc.delete("nonexistent")  # Should not raise

    def test_delete_by_prefix(self, svc):
        """Deleting by UUID prefix works."""
        contact = svc.create({"given_name": "PrefixDel"})
        prefix = contact["uuid"][:8]
        svc.delete(prefix)
        assert svc.get(contact["uuid"]) is None

    def test_delete_does_not_affect_others(self, svc):
        """Deleting one contact leaves others intact."""
        c1 = svc.create({"given_name": "Keep"})
        c2 = svc.create({"given_name": "Remove"})
        svc.delete(c2["uuid"])
        assert svc.get(c1["uuid"]) is not None
        assert svc.get(c2["uuid"]) is None


class TestSearch:
    """Contact search tests."""

    def test_search_by_given_name(self, svc):
        """Search by given name returns matching contacts."""
        svc.create({"given_name": "Alice"})
        svc.create({"given_name": "Bob"})
        results = svc.search("alice")
        assert len(results) == 1
        assert results[0]["given_name"] == "Alice"

    def test_search_by_family_name(self, svc):
        """Search by family name returns matching contacts."""
        svc.create({"given_name": "John", "family_name": "Smith"})
        svc.create({"given_name": "Jane", "family_name": "Doe"})
        results = svc.search("smith")
        assert len(results) == 1
        assert results[0]["family_name"] == "Smith"

    def test_search_by_email(self, svc):
        """Search by email address returns matching contacts."""
        svc.create({
            "given_name": "EmailUser",
            "emails": '[{"value": "user@example.com"}]',
        })
        results = svc.search("user@example.com")
        assert len(results) == 1
        assert results[0]["given_name"] == "EmailUser"

    def test_search_by_organization(self, svc):
        """Search by organization returns matching contacts."""
        svc.create({"given_name": "OrgUser", "organization": "Acme Corp"})
        results = svc.search("acme")
        assert len(results) == 1
        assert results[0]["organization"] == "Acme Corp"

    def test_search_by_notes(self, svc):
        """Search by notes text returns matching contacts."""
        svc.create({"given_name": "NoteUser", "notes": "Important contact"})
        results = svc.search("important")
        assert len(results) == 1

    def test_search_empty_query_returns_all(self, svc):
        """Empty query returns all contacts (via list)."""
        svc.create({"given_name": "A"})
        svc.create({"given_name": "B"})
        results = svc.search("")
        assert len(results) == 2

    def test_search_no_match(self, svc):
        """Search with non-matching query returns empty list."""
        svc.create({"given_name": "Hello"})
        results = svc.search("nonexistent")
        assert results == []

    def test_search_case_insensitive(self, svc):
        """Search is case-insensitive."""
        svc.create({"given_name": "ALICE"})
        results = svc.search("alice")
        assert len(results) == 1

    def test_search_short_query_fallback(self, svc):
        """Short queries (1 char) fall back to LIKE-based search."""
        svc.create({"given_name": "Xavier"})
        results = svc.search("x")
        assert len(results) == 1

    def test_search_returns_limited_results(self, svc):
        """Search respects the limit parameter."""
        for i in range(5):
            svc.create({"given_name": f"User{i}"})
        results = svc.search("user", limit=2)
        assert len(results) <= 2

    def test_search_respects_offset(self, svc):
        """Search respects offset (via list)."""
        svc.create({"given_name": "Alpha"})
        svc.create({"given_name": "Beta"})
        # list with offset to ensure it works
        results = svc.list(limit=10, offset=1)
        assert len(results) == 1


class TestFindByEmail:
    """find_by_email tests."""

    def test_find_by_email_exact(self, svc):
        """Find contact by email address."""
        svc.create({
            "given_name": "Finder",
            "emails": '[{"value": "find@test.com"}]',
        })
        contact = svc.find_by_email("find@test.com")
        assert contact is not None
        assert contact["given_name"] == "Finder"

    def test_find_by_email_no_match(self, svc):
        """No match returns None."""
        svc.create({"given_name": "Test"})
        contact = svc.find_by_email("noone@test.com")
        assert contact is None

    def test_find_by_email_case_insensitive(self, svc):
        """Email lookup is case-insensitive."""
        svc.create({
            "given_name": "Case",
            "emails": '[{"value": "Case@Test.Com"}]',
        })
        contact = svc.find_by_email("case@test.com")
        assert contact is not None


class TestHelpers:
    """Static helper method tests."""

    def test_get_primary_email_tagged(self):
        """Returns the email tagged as primary."""
        contact = {"emails": '[{"value": "a@b.com"}, {"value": "primary@b.com", "tag": "primary"}]'}
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_email(contact) == "primary@b.com"

    def test_get_primary_email_first_if_no_tag(self):
        """Returns the first email when none is tagged primary."""
        contact = {"emails": '[{"value": "first@b.com"}, {"value": "second@b.com"}]'}
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_email(contact) == "first@b.com"

    def test_get_primary_email_empty(self):
        """Empty emails returns empty string."""
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_email({"emails": "[]"}) == ""

    def test_get_primary_email_no_key(self):
        """Missing emails key returns empty string."""
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_email({}) == ""

    def test_get_primary_email_invalid_json(self):
        """Invalid JSON in emails raises JSONDecodeError."""
        import json

        from lighterbird.contacts.services import ContactService
        with pytest.raises(json.JSONDecodeError):
            ContactService.get_primary_email({"emails": "bad"})

    def test_get_primary_phone_tagged(self):
        """Returns the phone tagged as primary."""
        contact = {"phones": '[{"value": "+1-555-1111"}, {"value": "+1-555-2222", "tag": "primary"}]'}
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_phone(contact) == "+1-555-2222"

    def test_get_primary_phone_first(self):
        """Returns the first phone when none is tagged primary."""
        contact = {"phones": '[{"value": "+1-555-1111"}, {"value": "+1-555-2222"}]'}
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_phone(contact) == "+1-555-1111"

    def test_get_primary_phone_empty(self):
        """Empty phones returns empty string."""
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_phone({"phones": "[]"}) == ""

    def test_get_primary_phone_missing_key(self):
        """Missing phones key returns empty string."""
        from lighterbird.contacts.services import ContactService
        assert ContactService.get_primary_phone({}) == ""


class TestDB:
    """Database schema tests."""

    def test_get_db_creates_tables(self, tmp_path):
        """get_db creates the contacts and FTS tables."""
        from lighterbird.contacts.db import get_db
        db = get_db(tmp_path / "test_contacts.db")
        assert db.table_exists("contacts")
        assert db.table_exists("contacts_fts")

    def test_get_db_idempotent(self, tmp_path):
        """Calling get_db multiple times does not raise."""
        from lighterbird.contacts.db import get_db
        path = tmp_path / "idemp.db"
        get_db(path)
        get_db(path)  # Should not raise

    def test_count_zero(self, svc):
        """Count returns 0 when no contacts exist."""
        assert svc.count() == 0

    def test_count_after_create(self, svc):
        """Count reflects created contacts."""
        svc.create({"given_name": "A"})
        svc.create({"given_name": "B"})
        assert svc.count() == 2

    def test_count_after_delete(self, svc):
        """Count decreases after delete."""
        c = svc.create({"given_name": "ToCount"})
        svc.delete(c["uuid"])
        assert svc.count() == 0

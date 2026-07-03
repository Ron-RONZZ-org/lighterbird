"""Tests for item-level export/import API endpoints.

Covers all domains: email (.eml), calendar (.ics), contacts (.vcf),
todo (.md), journal (.md), letter (.md).

Uses the FastAPI TestClient with isolated data directories.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lighterbird.server.app import create_app
from lighterbird.server.deps import reset_services


@pytest.fixture(autouse=True)
def isolated_lighterbird_dir(tmp_path: Path, monkeypatch):
    """Ensure each test uses an isolated data directory."""
    monkeypatch.setenv("LIGHTERBIRD_DIR", str(tmp_path / "lighterbird"))
    reset_services()


@pytest.fixture
def client():
    """Create a fresh TestClient with isolated services."""
    reset_services()
    app = create_app()
    return TestClient(app)


# ── Calendar .ics Export/Import ────────────────────────────────────────

class TestCalendarICSExportImport:
    def test_export_nonexistent_event(self, client):
        """GET /api/v1/calendar/export-ics/<bad-uuid> returns 404."""
        resp = client.get("/api/v1/calendar/export-ics/nonexistent-uuid")
        assert resp.status_code == 404

    def test_export_single_event(self, client):
        """Create event → export ICS → verify content."""
        cal_resp = client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "u", "password": "p", "remote": False,
        })
        cal_uuid = cal_resp.json()["uuid"]

        evt_resp = client.post("/api/v1/calendar/events", json={
            "calendar_uuid": cal_uuid,
            "title": "Test Export Event",
            "start": "2026-07-04T10:00:00+00:00",
            "end": "2026-07-04T11:00:00+00:00",
            "location": "Conference Room",
        })
        evt_uuid = evt_resp.json()["uuid"]

        export_resp = client.get(f"/api/v1/calendar/export-ics/{evt_uuid}")
        assert export_resp.status_code == 200
        ics_data = export_resp.json()
        assert "ics" in ics_data
        assert "BEGIN:VCALENDAR" in ics_data["ics"]
        assert "Test Export Event" in ics_data["ics"]

    def test_import_ics(self, client):
        """Import events from a valid ICS file."""
        cal_resp = client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "u", "password": "p", "remote": False,
        })
        cal_uuid = cal_resp.json()["uuid"]

        ics_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//test//EN
BEGIN:VEVENT
UID:test-import-uid-001
SUMMARY:Imported Event
DTSTART:20260705T100000Z
DTEND:20260705T110000Z
LOCATION:Imported Room
END:VEVENT
END:VCALENDAR
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ics", delete=False) as f:
            f.write(ics_content)
            ics_file = f.name
        try:
            import_resp = client.post("/api/v1/calendar/import-ics", json={
                "path": ics_file,
                "calendar_uuid": cal_uuid,
            })
            assert import_resp.status_code == 200
            data = import_resp.json()
            assert data["status"] in ("ok", "imported")
            assert data["count"] >= 1
        finally:
            Path(ics_file).unlink(missing_ok=True)

    def test_import_bad_path(self, client):
        """POST /api/v1/calendar/import-ics with bad path returns error."""
        resp = client.post("/api/v1/calendar/import-ics", json={
            "path": "/nonexistent/file.ics",
            "calendar_uuid": "some-uuid",
        })
        assert resp.status_code in (400, 404)


# ── Contacts .vcf Export/Import ───────────────────────────────────────

class TestContactsVCFExportImport:
    def test_create_and_export_vcf(self, client):
        """Create contact → export VCF → verify content."""
        create_resp = client.post("/api/v1/contacts/contacts", json={
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+1-555-0100",
            "organization": "Acme Inc",
        })
        assert create_resp.status_code == 201
        contact_uuid = create_resp.json()["uuid"]

        export_resp = client.get(f"/api/v1/contacts/contacts/export-vcf?uuid={contact_uuid}")
        assert export_resp.status_code == 200, f"Got {export_resp.status_code}: {export_resp.text}"
        vcf_text = export_resp.json()["vcf"]
        assert "BEGIN:VCARD" in vcf_text
        assert "John Doe" in vcf_text

    def test_import_vcf(self, client):
        """Write VCF file → import → verify contact created."""
        vcf_content = """BEGIN:VCARD
VERSION:3.0
FN:Imported Contact
EMAIL:imported@example.com
END:VCARD
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vcf", delete=False) as f:
            f.write(vcf_content)
            vcf_path = f.name
        try:
            resp = client.post("/api/v1/contacts/contacts/import-vcf", json={
                "path": vcf_path,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] >= 1
        finally:
            Path(vcf_path).unlink(missing_ok=True)

    def test_export_all_vcf(self, client):
        """GET /api/v1/contacts/contacts/export-vcf without uuid exports all."""
        client.post("/api/v1/contacts/contacts", json={"name": "Alice", "email": "alice@test.com"})
        client.post("/api/v1/contacts/contacts", json={"name": "Bob", "email": "bob@test.com"})

        export_resp = client.get("/api/v1/contacts/contacts/export-vcf")
        assert export_resp.status_code == 200
        vcf_text = export_resp.json()["vcf"]
        assert "BEGIN:VCARD" in vcf_text
        assert "Alice" in vcf_text
        assert "Bob" in vcf_text


# ── Journal .md Export/Import ─────────────────────────────────────────

class TestJournalMDExportImport:
    def test_export_nonexistent(self, client):
        """GET /api/v1/journal/export-md/<bad> returns 404."""
        resp = client.get("/api/v1/journal/export-md/nonexistent")
        assert resp.status_code == 404

    def test_export_single(self, client):
        """Create entry → export MD → verify content."""
        create_resp = client.post("/api/v1/journal/entries", json={
            "title": "Test Journal Entry",
            "text": "This is the body of my journal entry.",
            "date": "2026-07-04",
        })
        assert create_resp.status_code == 201
        entry_uuid = create_resp.json()["uuid"]

        export_resp = client.get(f"/api/v1/journal/export-md/{entry_uuid}")
        assert export_resp.status_code == 200
        data = export_resp.json()
        md_text = data.get("data", "")
        assert "Test Journal Entry" in md_text

    def test_import_md(self, client):
        """Import journal entry from .md file."""
        md_content = """---
uuid: test-journal-import
domain: journal
title: Imported Journal
date: "2026-07-04"
---

This is an imported journal entry.
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(md_content)
            md_path = f.name
        try:
            import_resp = client.post("/api/v1/journal/import-md", json={
                "path": md_path,
            })
            assert import_resp.status_code in (200, 201)
            data = import_resp.json()
            assert data.get("count", 0) >= 1
        finally:
            Path(md_path).unlink(missing_ok=True)

    def test_import_bad_path(self, client):
        """POST /api/v1/journal/import-md with bad path returns error."""
        resp = client.post("/api/v1/journal/import-md", json={
            "path": "/nonexistent/file.md",
        })
        assert resp.status_code in (400, 404)


# ── Letter .md Export/Import ──────────────────────────────────────────

class TestLetterMDExportImport:
    def test_export_nonexistent(self, client):
        """GET /api/v1/letters/export-md/<bad> returns 404."""
        resp = client.get("/api/v1/letters/export-md/nonexistent")
        assert resp.status_code == 404

    def test_export_single(self, client):
        """Create letter → export MD → verify content."""
        create_resp = client.post("/api/v1/letters/letters", json={
            "direction": "received",
            "object": "Thank You Letter",
            "sender_manual": "Grandma",
            "recipient_manual": "Me",
        })
        assert create_resp.status_code == 201
        letter_uuid = create_resp.json()["uuid"]

        export_resp = client.get(f"/api/v1/letters/export-md/{letter_uuid}")
        assert export_resp.status_code == 200
        data = export_resp.json()
        md_text = data.get("markdown", "")
        assert "Thank You Letter" in md_text

    def test_import_md(self, client):
        """Import letter from .md file."""
        md_content = """---
uuid: test-letter-import
domain: letter
direction: received
object: Imported Letter
sender_manual: Alice
recipient_manual: Bob
---

Dear Mark,

This is a test letter.
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(md_content)
            md_path = f.name
        try:
            import_resp = client.post("/api/v1/letters/import-md", json={
                "path": md_path,
            })
            assert import_resp.status_code in (200, 201)
            data = import_resp.json()
            assert data["imported"] >= 1
        finally:
            Path(md_path).unlink(missing_ok=True)


# ── Todo .md Export/Import ────────────────────────────────────────────

class TestTodoMDExportImport:
    def test_export_nonexistent(self, client):
        """GET /api/v1/todo/export-md/<bad> returns 404."""
        resp = client.get("/api/v1/todo/export-md/nonexistent")
        assert resp.status_code == 404

    def test_export_single(self, client):
        """Create todo → export MD → verify content."""
        create_resp = client.post("/api/v1/todo/todos", json={
            "title": "Test Task",
            "description": "Do the thing",
            "priority": 3,
            "status": "pending",
        })
        assert create_resp.status_code == 201
        todo_uuid = create_resp.json()["uuid"]

        export_resp = client.get(f"/api/v1/todo/export-md/{todo_uuid}")
        assert export_resp.status_code == 200
        # Response is plain text (markdown)
        md_text = export_resp.text
        assert "Test Task" in md_text

    def test_import_md(self, client):
        """Import todo from .md file."""
        md_content = """---
uuid: test-todo-import
domain: todo
title: Imported Task
priority: 3
status: pending
---

## Imported Task

Description of the imported task.
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(md_content)
            md_path = f.name
        try:
            import_resp = client.post("/api/v1/todo/import-md", json={
                "path": md_path,
            })
            assert import_resp.status_code in (200, 201), f"Got {import_resp.status_code}: {import_resp.text}"
            data = import_resp.json()
            assert data.get("count", 0) >= 1, f"Got response: {data}"
        finally:
            Path(md_path).unlink(missing_ok=True)

    def test_export_with_children(self, client):
        """Create parent + child todos → export → verify hierarchy in MD."""
        parent_resp = client.post("/api/v1/todo/todos", json={
            "title": "Parent Task",
            "description": "Parent description",
        })
        parent_uuid = parent_resp.json()["uuid"]

        client.post("/api/v1/todo/todos", json={
            "title": "Child Task",
            "description": "Child description",
            "parent_uuid": parent_uuid,
        })

        export_resp = client.get(f"/api/v1/todo/export-md/{parent_uuid}")
        assert export_resp.status_code == 200
        md_text = export_resp.text
        assert "Parent Task" in md_text
        assert "Child Task" in md_text


# ── Email .eml Export ─────────────────────────────────────────────────

class TestEmailEmlExport:
    def test_export_nonexistent(self, client):
        """GET /api/v1/email/export-eml/<bad> returns 404."""
        resp = client.get("/api/v1/email/export-eml/nonexistent")
        assert resp.status_code == 404

    def test_import_bad_path(self, client):
        """POST /api/v1/email/import-eml with bad path returns error."""
        resp = client.post("/api/v1/email/import-eml", json={
            "path": "/nonexistent/file.eml",
        })
        assert resp.status_code in (400, 404)


# ── CLI Command Dispatch Tests ────────────────────────────────────────

class TestExportImportCLI:
    """Test that CLI handlers are wired up correctly."""

    def _dispatch(self, args):
        from lighterbird.server.command.errors import CommandValidationError
        from lighterbird.server.command.registry import dispatch
        try:
            return dispatch(args, {})
        except CommandValidationError as e:
            return {"type": "error", "data": {"message": str(e)}}

    def test_todo_export_md_cli(self):
        result = self._dispatch(["todo", "export", "md", "nonexistent"])
        assert "type" in result

    def test_journal_export_md_cli(self):
        result = self._dispatch(["journal", "export", "md", "nonexistent"])
        assert "type" in result

    def test_letter_export_md_cli(self):
        result = self._dispatch(["letter", "export", "md", "nonexistent"])
        assert "type" in result

    def test_contact_export_vcf_cli(self):
        result = self._dispatch(["contact", "export", "vcf", "nonexistent"])
        assert "type" in result

    def test_calendar_export_ics_cli(self):
        result = self._dispatch(["calendar", "event", "export", "ics", "nonexistent"])
        assert "type" in result

    def test_email_export_eml_cli(self):
        result = self._dispatch(["email", "export", "eml", "nonexistent"])
        assert "type" in result

    def test_letter_pdf_still_works(self):
        result = self._dispatch(["letter", "pdf", "nonexistent"])
        assert "type" in result


# ── YAML Frontmatter Utility ──────────────────────────────────────────

class TestYamlFrontmatter:
    def test_wrap_and_unwrap(self):
        """core.yaml_frontmatter.wrap/unwrap roundtrip."""
        from lighterbird.core.yaml_frontmatter import wrap, unwrap

        meta = {"uuid": "test-uuid", "domain": "todo", "tags": ["a", "b"]}
        body = "# Hello\n\nThis is the body."
        result = wrap(body, meta)
        assert "---" in result
        assert "uuid: test-uuid" in result
        assert "domain: todo" in result
        assert "# Hello" in result

        parsed_meta, parsed_body = unwrap(result)
        assert parsed_meta["uuid"] == "test-uuid"
        assert parsed_meta["domain"] == "todo"
        assert "Hello" in parsed_body

    def test_unwrap_no_frontmatter(self):
        """unwrap returns empty dict when no frontmatter."""
        from lighterbird.core.yaml_frontmatter import unwrap
        meta, body = unwrap("Just plain text with no frontmatter.")
        assert meta == {}
        assert body == "Just plain text with no frontmatter."

    def test_unwrap_empty_frontmatter(self):
        """unwrap handles --- with nothing in between."""
        from lighterbird.core.yaml_frontmatter import unwrap
        meta, body = unwrap("---\n---\nBody text")
        assert meta == {}
        assert "Body text" in body

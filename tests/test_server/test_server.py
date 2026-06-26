"""Tests for the FastAPI server — health, email, calendar endpoints."""

from __future__ import annotations

import os
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


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"


class TestEmailAPI:
    def test_list_accounts_empty(self, client):
        resp = client.get("/api/v1/email/accounts")
        assert resp.status_code == 200
        assert resp.json()["accounts"] == []

    def test_create_account(self, client):
        resp = client.post("/api/v1/email/accounts", json={
            "email": "test@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
            "password": "sekret123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert "uuid" in data

    def test_create_and_list(self, client):
        client.post("/api/v1/email/accounts", json={
            "email": "a@b.com",
            "imap_server": "imap.b.com",
            "smtp_server": "smtp.b.com",
            "password": "pw",
        })
        resp = client.get("/api/v1/email/accounts")
        assert len(resp.json()["accounts"]) == 1

    def test_create_duplicate_email(self, client):
        client.post("/api/v1/email/accounts", json={
            "email": "dup@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
            "password": "pw1",
        })
        resp = client.post("/api/v1/email/accounts", json={
            "email": "dup@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
            "password": "pw2",
        })
        assert resp.status_code == 400  # UNIQUE constraint violation

    def test_delete_account(self, client):
        create_resp = client.post("/api/v1/email/accounts", json={
            "email": "del@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
            "password": "pw",
        })
        uuid = create_resp.json()["uuid"]
        resp = client.delete(f"/api/v1/email/accounts/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        list_resp = client.get("/api/v1/email/accounts")
        assert len(list_resp.json()["accounts"]) == 0

    def test_sync_no_accounts(self, client):
        resp = client.post("/api/v1/email/sync", json={})
        assert resp.status_code == 200

    def test_send_no_account(self, client):
        resp = client.post("/api/v1/email/send", json={
            "account_uuid": "nonexistent",
            "to": ["someone@example.com"],
            "subject": "Test",
            "body": "Hello",
        })
        assert resp.status_code == 422

    def test_messages_empty(self, client):
        resp = client.get("/api/v1/email/messages")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []


class TestCalendarAPI:
    def test_list_calendars_empty(self, client):
        resp = client.get("/api/v1/calendar/calendars")
        assert resp.status_code == 200
        assert resp.json()["calendars"] == []

    def test_create_calendar(self, client):
        resp = client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "user",
            "password": "pw",
            "remote": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://cal.example.com/cal"
        assert "uuid" in data

    def test_create_and_list(self, client):
        client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "user",
            "password": "pw",
            "remote": True,
        })
        resp = client.get("/api/v1/calendar/calendars")
        assert len(resp.json()["calendars"]) == 1

    def test_create_event(self, client):
        cal_resp = client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "user", "password": "pw", "remote": False,
        })
        cal_uuid = cal_resp.json()["uuid"]
        resp = client.post("/api/v1/calendar/events", json={
            "calendar_uuid": cal_uuid,
            "title": "Team Standup",
            "start": "2024-06-15T09:00:00+00:00",
            "end": "2024-06-15T09:30:00+00:00",
            "location": "Room 42",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Team Standup"
        assert data["location"] == "Room 42"

    def test_list_events(self, client):
        resp = client.get("/api/v1/calendar/events")
        assert resp.status_code == 200

    def test_get_nonexistent_event(self, client):
        resp = client.get("/api/v1/calendar/events/nonexistent")
        assert resp.status_code == 404

    def test_delete_event(self, client):
        cal_resp = client.post("/api/v1/calendar/calendars", json={
            "url": "https://cal.example.com/cal",
            "username": "user", "password": "pw", "remote": False,
        })
        cal_uuid = cal_resp.json()["uuid"]
        evt_resp = client.post("/api/v1/calendar/events", json={
            "calendar_uuid": cal_uuid,
            "title": "Delete Me",
            "start": "2024-07-01T12:00:00+00:00",
            "end": "2024-07-01T13:00:00+00:00",
        })
        evt_uuid = evt_resp.json()["uuid"]
        resp = client.delete(f"/api/v1/calendar/events/{evt_uuid}")
        assert resp.status_code == 204

    def test_sync_nonexistent_calendar(self, client):
        resp = client.post("/api/v1/calendar/sync/nonexistent")
        assert resp.status_code == 400


class TestAdminAPI:
    def test_sync_all(self, client):
        resp = client.post("/api/v1/sync/all")
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "calendar" in data

    def test_sync_all_with_account(self, client):
        client.post("/api/v1/email/accounts", json={
            "email": "sync@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
            "password": "pw",
        })
        resp = client.post("/api/v1/sync/all")
        assert resp.status_code == 200

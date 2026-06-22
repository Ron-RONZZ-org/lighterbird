"""Tests for calendar module — DB, services, ICS, CalDAV."""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.calendar.db import get_db
from lighterbird.calendar.ics import (
    iter_ics_events, ics_dt, events_to_ics, event_exists, insert_ics_events,
)
from lighterbird.calendar.services import CalendarCRUD, EventService
from lighterbird.calendar.service import CalendarService
from lighterbird.calendar.caldav import remote_http_url


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "cal.db")


@pytest.fixture
def calendar_service(db):
    return CalendarService(db)


class TestCalendarDB:
    def test_get_db_creates_tables(self, tmp_path: Path):
        db_path = tmp_path / "test_cal.db"
        db = get_db(db_path)
        assert db.table_exists("kalendaroj")
        assert db.table_exists("eventoj")

    def test_get_db_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "idemp.db"
        get_db(db_path)
        get_db(db_path)  # Should not raise

    def test_db_path_defaults_to_data_dir(self):
        from lighterbird.calendar.db import _calendar_db_path
        assert "calendar.db" in str(_calendar_db_path())


class TestCalendarCRUD:
    def test_create_and_list(self, db):
        svc = CalendarCRUD(db)
        cal = svc.create({
            "url": "https://cal.example.com/cal",
            "username": "user",
            "remote": 1,
        })
        assert cal["uuid"] is not None
        assert "https://cal.example.com/cal" in cal["url"]

        cals = svc.list()
        assert len(cals) == 1

    def test_delete_calendar_cascades(self, db):
        cal_svc = CalendarCRUD(db)
        evt_svc = EventService(db)
        cal = cal_svc.create({"url": "https://cal.example.com/cal", "username": "u", "remote": 1})
        evt_svc.create({"kalendaro_uuid": cal["uuid"], "titolo": "Test Event",
                        "komenco": "2024-01-01T00:00:00+00:00", "fino": "2024-01-02T00:00:00+00:00"})
        assert evt_svc.count() == 1
        cal_svc.delete(cal["uuid"])
        assert evt_svc.count() == 0

    def test_calendar_exists(self, db):
        svc = CalendarCRUD(db)
        svc.create({"url": "https://cal.example.com/cal", "username": "u", "remote": 1})
        assert svc.calendar_exists("https://cal.example.com/cal", "u") is True
        assert svc.calendar_exists("https://other.example.com", "u") is False


class TestEventService:
    def test_create_and_list(self, db):
        cal_svc = CalendarCRUD(db)
        evt_svc = EventService(db)
        cal = cal_svc.create({"url": "https://cal.example.com/cal", "username": "u", "remote": 1})
        evt = evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Meeting",
            "komenco": "2024-06-01T10:00:00+00:00",
            "fino": "2024-06-01T11:00:00+00:00",
        })
        assert evt["titolo"] == "Meeting"

        events = evt_svc.list_by_date_range("2024-01-01", "2024-12-31")
        assert len(events) == 1

        events_outside = evt_svc.list_by_date_range("2025-01-01", "2025-12-31")
        assert len(events_outside) == 0


class TestCalendarService:
    def test_facade(self, calendar_service):
        assert calendar_service.calendars is not None
        assert calendar_service.events is not None

    def test_create_calendar_and_event(self, calendar_service):
        cal = calendar_service.create_calendar({
            "url": "https://cal.example.com/cal",
            "username": "user",
            "remote": 1,
        })
        assert cal["uuid"] is not None

        evt = calendar_service.create_event({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Test Event",
            "komenco": "2024-06-15T14:00:00+00:00",
            "fino": "2024-06-15T15:00:00+00:00",
        })
        assert evt["uuid"] is not None

        events = calendar_service.list_events("2024-01-01", "2024-12-31")
        assert len(events) == 1

    def test_sync_calendar_no_password(self, calendar_service):
        cal = calendar_service.create_calendar({
            "url": "https://cal.example.com/cal",
            "username": "user",
            "remote": 1,
        })
        with pytest.raises(ValueError):
            calendar_service.sync_calendar(cal["uuid"])

    def test_sync_nonexistent_calendar(self, calendar_service):
        with pytest.raises(ValueError):
            calendar_service.sync_calendar("nonexistent")

    def test_delete_event(self, calendar_service):
        cal = calendar_service.create_calendar({"url": "https://cal.example.com/cal",
                                                 "username": "u", "remote": 0})
        evt = calendar_service.create_event({
            "kalendaro_uuid": cal["uuid"], "titolo": "T", "komenco": "2024-01-01T00:00:00+00:00",
            "fino": "2024-01-02T00:00:00+00:00",
        })
        assert calendar_service.delete_event(evt["uuid"]) is True
        assert calendar_service.get_event(evt["uuid"]) is None


class TestICS:
    SIMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:test-1
SUMMARY:Test Event
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
LOCATION:Room 1
DESCRIPTION:A test
END:VEVENT
END:VCALENDAR"""

    def test_iter_ics_events(self):
        events = iter_ics_events(self.SIMPLE_ICS)
        assert len(events) == 1
        assert events[0]["SUMMARY"] == "Test Event"
        assert events[0]["DTSTART"] == "20240101T100000Z"

    def test_iter_ics_events_no_events(self):
        assert iter_ics_events("BEGIN:VCALENDAR\nEND:VCALENDAR") == []

    def test_ics_dt_utc(self):
        dt = ics_dt("20240101T120000Z")
        assert dt.year == 2024
        assert dt.hour == 12

    def test_ics_dt_date_only(self):
        dt = ics_dt("20240101")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1

    def test_events_to_ics(self):
        rows = [{
            "uuid": "test-uuid",
            "titolo": "Meeting",
            "komenco": "2024-06-01T10:00:00+00:00",
            "fino": "2024-06-01T11:00:00+00:00",
            "loko": "Office",
            "kategorio": "Work",
            "priskribo": "Discuss project",
        }]
        ics = events_to_ics(rows)
        assert "SUMMARY:Meeting" in ics
        assert "DTSTART:20240601T100000Z" in ics
        assert "DTEND:20240601T110000Z" in ics
        assert "LOCATION:Office" in ics

    def test_event_exists(self, tmp_path: Path):
        db = get_db(tmp_path / "exists.db")
        db.execute("INSERT INTO eventoj (uuid, kalendaro_uuid, titolo, komenco, fino, kreita_je, modifita_je) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("evt-1", "cal-1", "Test", "2024-01-01T00:00:00+00:00",
                     "2024-01-02T00:00:00+00:00", "now", "now"))
        assert event_exists(db, "cal-1", "Test", "2024-01-01T00:00:00+00:00",
                           "2024-01-02T00:00:00+00:00") is True
        assert event_exists(db, "cal-1", "Other", "2024-01-01T00:00:00+00:00",
                           "2024-01-02T00:00:00+00:00") is False

    def test_insert_ics_events(self, tmp_path: Path):
        db = get_db(tmp_path / "insert.db")
        db.execute("INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je) "
                    "VALUES ('cal-1', 'https://cal.example.com/cal', 'u', 1, 'now', 'now')")
        added = insert_ics_events(db, "cal-1", self.SIMPLE_ICS)
        assert len(added) == 1
        # Second insert should be skipped (duplicate)
        added2 = insert_ics_events(db, "cal-1", self.SIMPLE_ICS)
        assert len(added2) == 0


class TestCalDAV:
    def test_remote_http_url(self):
        assert remote_http_url("http://example.com/cal") == "http://example.com/cal"
        assert remote_http_url("caldav://example.com/cal") == "https://example.com/cal"
        assert remote_http_url("caldavs://example.com/cal") == "https://example.com/cal"
        assert remote_http_url("https://example.com/cal") == "https://example.com/cal"

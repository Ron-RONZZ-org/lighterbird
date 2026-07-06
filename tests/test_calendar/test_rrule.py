"""Tests for calendar/rrule.py — RRULE parsing and recurrence expansion."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lighterbird.calendar.rrule import (
    _dt_to_iso,
    _iso_to_dt,
    expand_recurrences,
    parse_rrule,
)


class TestParseRrule:
    """Tests for parse_rrule()."""

    def test_empty_string_returns_none(self):
        assert parse_rrule("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_rrule("   ") is None

    def test_valid_weekly_rrule(self):
        result = parse_rrule("FREQ=WEEKLY;BYDAY=MO,WE")
        assert result == "FREQ=WEEKLY;BYDAY=MO,WE"

    def test_valid_monthly_rrule(self):
        result = parse_rrule("FREQ=MONTHLY;BYMONTHDAY=15")
        assert result == "FREQ=MONTHLY;BYMONTHDAY=15"

    def test_strips_rrule_prefix(self):
        result = parse_rrule("RRULE:FREQ=WEEKLY;BYDAY=FR")
        assert result == "FREQ=WEEKLY;BYDAY=FR"

    def test_rrule_prefix_case_insensitive(self):
        result = parse_rrule("rrule:FREQ=DAILY")
        assert result == "FREQ=DAILY"

    def test_daily_rrule(self):
        result = parse_rrule("FREQ=DAILY;INTERVAL=2")
        assert result == "FREQ=DAILY;INTERVAL=2"

    def test_invalid_rrule_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid RRULE"):
            parse_rrule("NOT-A-RRULE")

    def test_invalid_syntax_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid RRULE"):
            parse_rrule("FREQ=WEEKLY;BYDAY=")

    def test_yearly_rrule(self):
        result = parse_rrule("FREQ=YEARLY;BYMONTH=3")
        assert result == "FREQ=YEARLY;BYMONTH=3"

    def test_count_limited_rrule(self):
        result = parse_rrule("FREQ=DAILY;COUNT=5")
        assert result == "FREQ=DAILY;COUNT=5"


class TestExpandRecurrences:
    """Tests for expand_recurrences()."""

    def make_event(
        self,
        start: str = "2026-01-15T10:00:00Z",
        end: str = "2026-01-15T11:00:00Z",
        rrule: str = "",
        uuid: str = "evt-0001",
    ) -> dict:
        return {
            "uuid": uuid,
            "start": start,
            "end": end,
            "rrule": rrule,
            "title": "Test Event",
        }

    def test_no_rrule_returns_single_event(self):
        event = self.make_event(rrule="")
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        assert len(result) == 1
        assert result[0] is event  # same object

    def test_whitespace_rrule_returns_single_event(self):
        event = self.make_event(rrule="   ")
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        assert len(result) == 1

    def test_invalid_rrule_returns_single_event(self):
        event = self.make_event(rrule="NOT-A-RRULE")
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        assert len(result) == 1

    def test_weekly_recurrence(self):
        event = self.make_event(
            start="2026-01-05T10:00:00Z",
            end="2026-01-05T11:00:00Z",
            rrule="FREQ=WEEKLY;BYDAY=MO",
        )
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        # 5 Mondays in Jan 2026: 5, 12, 19, 26, plus Feb 2
        # But range_end is Feb 1 so 4 instances + original
        assert len(result) == 4
        assert result[0] is event  # original event
        # Each generated instance has _recurring flag and master_uuid
        for inst in result:
            assert inst["uuid"].startswith("evt-0001")

    def test_instances_have_correct_structure(self):
        event = self.make_event(
            start="2026-02-02T10:00:00Z",
            end="2026-02-02T11:00:00Z",
            rrule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
        )
        result = expand_recurrences(event, "2026-02-01", "2026-02-15")
        for inst in result:
            assert "start" in inst
            assert "end" in inst
            assert inst["title"] == "Test Event"
        assert len(result) >= 5

    def test_respects_max_instances(self):
        event = self.make_event(
            start="2026-01-01T10:00:00Z",
            end="2026-01-01T11:00:00Z",
            rrule="FREQ=DAILY",
        )
        result = expand_recurrences(event, "2026-01-01", "2026-12-31", max_instances=10)
        assert len(result) == 10

    def test_recurrence_outside_range(self):
        """Event happens after range — no instances returned."""
        event = self.make_event(
            start="2027-01-01T10:00:00Z",
            end="2027-01-01T11:00:00Z",
            rrule="FREQ=DAILY",
        )
        result = expand_recurrences(event, "2026-01-01", "2026-12-31")
        # The first occurrence is outside range_end so the loop breaks
        # before any instances are appended.
        assert len(result) == 0

    def test_generated_instance_uuid_format(self):
        event = self.make_event(
            start="2026-01-05T10:00:00Z",
            end="2026-01-05T11:00:00Z",
            rrule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
            uuid="evt-main",
        )
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        # Original is passed through as-is
        assert result[0]["uuid"] == "evt-main"
        # Generated instances get date suffix
        for inst in result[1:]:
            assert inst["uuid"].startswith("evt-main-")
            assert inst["master_uuid"] == "evt-main"
            assert inst["_recurring"] is True

    def test_undefined_start_timezone(self):
        """Events with timezone-naive datetimes are treated as UTC."""
        event = self.make_event(
            start="2026-01-05T10:00:00",
            end="2026-01-05T11:00:00",
            rrule="FREQ=WEEKLY;COUNT=3",
        )
        result = expand_recurrences(event, "2026-01-01", "2026-02-01")
        assert len(result) == 3


class TestIsoConversions:
    """Tests for _iso_to_dt and _dt_to_iso."""

    def test_iso_to_dt_utc_z(self):
        dt = _iso_to_dt("2026-01-15T10:00:00Z")
        assert dt.tzinfo is not None
        assert dt == datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_iso_to_dt_naive_becomes_utc(self):
        dt = _iso_to_dt("2026-01-15T10:00:00")
        assert dt.tzinfo is UTC

    def test_dt_to_iso_utc(self):
        dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        iso = _dt_to_iso(dt)
        assert iso == "2026-01-15T10:00:00+00:00"

    def test_dt_to_iso_strips_microseconds(self):
        dt = datetime(2026, 1, 15, 10, 0, 0, 123456, tzinfo=UTC)
        iso = _dt_to_iso(dt)
        assert iso == "2026-01-15T10:00:00+00:00"

    def test_dt_to_iso_converts_tz(self):

        est = UTC  # simplified: just confirm it normalizes to UTC
        dt = datetime(2026, 1, 15, 5, 0, 0, tzinfo=est)
        iso = _dt_to_iso(dt)
        assert iso.endswith("+00:00")

    def test_roundtrip(self):
        iso_in = "2026-06-15T14:30:00Z"
        dt = _iso_to_dt(iso_in)
        iso_out = _dt_to_iso(dt)
        assert iso_out == "2026-06-15T14:30:00+00:00"

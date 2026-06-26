"""Calendar REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_calendar_service
from lighterbird.server.schemas import (
    CalendarCreate, CalendarResponse, CalendarListResponse, CalendarUpdate,
    EventCreate, EventResponse, EventListResponse, EventQueryParams,
)
from lighterbird.calendar.service import CalendarService

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


def _calendar_to_response(cal: dict) -> CalendarResponse:
    return CalendarResponse(
        uuid=cal["uuid"],
        url=cal.get("url", ""),
        username=cal.get("username", ""),
        remote=bool(cal.get("remote", 1)),
    )


def _event_to_response(evt: dict) -> EventResponse:
    return EventResponse(
        uuid=evt["uuid"],
        calendar_uuid=evt.get("kalendaro_uuid", ""),
        title=evt.get("titolo", ""),
        start=evt.get("komenco", ""),
        end=evt.get("fino", ""),
        location=evt.get("loko", ""),
        description=evt.get("priskribo", ""),
        category=evt.get("kategorio", ""),
    )


@router.get("/calendars", response_model=CalendarListResponse)
def list_calendars(cal_svc: CalendarService = Depends(get_calendar_service)):
    cals = cal_svc.list_calendars()
    return CalendarListResponse(
        calendars=[_calendar_to_response(c) for c in cals]
    )


@router.post("/calendars", response_model=CalendarResponse, status_code=201)
def create_calendar(
    data: CalendarCreate,
    cal_svc: CalendarService = Depends(get_calendar_service),
):
    cal_data = {
        "url": data.url,
        "username": data.username,
        "remote": 1 if data.remote else 0,
    }
    cal = cal_svc.create_calendar(cal_data, password=data.password)
    return _calendar_to_response(cal)


@router.patch("/calendars/{uuid}")
def update_calendar(
    uuid: str,
    data: CalendarUpdate,
    cal_svc: CalendarService = Depends(get_calendar_service),
):
    """Update a calendar (partial)."""
    existing = cal_svc.calendars.get(uuid)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Calendar not found: {uuid[:8]}")
    updates = {}
    if data.url is not None:
        updates["url"] = data.url
    if data.username is not None:
        updates["username"] = data.username
    if updates:
        cal_svc.calendars.update(uuid, updates)
    if data.password is not None:
        from lighterbird.calendar.keyring import set_password

        set_password(uuid, data.password)
    return {"status": "updated", "uuid": uuid[:8]}


@router.delete("/calendars/{uuid}")
def remove_calendar(uuid: str, cal_svc: CalendarService = Depends(get_calendar_service)):
    """Delete a calendar."""
    existing = cal_svc.calendars.get(uuid)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Calendar not found: {uuid[:8]}")
    cal_svc.delete_calendar(uuid)
    return {"status": "deleted"}


@router.post("/sync/{uuid}")
def sync_calendar(uuid: str, cal_svc: CalendarService = Depends(get_calendar_service)):
    try:
        result = cal_svc.sync_calendar(uuid)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/events", response_model=EventListResponse)
def list_events(
    start: str = Query(default="2000-01-01"),
    end: str = Query(default="2099-12-31"),
    calendar_uuid: str | None = None,
    query: str | None = None,
    cal_svc: CalendarService = Depends(get_calendar_service),
):
    events = cal_svc.list_events(start, end, calendar_uuid=calendar_uuid)
    # Client-side search filter (simple title/description match like A-organizi)
    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("titolo") or "").lower()
            or q in (e.get("priskribo") or "").lower()
        ]
    return EventListResponse(events=[_event_to_response(e) for e in events])


@router.post("/events", response_model=EventResponse, status_code=201)
def create_event(
    data: EventCreate,
    cal_svc: CalendarService = Depends(get_calendar_service),
):
    # Validate calendar exists
    calendars = cal_svc.list_calendars()
    if not any(c["uuid"] == data.calendar_uuid for c in calendars):
        raise HTTPException(
            status_code=404,
            detail=f"Calendar '{data.calendar_uuid[:8]}' not found. "
                   f"Use !calendar account list to see available calendars.",
        )
    evt_data = {
        "kalendaro_uuid": data.calendar_uuid,
        "titolo": data.title,
        "komenco": data.start,
        "fino": data.end,
        "loko": data.location,
        "priskribo": data.description,
        "kategorio": data.category,
    }
    evt = cal_svc.create_event(evt_data)
    return _event_to_response(evt)


@router.get("/events/{uuid}", response_model=EventResponse)
def get_event(uuid: str, cal_svc: CalendarService = Depends(get_calendar_service)):
    evt = cal_svc.get_event(uuid)
    if not evt:
        raise HTTPException(status_code=404, detail=f"Event not found: {uuid[:8]}")
    return _event_to_response(evt)


@router.delete("/events/{uuid}", status_code=204)
def delete_event(uuid: str, cal_svc: CalendarService = Depends(get_calendar_service)):
    cal_svc.delete_event(uuid)

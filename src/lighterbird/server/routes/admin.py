"""Admin REST API routes — health, sync triggers."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from lighterbird.server.deps import get_email_service, get_calendar_service
from lighterbird.server.schemas import HealthResponse
from lighterbird.email.service import EmailService
from lighterbird.calendar.service import CalendarService

router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@router.post("/sync/all")
def sync_all(
    email_svc: EmailService = Depends(get_email_service),
    cal_svc: CalendarService = Depends(get_calendar_service),
):
    return {
        "email": email_svc.sync_all(),
        "calendar": cal_svc.sync_all_calendars(),
    }

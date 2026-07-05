"""Profiles REST API routes.

Provides search and retrieval for user identity profiles,
which were previously CLI-only (``!user info``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from lighterbird.profiles.services.profiles import ProfileService
from lighterbird.server.deps import get_profiles_service

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("/profiles")
def list_profiles(
    query: str | None = None,
    limit: int = 50,
    svc: ProfileService = Depends(get_profiles_service),
):
    """List/search profiles. If ``query`` is given, filters by full_name."""
    all_profiles = svc.list()
    if query:
        q = query.lower().strip()
        all_profiles = [
            p for p in all_profiles
            if q in p.get("full_name", "").lower()
            or q in p.get("profile_name", "").lower()
        ]
    return {"profiles": all_profiles[:limit], "total": len(all_profiles)}


@router.get("/profiles/{uuid}")
def get_profile(uuid: str, svc: ProfileService = Depends(get_profiles_service)):
    """Get a single profile by UUID."""
    profile = svc.get(uuid)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile not found: {uuid[:8]}")
    return profile

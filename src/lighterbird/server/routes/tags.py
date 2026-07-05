"""Tags API route — tag management and autocomplete."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from lighterbird.server.deps import get_tag_service

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


@router.get("")
def list_tags():
    """List all tags, ordered by name."""
    svc = get_tag_service()
    tags = svc.list_tags()
    return {"tags": tags, "count": len(tags)}


@router.get("/autocomplete")
def autocomplete_tags(q: str = ""):
    """Autocomplete: filter tags by prefix.

    Returns matching tag names and colors.
    """
    svc = get_tag_service()
    all_tags = svc.list_tags()
    if q:
        ql = q.lower()
        all_tags = [t for t in all_tags if ql in t["name"].lower()]
    return {"tags": all_tags}


@router.get("/domain/{domain}")
def list_tags_for_domain(domain: str):
    """List tags used in a specific domain, with usage count."""
    svc = get_tag_service()
    tags = svc.list_tags_for_domain(domain)
    return {"tags": tags, "count": len(tags)}

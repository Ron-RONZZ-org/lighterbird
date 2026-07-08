"""Shared content render-preview API endpoint.

Provides a single ``POST /api/v1/render-preview`` endpoint that any
frontend component can call to convert markdown / html / plain text
into HTML for preview rendering.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from lighterbird.server.render_utils import convert_to_html

router = APIRouter(prefix="/api/v1", tags=["render"])


class RenderPreviewRequest(BaseModel):
    content: str = ""
    format: str = "markdown"


@router.post("/render-preview")
def render_preview(req: RenderPreviewRequest):
    """Convert content to HTML for preview rendering.

    Accepts ``content`` (string) and ``format`` (``"markdown"``,
    ``"html"``, or ``"plain"``).  Returns ``{"html": "…"}``.
    """
    if not req.content.strip():
        return {"html": ""}
    html = convert_to_html(req.content, req.format)
    return {"html": html}

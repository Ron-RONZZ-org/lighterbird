"""Letters REST API routes."""

from __future__ import annotations

import html as html_mod
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from lighterbird.letter.services.letters import LetterService
from lighterbird.server.render_utils import convert_to_html
from lighterbird.server.deps import get_letter_service

router = APIRouter(prefix="/api/v1/letters", tags=["letters"])


def _render_letter_full_html(letter: dict, body_html: str) -> str:
    """Wrap letter metadata + body in a full HTML page with print-to-PDF support.

    Generates a self-contained letterhead layout (sender top-left, recipient
    right-aligned, date, subject line) with the body content, plus an auto‐print
    JavaScript that opens the browser's print dialog (user picks "Save as PDF").
    """
    today = date.today().isoformat()
    sender = html_mod.escape(letter.get("sender_manual", ""))
    recipient = html_mod.escape(letter.get("recipient_manual", ""))
    subject = html_mod.escape(letter.get("object", "(untitled)"))
    letter_date = html_mod.escape(letter.get("created_at", today))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Letter — {subject}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Times New Roman", Georgia, serif;
      background: #fff; color: #000;
      padding: 2.5cm 2cm; line-height: 1.6; font-size: 12pt;
      max-width: 21cm; margin: 0 auto;
    }}
    @media print {{
      body {{ padding: 0.5cm; }}
      .no-print {{ display: none !important; }}
    }}
    .sender-block {{ margin-bottom: 0.5cm; font-size: 11pt; color: #444; }}
    .sender-block .line {{ margin: 0; }}
    .date {{ font-size: 11pt; color: #666; margin-top: 0.3cm; }}
    .recipient-block {{ margin-top: 1.5cm; text-align: right; font-size: 11pt; }}
    .recipient-block .line {{ margin: 0; }}
    .subject {{ font-weight: bold; margin-top: 1cm; margin-bottom: 1cm; font-size: 13pt; }}
    .body {{ text-align: justify; }}
    .body p {{ margin: 0.3em 0; }}
    .signature {{ margin-top: 2cm; }}
  </style>
</head>
<body>
  <div class="sender-block">
    <p class="line">{sender}</p>
    <p class="date">{letter_date}</p>
  </div>
  <div class="recipient-block">
    <p class="line">{recipient}</p>
  </div>
  <div class="subject">Re: {subject}</div>
  <div class="body">
    {body_html}
  </div>
  <p class="no-print" style="margin-top:1cm;color:#999;font-size:10pt;text-align:center;border-top:1px solid #ddd;padding-top:0.5cm;">
    Use Ctrl+P → "Save as PDF" to save this letter.
  </p>
  <script class="no-print">
    window.onload = function() {{
      setTimeout(function() {{ window.print(); }}, 300);
    }};
  </script>
</body>
</html>"""


class RenderPreviewRequest(BaseModel):
    content: str = ""
    format: str = "markdown"


@router.post("/render-preview")
def render_preview(req: RenderPreviewRequest):
    """Convert body content to HTML for preview rendering (uses shared utility)."""
    if not req.content.strip():
        return {"html": ""}
    html = convert_to_html(req.content, req.format)
    return {"html": html}


@router.get("/letters")
def list_letters(
    direction: str | None = None,
    sort: str = "newest",
    group: str | None = None,
    limit: int = 50,
    svc: LetterService = Depends(get_letter_service),
):
    order_by = "created_at"
    desc = True
    if sort == "oldest":
        desc = False
    elif sort == "sender":
        order_by = "sender_manual"
        desc = False

    if group == "conversation":
        raw = svc.list_grouped(limit=limit)
    else:
        raw = svc.list(limit=limit, direction=direction, order_by=order_by, desc=desc)
    letters = [dict(l) for l in raw]
    return {"letters": letters, "total": len(letters)}


@router.post("/letters", status_code=201)
def create_letter(
    data: dict,
    svc: LetterService = Depends(get_letter_service),
):
    letter_data = {
        "direction": data.get("direction", "received"),
        "object": data.get("object", ""),
        "sender_manual": data.get("sender_manual", ""),
        "sender_profile": data.get("sender_profile"),
        "recipient_manual": data.get("recipient_manual", ""),
        "recipient_contact": data.get("recipient_contact"),
        "respond_to_uuid": data.get("respond_to_uuid"),
    }
    letter = svc.create(letter_data)

    body = data.get("body", "")
    if body:
        body_format = data.get("body_format", "html")
        html_content = svc.convert_to_html(body, body_format) if body_format != "html" else body
        svc.store_body(letter["uuid"], html_content)

    return dict(letter)


@router.get("/letters/{uuid}")
def get_letter(uuid: str, svc: LetterService = Depends(get_letter_service)):
    letter = svc.get_with_thread(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")
    return dict(letter)


@router.get("/letters/{uuid}/body")
def get_letter_body(uuid: str, svc: LetterService = Depends(get_letter_service)):
    letter = svc.get(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")
    body = svc.get_body(uuid)
    return {"uuid": uuid, "body": body, "body_format": letter.get("body_format", "html")}


@router.delete("/letters/{uuid}", status_code=204)
def delete_letter(uuid: str, svc: LetterService = Depends(get_letter_service)):
    svc.delete(uuid)


@router.get("/letters/{uuid}/render", response_class=HTMLResponse)
def render_letter(uuid: str, svc: LetterService = Depends(get_letter_service)):
    """Return a fully rendered letter HTML page for print/PDF download.

    The page includes the letterhead (sender, recipient, date, subject) and
    body content wrapped in print-optimised CSS plus an auto‑print script.
    When opened in the browser the print dialog appears immediately; the user
    selects "Save as PDF" to download a proper PDF.
    """
    letter = svc.get(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")

    body = svc.get_body(uuid)
    if not body:
        from lighterbird.server.command.handlers.letter import _generate_letter_html
        body = _generate_letter_html(
            uuid,
            letter.get("sender_manual", ""),
            letter.get("recipient_manual", ""),
            letter.get("object", ""),
        )

    return _render_letter_full_html(letter, body)


class ExportMDRequest(BaseModel):
    uuids: list[str] = []


@router.get("/export-md/{uuid}", response_class=PlainTextResponse)
def export_letter_md(uuid: str, svc: LetterService = Depends(get_letter_service)):
    """Export a single letter as YAML-frontmatter markdown."""
    letter = svc.get(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")
    md = svc.export_md(uuid=uuid)
    return PlainTextResponse(md, media_type="text/markdown",
                            headers={"Content-Disposition": f'attachment; filename="letter-{uuid[:8]}.md"'})


@router.get("/export-md", response_class=PlainTextResponse)
def export_letters_md(
    uuids: str = "",
    svc: LetterService = Depends(get_letter_service),
):
    """Export multiple letters as concatenated YAML-frontmatter markdown.

    Query param ``uuids`` is a comma-separated list of UUIDs.
    """
    if not uuids:
        raise HTTPException(status_code=400, detail="No UUIDs provided. Use ?uuids=uuid1,uuid2")
    uuid_list = [u.strip() for u in uuids.split(",") if u.strip()]
    md = svc.export_md(uuids=uuid_list)
    return PlainTextResponse(md, media_type="text/markdown",
                            headers={"Content-Disposition": f'attachment; filename="letters-{len(uuid_list)}.md"'})


class ImportMDRequest(BaseModel):
    path: str


@router.post("/import-md")
def import_letter_md(
    req: ImportMDRequest,
    svc: LetterService = Depends(get_letter_service),
):
    """Import a letter from a YAML-frontmatter markdown file."""
    try:
        uuids = svc.import_md(req.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"uuids": uuids, "imported": len(uuids)}

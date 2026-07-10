"""Command handlers for ``!letter`` send and PDF operations.

Registered paths:
    - letter.send
    - letter.pdf
"""

from __future__ import annotations

from typing import Any

from lighterbird.letter.services.letters import LetterService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_letter_service


@command("letter.send", interactive=True)
def letter_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter send <recipient> [--object OBJECT] [--body <file-path>]
                                  [--body-text CONTENT] [--body-format FORMAT]
                                  [--sender-profile UUID] [--recipient-contact UUID]
                                  [--sender SENDER] [--respond-to UUID]
                                  [--tag TAG,...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing recipient.",
            "Usage: !letter send \"Recipient Name\" [--object OBJECT] [--body <path>]"
            " [--tag TAG,...]",
        )
    recipient = remaining[0]
    svc: LetterService = get_letter_service()

    data: dict[str, Any] = {
        "direction": "sent",
        "object": flags.get("object", ""),
        "recipient_manual": recipient,
    }

    sender_profile = flags.get("sender-profile", "")
    if sender_profile:
        try:
            from lighterbird.server.deps import get_profiles_service
            profile_svc = get_profiles_service()
            profile = profile_svc.get(sender_profile)
            if profile:
                data["sender_profile"] = profile["uuid"]
                if not data.get("sender_manual"):
                    data["sender_manual"] = profile.get("full_name", "")
        except Exception:
            pass

    sender_manual = flags.get("sender", "")
    if sender_manual:
        data["sender_manual"] = sender_manual

    recipient_contact = flags.get("recipient-contact", "")
    if recipient_contact:
        try:
            from lighterbird.server.deps import get_contact_service
            contact_svc = get_contact_service()
            contact = contact_svc.get(recipient_contact)
            if contact:
                data["recipient_contact"] = contact["uuid"]
        except Exception:
            pass

    respond_to = flags.get("respond-to", "")
    if respond_to:
        parent = svc.get(respond_to)
        if not parent:
            raise CommandValidationError(f"Letter not found: {respond_to[:8]}")
        data["respond_to_uuid"] = parent["uuid"]

    letter = svc.create(data)

    # Set tags
    if "tag" in flags:
        tags = svc.normalize_tags([flags["tag"]])
        if tags:
            svc.set_tags(letter["uuid"], tags)

    body_file = flags.get("body", "")
    body_text = flags.get("body-text", "")
    html_body = ""
    if body_text:
        # Inline body text from GUI (takes precedence over file path)
        body_format = flags.get("body-format", "markdown")
        html_body = svc.convert_to_html(body_text, body_format)
        svc.store_body(letter["uuid"], html_body)
    elif body_file:
        try:
            from pathlib import Path
            body_path = Path(body_file)
            if not body_path.exists():
                raise CommandValidationError(f"Body file not found: {body_file}")
            content = body_path.read_text(encoding="utf-8")
            suffix = body_path.suffix.lower()
            fmt = "html"
            if suffix == ".md":
                fmt = "markdown"
            elif suffix == ".txt":
                fmt = "text"
            html_body = svc.convert_to_html(content, fmt)
            svc.store_body(letter["uuid"], html_body)
        except CommandValidationError:
            raise
        except Exception as e:
            raise CommandValidationError(f"Failed to read body file: {e}")
    else:
        # Generate a minimal letter HTML
        html_body = _generate_letter_html(
            letter["uuid"],
            data.get("sender_manual", "") or data.get("sender_profile", ""),
            recipient,
            flags.get("object", ""),
        )
        svc.store_body(letter["uuid"], html_body)

    return {
        "type": "status",
        "title": "Letter Sent",
        "data": {
            "uuid": letter["uuid"],
            "object": flags.get("object", ""),
            "recipient": recipient,
            "render_url": f"/api/v1/letters/letters/{letter['uuid']}/render",
        },
    }


def _generate_letter_html(uuid: str, sender: str, recipient: str, subject: str) -> str:
    """Generate a nicely formatted HTML letter."""
    from datetime import date
    today = date.today().isoformat()
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
    .sender-block {{ margin-bottom: 0.5cm; font-size: 11pt; color: #444; }}
    .sender-block .line {{ margin: 0; white-space: pre-wrap; }}
    .date {{ font-size: 11pt; color: #666; margin-top: 0.3cm; }}
    .recipient-block {{ margin-top: 1.5cm; text-align: right; font-size: 11pt; }}
    .recipient-block .line {{ margin: 0; white-space: pre-wrap; }}
    .subject {{ font-weight: bold; margin-bottom: 1cm; font-size: 13pt; }}
    .body {{ text-align: justify; }}
    .signature {{ margin-top: 2cm; }}
  </style>
</head>
<body>
  <div class="sender-block">
    <p class="line">{sender}</p>
    <p class="date">{today}</p>
  </div>
  <div class="recipient-block">
    <p class="line">{recipient}</p>
  </div>
  <div class="subject">Re: {subject}</div>
  <div class="body">
    <p>[Letter content]</p>
  </div>
</body>
</html>"""


@command("letter.pdf",
         params=[{"name": "uuid", "type": "string", "help": "Letter UUID", "required": True, "uuidSource": "letters.letters"}])
def letter_pdf(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter pdf <uuid> [--output PATH]

    Generate a PDF file from a letter's body content.
    Uses ``fpdf2`` (install with ``pip install lighterbird[pdf]``).

    If --output is omitted, saves to
    ``{data_dir}/letters/pdfs/{uuid}.pdf`` and returns the path.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing letter UUID.", "Usage: !letter pdf <uuid> [--output path]"
        )
    uuid = remaining[0]
    svc: LetterService = get_letter_service()
    letter_data = svc.get(uuid)
    if not letter_data:
        raise CommandValidationError(f"Letter not found: {uuid[:8]}")

    body = svc.get_body(uuid)
    if not body:
        # Generate minimal HTML if no body stored
        body = _generate_letter_html(
            uuid,
            letter_data.get("sender_manual", ""),
            letter_data.get("recipient_manual", ""),
            letter_data.get("object", ""),
        )

    # Determine output path
    output = flags.get("output", "")
    if not output:
        from lighterbird.core.paths import data_dir
        pdf_dir = data_dir() / "letters" / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        output = str(pdf_dir / f"{uuid}.pdf")

    try:
        from fpdf import FPDF
    except ImportError:
        raise CommandValidationError(
            "fpdf2 is required for PDF generation. "
            "Install it with: pip install lighterbird[pdf]"
        )

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=20)

        # Strip HTML tags for plain-text PDF content
        import re
        # Remove style/script blocks
        clean = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL)
        clean = re.sub(r'<script[^>]*>.*?</script>', '', clean, flags=re.DOTALL)
        # Replace <br> and </p> with newlines
        clean = re.sub(r'<br\s*/?>', '\n', clean)
        clean = re.sub(r'</p>', '\n\n', clean)
        clean = re.sub(r'</div>', '\n', clean)
        # Remove remaining tags
        clean = re.sub(r'<[^>]+>', '', clean)
        # Unescape HTML entities
        clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        clean = clean.replace('&quot;', '"').replace('&#39;', "'")
        # Decode multi-byte entities
        clean = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), clean)
        clean = clean.strip()

        # Write as multi-line text
        pdf.set_font("Times", size=12)
        for line in clean.split('\n'):
            line = line.strip()
            if line:
                try:
                    pdf.multi_cell(0, 6, line)
                except ValueError:
                    # Fallback: encode as latin-1, replacing unsupported chars
                    safe = line.encode('latin-1', errors='replace').decode('latin-1')
                    pdf.multi_cell(0, 6, safe)
            else:
                pdf.ln(4)

        pdf.output(output)
    except Exception as e:
        raise CommandValidationError(f"PDF generation failed: {e}")

    return {
        "type": "status",
        "title": "PDF Generated",
        "data": {
            "uuid": uuid,
            "output": output,
            "pages": pdf.pages_count if 'pdf' in dir() else 0,
        },
    }

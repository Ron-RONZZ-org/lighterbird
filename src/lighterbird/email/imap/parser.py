"""Email message parsing — MIME body extraction, metadata.

Forked from A-lien's imap/_message_parser.py.
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from lighterbird.email.imap.helpers import decode_mime_header, parse_address_list


def parse_email_message(
    msg: Any,
    konto_id: str,
    dosierujo_id: str,
    imap_uid: int,
) -> dict[str, Any]:
    """Parse a single email message into a storage dict.

    Args:
        msg: Email message object (from email.message_from_bytes)
        konto_id: Account UUID
        dosierujo_id: Folder UUID
        imap_uid: IMAP UID

    Returns:
        Dict with all fields for the mesagoj table.
    """
    now = datetime.now(timezone.utc).isoformat()
    message_id = decode_mime_header(msg.get("Message-ID", ""))
    in_reply_to = decode_mime_header(msg.get("In-Reply-To", ""))

    subject = decode_mime_header(msg.get("Subject", ""))
    from_header = decode_mime_header(msg.get("From", ""))
    to_raw = decode_mime_header(msg.get("To", ""))
    cc_raw = decode_mime_header(msg.get("Cc", ""))
    date_str = msg.get("Date", "")

    ricevita_je = now
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            ricevita_je = dt.isoformat()
        except (TypeError, ValueError):
            pass

    body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            filename = part.get_filename()
            if "attachment" in disp or filename:
                continue  # Skip attachments for MVP
            elif ct == "text/plain" and not body and not filename:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
            elif ct == "text/html" and not html_body and not filename:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    data: dict[str, Any] = {
        "uuid": str(uuid_mod.uuid4()),
        "konto_id": konto_id,
        "dosierujo_id": dosierujo_id,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "imap_uid": imap_uid,
        "de": from_header,
        "al": json.dumps(parse_address_list(to_raw), ensure_ascii=False),
        "kc": json.dumps(parse_address_list(cc_raw), ensure_ascii=False),
        "subjekto": subject,
        "korpo": body,
        "html_korpo": html_body,
        "prioritato": 5,
        "legita": 0,
        "stelo": 0,
        "forigita": 0,
        "ricevita_je": ricevita_je,
        "kreita_je": now,
        "modifita_je": now,
    }
    return data

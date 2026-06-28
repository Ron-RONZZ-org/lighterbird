"""Email message parsing — MIME body extraction, metadata, attachments.

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
    account_email: str,
    folder_name: str,
    imap_uid: int,
    store_attachments: bool = True,
) -> dict[str, Any]:
    """Parse a single email message into a storage dict.

    Args:
        msg: Email message object (from email.message_from_bytes).
        account_email: Account email.
        folder_name: Folder name.
        imap_uid: IMAP UID.
        store_attachments: If True, persist attachment blobs via
            AttachmentStore and include attachment metadata in the result.

    Returns:
        Dict with all fields for the messages table, plus an extra
        ``_attachments`` key with attachment metadata if any were found.
    """
    now = datetime.now(timezone.utc).isoformat()
    raw_message_id = decode_mime_header(msg.get("Message-ID", ""))
    # Strip angle brackets from Message-ID
    message_id = raw_message_id.strip("<>") if raw_message_id else ""
    in_reply_to = decode_mime_header(msg.get("In-Reply-To", "")).strip("<>")

    subject = decode_mime_header(msg.get("Subject", ""))
    from_header = decode_mime_header(msg.get("From", ""))
    to_raw = decode_mime_header(msg.get("To", ""))
    cc_raw = decode_mime_header(msg.get("Cc", ""))
    date_str = msg.get("Date", "")

    received_at = now
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            received_at = dt.isoformat()
        except (TypeError, ValueError):
            pass

    body = ""
    html_body = ""
    attachments: list[dict[str, Any]] = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            filename = part.get_filename()

            if "attachment" in disp or filename:
                payload = part.get_payload(decode=True)
                content_id = (part.get("Content-ID") or str(uuid_mod.uuid4())).strip("<>")
                att = {
                    "filename": filename or "attachment",
                    "mime_type": ct,
                    "size": len(payload) if payload else 0,
                    "content_id": content_id,
                    "data": payload if store_attachments else None,
                }
                attachments.append(att)
            elif ct not in ("text/plain", "text/html") and not part.is_multipart():
                name = part.get_param("name", None, "Content-Type") or ""
                if name:
                    payload = part.get_payload(decode=True)
                    content_id = (part.get("Content-ID") or str(uuid_mod.uuid4())).strip("<>")
                    attachments.append({
                        "filename": name,
                        "mime_type": ct,
                        "size": len(payload) if payload else 0,
                        "content_id": content_id,
                        "data": payload if store_attachments else None,
                    })
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
        "account_email": account_email,
        "folder_name": folder_name,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "imap_uid": imap_uid,
        "from_addr": from_header,
        "to_recipients": json.dumps(parse_address_list(to_raw), ensure_ascii=False),
        "cc_recipients": json.dumps(parse_address_list(cc_raw), ensure_ascii=False),
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "priority": 5,
        "is_read": 0,
        "is_starred": 0,
        "is_deleted": 0,
        "received_at": received_at,
        "created_at": now,
        "updated_at": now,
    }

    if attachments:
        # Store metadata as JSON in the message (backward compat)
        meta_list = [
            {
                "dosiernomo": a["filename"],
                "mime_tipo": a["mime_type"],
                "size": a["size"],
                "content_id": a["content_id"],
            }
            for a in attachments
        ]
        data["_attachments_meta"] = meta_list
        data["_attachments_data"] = [
            a for a in attachments if a["data"] is not None
        ]

    return data

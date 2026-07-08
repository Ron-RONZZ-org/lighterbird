"""Shared content-to-HTML rendering utilities for preview and send flows.

Extracted from ``letter.services.letters.LetterService.convert_to_html``
so that email, journal, and any other domain can render markdown/html/plain
content without depending on LetterService.
"""

from __future__ import annotations

import re
from typing import Any


def convert_to_html(content: str, fmt: str) -> str:
    """Convert markdown or plain text to HTML.

    Args:
        content: The source content string.
        fmt: One of ``"html"``, ``"markdown"``, or ``"plain"``.

    Returns:
        Rendered HTML string. HTML input is returned as-is (no
        sanitisation — caller should sanitise for untrusted content).
    """
    if fmt == "html":
        return content
    if fmt == "markdown":
        try:
            import markdown as md_lib

            return md_lib.markdown(content)
        except ImportError:
            pass
        # Fallback: basic hand-rolled markdown parser
        lines: list[str] = []
        in_para = False
        for raw_line in content.split("\n"):
            stripped = raw_line.strip()
            if not stripped:
                if in_para:
                    lines.append("</p>")
                    in_para = False
                continue
            if stripped.startswith("# "):
                if in_para:
                    lines.append("</p>")
                    in_para = False
                lines.append(f"<h1>{_inline_markdown(stripped[2:])}</h1>")
            elif stripped.startswith("## "):
                if in_para:
                    lines.append("</p>")
                    in_para = False
                lines.append(f"<h2>{_inline_markdown(stripped[3:])}</h2>")
            elif stripped.startswith("### "):
                if in_para:
                    lines.append("</p>")
                    in_para = False
                lines.append(f"<h3>{_inline_markdown(stripped[4:])}</h3>")
            else:
                if not in_para:
                    lines.append("<p>")
                    in_para = True
                lines.append(_inline_markdown(stripped))
        if in_para:
            lines.append("</p>")
        return "\n".join(lines)
    # plain text — escape HTML entities and wrap in <pre>
    _escaped = (
        content.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<pre>{_escaped}</pre>"


def _inline_markdown(text: str) -> str:
    """Apply basic inline markdown formatting (bold, italic, code, links)."""
    # Must escape HTML entities before adding markdown tags
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # **bold** or __bold__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # *italic* or _italic_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    # `inline code`
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{m.group(1)}</code>",
        text,
    )
    # [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text


def escape_html(text: str) -> str:
    """Escape HTML special characters in a string."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ── Email composition ──────────────────────────────────────────────────

_PREVIEW_CSS = """
body{font-family:Georgia,"Times New Roman",serif;padding:2em;line-height:1.6;color:#000;background:#fff;max-width:21cm;margin:0 auto;}
img{max-width:100%;}
pre{background:#f5f5f5;padding:1em;overflow-x:auto;}
code{background:#f0f0f0;padding:0.15em 0.3em;border-radius:3px;}
pre code{background:none;padding:0;}
table{border-collapse:collapse;width:100%;}
td,th{border:1px solid #ccc;padding:0.4em;}
th{background:#f0f0f0;}
blockquote{border-left:3px solid #ccc;margin-left:0;padding-left:1em;color:#555;}
.signature-separator{border:none;border-top:1px solid #ccc;margin:1em 0;}
.signature{color:#555;font-size:0.9em;}
.attachment-link{display:inline-block;margin:0.25em 0;padding:0.3em 0.6em;background:#f0f0f0;border:1px solid #ccc;border-radius:4px;text-decoration:none;color:#333;}
.attachment-link:hover{background:#e0e0e0;}
.subject-title{font-size:1.3em;font-weight:bold;margin-bottom:0.5em;color:#000;}
"""


def compose_email_html(
    subject: str,
    body: str,
    body_format: str,
    signature_text: str | None = None,
    signature_format: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    attachment_base_url: str = "",
    full_document: bool = False,
) -> str:
    """Compose an HTML email document from its parts.

    Converts body and signature (if markdown/plain) to HTML via
    :func:`convert_to_html`, then assembles them into an HTML
    string suitable for preview or SMTP send.

    Args:
        subject: Email subject line (rendered as heading).
        body: Email body text.
        body_format: One of ``"markdown"``, ``"html"``, or ``"plain"``.
        signature_text: Optional signature text.
        signature_format: Signature format.  Ignored if ``signature_text``
            is falsy.  Defaults to ``"plain"``.
        attachments: Optional list of attachment dicts with ``"uuid"``
            and ``"filename"`` keys.
        attachment_base_url: Base URL for attachment download links
            (e.g. ``/api/v1/email/attachments/``).
        full_document: If True, returns a complete HTML document with
            DOCTYPE, head, style, and body tags.  If False (default),
            returns only the inner HTML content (for embedding in
            PreviewDialog or new-tab wrapper).

    Returns:
        HTML string (full document or inner content).
    """
    # Convert body
    body_html = convert_to_html(body, body_format)

    # Convert signature
    sig_html = ""
    if signature_text:
        fmt = signature_format or "plain"
        sig_html = convert_to_html(signature_text, fmt)
        sig_html = f'<div class="signature">{sig_html}</div>'

    # Attachment links
    att_html = ""
    if attachments:
        items = []
        for att in attachments:
            att_uuid = att.get("uuid", "")
            filename = att.get("filename", "attachment")
            href = f"{attachment_base_url}{att_uuid}/download" if attachment_base_url else "#"
            items.append(
                f'<a href="{escape_html(href)}" class="attachment-link" '
                f'target="_blank">{escape_html(filename)}</a>'
            )
        if items:
            att_html = '<div class="attachments">\n' + "\n".join(items) + "\n</div>"

    inner_parts = [
        f'<div class="subject-title">{escape_html(subject)}</div>'
        if subject else "",
        '<div class="body">',
        body_html,
        "</div>",
        f'<hr class="signature-separator">\n{sig_html}' if sig_html else "",
        att_html if att_html else "",
    ]
    inner_html = "\n".join(p for p in inner_parts if p)

    if full_document:
        return (
            "<!DOCTYPE html>\n<html lang='en'>\n<head><meta charset='utf-8'>\n"
            f"<style>{_PREVIEW_CSS}</style>\n</head><body>\n{inner_html}\n</body></html>"
        )
    return inner_html


__all__ = ["convert_to_html", "escape_html", "compose_email_html"]

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


__all__ = ["convert_to_html", "escape_html"]

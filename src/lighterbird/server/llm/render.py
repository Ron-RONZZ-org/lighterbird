"""Markdown-to-HTML rendering for LLM responses.

Uses mistune for full rendering (non-streaming responses).
Also provides a lightweight HTML sanitizer to strip dangerous tags.
"""

from __future__ import annotations

import re

import mistune

# ── Mistune renderer ─────────────────────────────────────────────────────────

_markdown = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "table", "url"],
)

# HTML tags we allow through sanitization
_ALLOWED_TAGS = {
    "p", "br", "hr",
    "ul", "ol", "li",
    "strong", "em", "b", "i", "u", "s", "del",
    "code", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
}

_ALLOWED_ATTRS = {
    "a": {"href", "title", "target"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class"},
    "th": {"align"},
    "td": {"align"},
    "*": {"id"},  # allowed on any element (fragment identifiers)
}


def render_markdown(text: str) -> str:
    """Render markdown to sanitized HTML.

    Args:
        text: Raw markdown string from LLM.

    Returns:
        Safe HTML string suitable for ``innerHTML``.
    """
    if not text:
        return ""
    raw_html = _markdown(text)
    return _sanitize_html(raw_html)


def _sanitize_html(html: str) -> str:
    """Strip disallowed tags and attributes from HTML.

    This is a lightweight allowlist-based sanitizer. For full protection
    against XSS in user-generated content, consider ``bleach`` or
    ``nh3`` — but for LLM-generated content (which we control via the
    system prompt), this allowlist is sufficient.
    """
    # Remove all tags not in ALLOWED_TAGS
    def _strip_tag(m: re.Match[str]) -> str:
        full = m.group(0)
        if full.startswith("</"):
            tag = full[2:-1].split()[0].rstrip(">")
            if tag in _ALLOWED_TAGS:
                return full
            return ""
        # Opening tag
        tag_match = re.match(r"<(\w+)", full)
        if not tag_match:
            return _escape_lt(full)
        tag = tag_match.group(1)
        if tag not in _ALLOWED_TAGS:
            return _escape_lt(full)
        # Keep only allowed attributes
        allowed = _ALLOWED_ATTRS.get(tag, set()) | _ALLOWED_ATTRS.get("*", set())
        attrs = _filter_attrs(full, allowed)
        if full.endswith("/>"):
            return f"<{tag} {attrs}/>" if attrs else f"<{tag}/>"
        return f"<{tag} {attrs}>" if attrs else f"<{tag}>"

    html = re.sub(r"<[^>]*>", _strip_tag, html)
    return html


def _filter_attrs(tag_html: str, allowed: set[str]) -> str:
    """Extract and return only allowed attributes from an HTML tag."""
    attrs_found: list[str] = []
    for a_name, a_val in re.findall(r"""(\w+)\s*=\s*(["'])(.*?)\2""", tag_html):
        if a_name in allowed:
            # Basic XSS protection: strip script: and javascript: from href
            if a_name == "href":
                a_val = re.sub(r"^(javascript|data|vbscript):", "", a_val, flags=re.IGNORECASE)
                if not a_val:
                    continue
            attrs_found.append(f'{a_name}="{_escape_attr(a_val)}"')
    return " ".join(attrs_found)


def _escape_lt(text: str) -> str:
    """Escape ``<`` in text that isn't part of an allowed tag."""
    return text.replace("<", "&lt;")


def _escape_attr(value: str) -> str:
    """Escape HTML special chars in attribute values."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── Lightweight streaming markdown renderer (frontend-compatible) ────────────

def render_streaming_markdown(text: str) -> str:
    """Convert markdown to HTML incrementally for streaming display.

    This produces simpler HTML than mistune but is safe to call on
    partial content (unclosed tags, mid-word formatting). It's designed
    to be called on each token chunk as it arrives.
    """
    if not text:
        return ""
    # Escape HTML
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Code blocks (must be processed before inline code)
    text = _process_code_blocks(text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold and italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    # Line breaks (double newline = paragraph)
    text = re.sub(r"\n\s*\n", "</p><p>", text)
    # Single newline = <br>
    text = re.sub(r"\n", "<br>", text)
    return f"<p>{text}</p>"


def _process_code_blocks(text: str) -> str:
    """Replace fenced code blocks with <pre><code>."""
    def _replace_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = m.group(2)
        # Escape already done
        lang_attr = f' class="language-{lang}"' if lang else ""
        return f"<pre><code{lang_attr}>{code}</code></pre>"
    return re.sub(
        r"```(\w*)\n(.*?)```",
        _replace_block,
        text,
        flags=re.DOTALL,
    )

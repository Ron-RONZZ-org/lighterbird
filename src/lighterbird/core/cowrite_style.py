"""Editable co-writing style guide for the lighterbird LLM assistant.

Uses a **cascade model**:

1. **General file** (``cowrite_style.md``) — cross-cutting rules that apply
   to all domains: tone, language, active voice, etc.
2. **Per-domain files** (``cowrite_style_{domain}.md``) — domain-specific
   rules for email, journal, todo, and letter writing.  Auto-seeded with
   focused defaults and appended to the general style when present.

General file always loads first (if it exists); the domain-specific file
is appended after.  Both are seeded on first access (lazy seeding).

This file is the **style layer only**.  The protocol layer (JSON format,
field preservation, response parsing) is hardcoded in
``server/cowrite/engine.py`` and is NEVER user-editable.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.paths import config_dir

_COWRITE_GENERAL_FILENAME = "cowrite_style.md"
_COWRITE_DOMAIN_PREFIX = "cowrite_style_"
_COWRITE_DOMAIN_SUFFIX = ".md"

# Map form_type → domain slug (used to build the per-domain filename).
_FORM_TYPE_TO_DOMAIN: dict[str, str] = {
    "email-send": "email",
    "email-forward": "email",
    "email-reply": "email",
    "todo-add": "todo",
    "journal-write": "journal",
    "letter-send": "letter",
    "letter-add": "letter",
}

# ── Default content ──────────────────────────────────────────────────────────

DEFAULT_COWRITE_STYLE = """# Co-writing Style Guide

This file lets you tell the LLM how you want your writing to sound.
Remove or edit the sections below to match your personal style.

## Tone
- Professional but approachable
- Clear and direct — avoid jargon
- Be concise; respect the reader's time

## Language
- Use active voice
- Avoid unnecessary adjectives
- Write in present tense unless describing past events
"""

DEFAULT_COWRITE_STYLE_EMAIL = """# Email Style Guide

## Email
- Start with a brief greeting
- State the purpose in the first paragraph
- Use short paragraphs (2-3 sentences max)
- End with a clear call to action or closing
- Signature is handled by the email account — do not add one
"""

DEFAULT_COWRITE_STYLE_JOURNAL = """# Journal Style Guide

## Journal
- Write in first person
- Be reflective and honest
- Include specific details (dates, names, context)
- Focus on what you learned or felt
"""

DEFAULT_COWRITE_STYLE_TODO = """# Todo Style Guide

## Todo
- Keep titles short and actionable (verb + object)
- Description should clarify context, not restate the title
- Use checklists for multi-step tasks
"""

DEFAULT_COWRITE_STYLE_LETTER = """# Letter Style Guide

## Letter
- Use formal salutation (Dear …)
- State the purpose in the opening paragraph
- Keep paragraphs focused and concise
- Close with a formal valediction (Sincerely, Yours faithfully, …)
- Recipient address and sender details are handled by the form — do not add them
"""


def cowrite_style_path() -> str:
    """Return the path to the general co-writing style file.

    Returns:
        ``~/.config/lighterbird/cowrite_style.md`` as a string.
    """
    return str(config_dir() / _COWRITE_GENERAL_FILENAME)


def cowrite_style_domain_path(domain: str) -> str:
    """Return the path to a domain-specific co-writing style file.

    Args:
        domain: Domain slug (``"email"``, ``"journal"``, ``"todo"``,
            ``"letter"``).

    Returns:
        ``~/.config/lighterbird/cowrite_style_{domain}.md`` as a string.
    """
    return str(config_dir() / f"{_COWRITE_DOMAIN_PREFIX}{domain}{_COWRITE_DOMAIN_SUFFIX}")


def _lazy_seed(path: Path, default: str) -> None:
    """Write *default* to *path* if the file doesn't exist or is empty."""
    try:
        if path.is_file():
            try:
                if path.read_text(encoding="utf-8").strip():
                    return
            except OSError:
                pass
    except OSError:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default, encoding="utf-8")
    except OSError:
        pass


def _read_file(path: Path) -> str | None:
    """Read and return *path* content, or ``None`` if missing/empty."""
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None
    except OSError:
        return None


def load_cowrite_style(form_type: str | None = None) -> str | None:
    """Load the co-writing style guide (general + per-domain cascade).

    **Cascade order** (both optional):
    1. Load general ``cowrite_style.md`` (if exists and non-empty).
    2. If *form_type* is provided, resolve the domain slug, load the
       domain-specific file (auto-seeding on first access), and append
       it under a ``## Domain-specific Guide`` heading.

    Args:
        form_type: Form type string (e.g. ``"email-send"``, ``"todo-add"``).
            If ``None``, only the general file is loaded.

    Returns:
        The combined style guide string, or ``None`` if nothing is
        available (general file missing/empty and no domain file).
    """
    general_path = config_dir() / _COWRITE_GENERAL_FILENAME
    parts: list[str] = []

    # 1. General file — lazy seed on first access
    general = _read_file(general_path)
    if general is None:
        _lazy_seed(general_path, DEFAULT_COWRITE_STYLE)
        general = _read_file(general_path)
    if general:
        parts.append(general)

    # 2. Domain-specific file (if form_type resolves to a known domain)
    domain = _FORM_TYPE_TO_DOMAIN.get(form_type) if form_type else None
    if domain:
        domain_path = config_dir() / f"{_COWRITE_DOMAIN_PREFIX}{domain}{_COWRITE_DOMAIN_SUFFIX}"
        domain_content = _read_file(domain_path)
        if domain_content is None:
            # Auto-seed with the appropriate default
            _defaults = {
                "email": DEFAULT_COWRITE_STYLE_EMAIL,
                "journal": DEFAULT_COWRITE_STYLE_JOURNAL,
                "todo": DEFAULT_COWRITE_STYLE_TODO,
                "letter": DEFAULT_COWRITE_STYLE_LETTER,
            }
            if domain in _defaults:
                _lazy_seed(domain_path, _defaults[domain])
                domain_content = _read_file(domain_path)
        if domain_content:
            parts.append("## Domain-specific Guide\n\n" + domain_content)

    return "\n\n".join(parts) if parts else None


__all__ = [
    "DEFAULT_COWRITE_STYLE",
    "DEFAULT_COWRITE_STYLE_EMAIL",
    "DEFAULT_COWRITE_STYLE_JOURNAL",
    "DEFAULT_COWRITE_STYLE_LETTER",
    "DEFAULT_COWRITE_STYLE_TODO",
    "cowrite_style_domain_path",
    "cowrite_style_path",
    "load_cowrite_style",
]

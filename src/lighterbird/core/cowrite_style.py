"""Editable co-writing style guide for the lighterbird LLM assistant.

Users can customise the writing style by placing a file at::

    ~/.config/lighterbird/cowrite_style.md

On first run (when no file exists) a shipped default is automatically
copied to that location so the user can edit it.

This file is OPTIONAL — if it is missing or empty, no style guidance is
appended to the co-writing protocol prompt (only the hardcoded protocol
layer is used).

NOTE: This is a *style* layer only. The protocol layer (JSON format,
completeness, field preservation) is hardcoded in
``server/cowrite/engine.py`` and is NEVER user-editable.
"""

from __future__ import annotations

from lighterbird.core.paths import config_dir

_COWRITE_STYLE_FILENAME = "cowrite_style.md"

# ── Shipped default ─────────────────────────────────────────────────────────

DEFAULT_COWRITE_STYLE = """# Co-writing Style Guide

This file lets you tell the LLM how you want your writing to sound.
Remove or edit the sections below to match your personal style.

## Tone
- Professional but approachable
- Clear and direct — avoid jargon
- Be concise; respect the reader's time

## Email
- Start with a brief greeting
- State the purpose in the first paragraph
- Use short paragraphs (2-3 sentences max)
- End with a clear call to action or closing
- Signature is handled by the email account — do not add one

## Journal
- Write in first person
- Be reflective and honest
- Include specific details (dates, names, context)
- Focus on what you learned or felt

## Todo
- Keep titles short and actionable (verb + object)
- Description should clarify context, not restate the title
- Use checklists for multi-step tasks

## Language
- Use active voice
- Avoid unnecessary adjectives
- Write in present tense unless describing past events
"""


def cowrite_style_path() -> str:
    """Return the path to the user-modifiable co-writing style file.

    Returns:
        ``~/.config/lighterbird/cowrite_style.md`` as a string.
    """
    return str(config_dir() / _COWRITE_STYLE_FILENAME)


def load_cowrite_style() -> str | None:
    """Load the co-writing style guide, auto-seeding on first run.

    Resolution order:
    1. If ``~/.config/lighterbird/cowrite_style.md`` exists and is
       non-empty → return its content (never modified).
    2. Otherwise, write the shipped default to that location and
       return its content.
    3. Fall back to :data:`DEFAULT_COWRITE_STYLE`.

    Returns:
        The style guide string, or ``None`` if the file is empty
        and no default could be written.
    """
    path = config_dir() / _COWRITE_STYLE_FILENAME

    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content

    # Auto-seed on first run
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(DEFAULT_COWRITE_STYLE, encoding="utf-8")
    except OSError:
        return None
    return DEFAULT_COWRITE_STYLE


__all__ = [
    "DEFAULT_COWRITE_STYLE",
    "cowrite_style_path",
    "load_cowrite_style",
]

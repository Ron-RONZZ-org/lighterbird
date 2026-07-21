"""Editable co-writing style guide — app-specific defaults wrapping lighterllm.

The cascade loading mechanism now lives in ``lighterllm.cowrite.style``.
This module provides lighterbird-specific defaults and the form_type →
domain mapping, then delegates to lighterllm.

See :mod:`lighterllm.cowrite.style` for the shared cascade logic.
"""

from __future__ import annotations

from lightercore.paths import config_dir
from lighterllm.cowrite.style import (
    cowrite_style_domain_path as _core_domain_path,
)
from lighterllm.cowrite.style import (
    cowrite_style_path as _core_path,
)
from lighterllm.cowrite.style import (
    load_cowrite_style as _core_load,
)

# ── Mapping form_type → domain slug ────────────────────────────────────────

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
    return _core_path(config_dir())


def cowrite_style_domain_path(domain: str) -> str:
    """Return the path to a domain-specific co-writing style file.

    Args:
        domain: Domain slug (``"email"``, ``"journal"``, etc.).

    Returns:
        ``~/.config/lighterbird/cowrite_style_{domain}.md`` as a string.
    """
    return _core_domain_path(config_dir(), domain)


def load_cowrite_style(form_type: str | None = None) -> str | None:
    """Load the co-writing style guide (general + per-domain cascade).

    Delegates to ``lightercore.cowrite.style.load_cowrite_style`` with
    lighterbird-specific defaults.

    Args:
        form_type: Form type (e.g. ``"email-send"``, ``"todo-add"``).

    Returns:
        The combined style guide string, or ``None``.
    """
    return _core_load(
        config_dir=config_dir(),
        form_type=form_type,
        form_type_to_domain=_FORM_TYPE_TO_DOMAIN,
        defaults={
            "general": DEFAULT_COWRITE_STYLE,
            "email": DEFAULT_COWRITE_STYLE_EMAIL,
            "journal": DEFAULT_COWRITE_STYLE_JOURNAL,
            "todo": DEFAULT_COWRITE_STYLE_TODO,
            "letter": DEFAULT_COWRITE_STYLE_LETTER,
        },
    )


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

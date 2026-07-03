"""Shared YAML frontmatter parsing/generation for .md export/import.

Lighterbird uses YAML frontmatter to embed metadata (uuid, timestamps,
tags, domain-specific fields) in Markdown export files.  This module
provides the shared ``wrap()`` and ``unwrap()`` functions used by
todo, journal, and letter services.

The format is standard:

.. code:: markdown

    ---
    uuid: "550e8400-e29b-41d4-a716-446655440000"
    domain: todo
    created_at: "2026-07-03T10:00:00Z"
    ---

    ## Body text starts here
"""

from __future__ import annotations

from typing import Any


def wrap(body: str, meta: dict[str, Any]) -> str:
    """Wrap *body* with YAML frontmatter from *meta*.

    Args:
        body: Markdown body text (without frontmatter).
        meta: Metadata dict (uuid, timestamps, tags, domain-specific keys).
              Values are serialised via PyYAML; ``None`` values are omitted.

    Returns:
        Full markdown string with frontmatter.
    """
    import yaml

    front = yaml.dump(
        {k: v for k, v in meta.items() if v is not None},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    return f"---\n{front}\n---\n\n{body}"


def unwrap(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from *text* and return ``(meta, body)``.

    If no frontmatter delimiter (``---``) is found, returns
    ``({}, text)`` — the caller can still attempt to import.

    Args:
        text: Full markdown text, optionally starting with frontmatter.

    Returns:
        Tuple of ``(meta_dict, body_string)``.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text

    # Find the closing --- (second occurrence)
    rest = stripped[3:].lstrip()
    end_idx = rest.find("\n---")
    if end_idx == -1:
        return {}, text

    front_raw = rest[:end_idx].strip()
    body = rest[end_idx + 4:].lstrip()
    if not front_raw:
        return {}, body

    import yaml
    try:
        meta: dict[str, Any] = yaml.safe_load(front_raw)
        if not isinstance(meta, dict):
            return {}, body
        return meta, body
    except yaml.YAMLError:
        return {}, body

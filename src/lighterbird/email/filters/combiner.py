"""Sieve script combining engine — merges multiple scripts into one.

Since ManageSieve servers accept only one active script, all user-active
scripts for an account are combined server-side before upload.

Algorithm:
  1. Collect all ``require [...]`` declarations, deduplicate capabilities.
  2. Strip require lines from individual script bodies.
  3. Wrap each body with a ``// === Script: <name> ===`` comment header.
  4. Emit: combined require; wrapped bodies.

Conflict detection is informational (non-blocking warnings):
  - Same ``fileinto`` target appearing in multiple scripts.
  - Multiple scripts with ``vacation``.
  - ``stop;`` that may shadow later rules.
"""

from __future__ import annotations

import re
from typing import Any


_REQUIRE_RE = re.compile(r'require\s+\[([^\]]+)\]\s*;')
_STOP_RE = re.compile(r'\bstop\s*;')
_VACATION_RE = re.compile(r'\bvacation\s')
_FILEINTO_RE = re.compile(r'\bfileinto\s+"([^"]+)"')


def _parse_require(content: str) -> set[str]:
    """Extract capability names from a ``require`` statement."""
    m = _REQUIRE_RE.search(content)
    if not m:
        return set()
    return {c.strip().strip('"\'') for c in m.group(1).split(",")}


def _strip_require(content: str) -> str:
    """Remove the ``require`` statement for safe concatenation."""
    return _REQUIRE_RE.sub("", content).strip()


def _fileinto_targets(content: str) -> set[str]:
    """Return the set of folders referenced by ``fileinto``."""
    return set(_FILEINTO_RE.findall(content))


def combine_scripts(
    scripts: list[dict[str, str]],
) -> tuple[str, list[dict[str, Any]]]:
    """Combine multiple Sieve scripts into one.

    Args:
        scripts: Ordered list of ``{"name": str, "content": str}`` dicts.

    Returns:
        ``(combined_script, warnings)`` where warnings is a list of
        ``{"type": ..., "message": ..., "scripts": [names]}`` dicts.
    """
    warnings: list[dict[str, Any]] = []

    # 1. Collect and deduplicate require capabilities
    all_caps: set[str] = set()
    script_bodies: list[str] = []
    seen_fileinto: dict[str, list[str]] = {}
    seen_vacation: list[str] = []
    seen_stop: list[str] = []

    for s in scripts:
        content = s.get("content", "").strip()
        if not content:
            continue
        name = s.get("name", "?")

        # Collect require capabilities
        caps = _parse_require(content)
        all_caps.update(caps)

        # Detect fileinto targets
        targets = _fileinto_targets(content)
        for t in targets:
            if t in seen_fileinto:
                seen_fileinto[t].append(name)
            else:
                seen_fileinto[t] = [name]

        # Detect vacation
        if _VACATION_RE.search(content):
            seen_vacation.append(name)

        # Detect stop
        if _STOP_RE.search(content):
            seen_stop.append(name)

        # Strip require and wrap
        body = _strip_require(content)
        script_bodies.append(f"// === Script: {name} ===\n{body}")

    # 2. Generate warnings
    for target, names in seen_fileinto.items():
        if len(names) > 1:
            warnings.append({
                "type": "duplicate_fileinto",
                "message": f"Multiple scripts fileinto '{target}': {', '.join(names)}",
                "scripts": list(names),
            })
    if len(seen_vacation) > 1:
        warnings.append({
            "type": "multiple_vacation",
            "message": f"Multiple scripts define vacation: {', '.join(seen_vacation)}. "
                       f"Only the last one will take effect.",
            "scripts": list(seen_vacation),
        })
    if len(seen_stop) > 1:
        warnings.append({
            "type": "multiple_stop",
            "message": f"Multiple scripts contain 'stop;': {', '.join(seen_stop)}. "
                       f"Later rules may be shadowed.",
            "scripts": list(seen_stop),
        })

    # 3. Build combined script
    parts: list[str] = []

    # Emit require
    if all_caps:
        caps_str = ", ".join(f'"{c}"' for c in sorted(all_caps))
        parts.append(f"require [{caps_str}];")

    parts.append("")
    parts.append(f"// === Combined from {len(scripts)} script(s) ===")
    parts.append("")

    for body in script_bodies:
        parts.append(body)
        parts.append("")

    combined = "\n".join(parts).strip()
    return combined, warnings


def check_conflicts(
    scripts: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Analyze scripts for conflicts without combining.

    Returns the same warning format as :func:`combine_scripts`.
    """
    _, warnings = combine_scripts(scripts)
    return warnings


__all__ = ["combine_scripts", "check_conflicts"]

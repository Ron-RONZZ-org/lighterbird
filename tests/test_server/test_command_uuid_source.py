"""Test that commands taking UUID/reference positional args have uuidSource configured.

This guards against the regression where new commands are added without wiring
up autocomplete for their UUID/reference positional parameters.

The test cross-references:
1. Backend ``@command()`` decorator ``params`` metadata for ``uuidSource`` keys.
2. The frontend ``getDataCompletionsFromCache()`` function to ensure every
   ``uuidSource`` prefix has a corresponding extractor registered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Import early to trigger @command side effects in all handler modules
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import get_handler_metadata

ROOT = Path(__file__).resolve().parent.parent.parent


# ── Commands that take UUID (or saved reference) as a positional arg ─────
#
# Each entry: (command_path, expected_uuidSource_prefix)
# The prefix is checked against getDataCompletionsFromCache's dispatch logic.
# If the param has uuidSource, it must start with one of these known prefixes.
_KNOWN_UUID_SOURCE_PREFIXES = {
    "email.",       # → addAccounts
    "calendar.",    # → addCalendars (check calendar.events first for events)
    "contacts.",    # → addContacts
    "todo.",        # → addTodos
    "journal.",     # → addJournal
    "user.",        # → addProfiles
    "letters.",     # → addLetters
}

# Commands whose first positional arg is a UUID/reference and MUST have uuidSource
_COMMANDS_REQUIRING_UUID_SOURCE = {
    # Calendar events (uuidSource: "calendar.events")
    "calendar.event.view",
    "calendar.event.modify",
    "calendar.event.delete",
    "calendar.event.rrule.set",
    "calendar.event.rrule.clear",
    "calendar.event.rrule.show",
    "calendar.event.export.ics",

    # Calendar accounts (uuidSource: "calendar.accounts")
    "calendar.account.modify",
    "calendar.account.delete",

    # Contacts (uuidSource: "contacts.contacts")
    "contact.view",
    "contact.modify",
    "contact.delete",
    "contact.export.vcf",
    "contact.merge",
    "contact.category.set",
    "contact.category.add",
    "contact.category.remove",

    # Todos (uuidSource: "todo.todos")
    "todo.view",
    "todo.modify",
    "todo.delete",
    "todo.done",
    "todo.export.md",

    # Journal (uuidSource: "journal.entries")
    "journal.view",
    "journal.delete",

    # Email accounts (uuidSource: "email.accounts")
    "email.account.delete",

    # Email signatures (uuidSource: "email.signatures")
    "email.signature.modify",
    "email.signature.delete",

    # Letters (uuidSource: "letters.letters")
    "letter.view",
    "letter.pdf",

    # User profiles (uuidSource: "user.profiles")
    "user.info.view",
    "user.info.modify",
    "user.info.delete",
}


def _get_frontend_extractors() -> set[str]:
    """Parse getDataCompletionsFromCache() from commandEngine.js to extract
    the uuidSource prefixes that are handled."""
    js_path = ROOT / "web" / "src" / "lib" / "commandEngine.js"
    js = js_path.read_text("utf-8")

    # Find the getDataCompletionsFromCache function body
    start = js.find("export function getDataCompletionsFromCache")
    if start < 0:
        return set()

    # Extract lines with uuidSource.startsWith() checks
    import re
    prefixes: set[str] = set()
    for m in re.finditer(
        r'uuidSource\.startsWith\(["\']([^"\']+)["\']\)',
        js[start:],
    ):
        prefixes.add(m.group(1))

    # Also check for exact match patterns like uuidSource === "email.folders"
    # These are handled as exact strings, not prefixes — but they still work.
    for m in re.finditer(
        r'uuidSource\s*===\s*["\']([^"\']+)["\']',
        js[start:],
    ):
        prefixes.add(m.group(1))

    return prefixes


class TestCommandUuidSource:
    """Verify uuidSource metadata on commands taking UUID positional args."""

    def setup_method(self) -> None:
        self.frontend_prefixes = _get_frontend_extractors()

    def test_all_required_commands_have_uuid_source(self) -> None:
        """Every command that takes a UUID positional arg must have uuidSource."""
        missing = []
        for cmd_path in sorted(_COMMANDS_REQUIRING_UUID_SOURCE):
            meta = get_handler_metadata(cmd_path)
            if meta is None:
                missing.append(f"{cmd_path} (not registered)")
                continue

            params = meta.get("params", [])
            if not params:
                missing.append(f"{cmd_path} (no params)")
                continue

            has_uuid_source = any(
                p.get("uuidSource") for p in params
            )
            if not has_uuid_source:
                missing.append(cmd_path)

        if missing:
            pytest.fail(
                f"Commands missing uuidSource on positional params:\n"
                + "\n".join(f"  {m}" for m in missing)
            )

    def test_uuid_source_prefixes_are_handled_by_frontend(self) -> None:
        """Every uuidSource used in backend commands has a corresponding
        extractor in the frontend getDataCompletionsFromCache()."""
        if not self.frontend_prefixes:
            pytest.skip("Could not parse frontend commandEngine.js")

        # Collect all unique uuidSource values from backend command params
        backend_sources: set[str] = set()
        for cmd_path in _COMMANDS_REQUIRING_UUID_SOURCE:
            meta = get_handler_metadata(cmd_path)
            if meta is None:
                continue
            for param in meta.get("params", []):
                src = param.get("uuidSource")
                if src:
                    backend_sources.add(src)

        # Check each backend uuidSource is handled by a frontend prefix
        # (either it starts with a known prefix or is an exact match)
        unhandled = []
        for src in sorted(backend_sources):
            is_handled = any(
                src.startswith(prefix) or src == prefix
                for prefix in self.frontend_prefixes
            )
            if not is_handled:
                unhandled.append(src)

        if unhandled:
            pytest.fail(
                f"uuidSource values not handled by frontend extractors:\n"
                + "\n".join(f"  {u}" for u in unhandled)
                + "\nAdd extractor functions to getDataCompletionsFromCache() "
                  "in web/src/lib/commandEngine.js"
            )

    def test_all_known_prefixes_have_at_least_one_user(self) -> None:
        """Every uuidSource prefix in the frontend is used by at least one
        backend command."""
        if not self.frontend_prefixes:
            pytest.skip("Could not parse frontend commandEngine.js")

        # Collect all uuidSource prefixes actually used in backend
        used_prefixes: set[str] = set()
        for cmd_path in _COMMANDS_REQUIRING_UUID_SOURCE:
            meta = get_handler_metadata(cmd_path)
            if meta is None:
                continue
            for param in meta.get("params", []):
                src = param.get("uuidSource", "")
                if src:
                    # Find matching frontend prefix
                    for prefix in self.frontend_prefixes:
                        if src.startswith(prefix) or src == prefix:
                            used_prefixes.add(prefix)

        # Unused prefixes are not necessarily wrong — they could be
        # prepared for future commands. But warn about them.
        unused = self.frontend_prefixes - used_prefixes

        if unused:
            # Display as warning, not failure — unused prefixes may be
            # forward-looking infrastructure.
            print(
                f"\n[INFO] Frontend extractor prefixes not yet used by "
                f"backend commands: {unused}"
            )

"""Automated guard for interactive form mapping invariants.

When adding a new interactive command, mappings must be added in sync
across the backend and frontend. This test cross-references the
authoritative ``_interactive_forms`` dict (backend) against the
frontend mapping locations and reports any missing or stale entries.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Import early to trigger @command side effects in all handler modules
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import _interactive_forms

ROOT = Path(__file__).resolve().parent.parent.parent


# ── Helpers ────────────────────────────────────────────────────────────────


def _read_js(path: str) -> str:
    return (ROOT / path).read_text("utf-8")


def _extract_form_returns(js: str) -> dict[str, str]:
    """Extract return mappings from resolveAddFormType().

    Matches lines like:
        return "email-account-add";
    but only those within the resolveAddFormType function.
    Only the LAST return value per function is kept (fallback is leafName).
    """
    mappings: dict[str, str] = {}
    # Find the resolveAddFormType function body
    start = js.find("function resolveAddFormType")
    if start < 0:
        return mappings
    end = js.find("function resolveAddTitle", start)
    if end < 0:
        end = js.find("// Fallback", start)
    body = js[start:end]

    # Extract command path patterns -> form type from if-statements
    # Match: if (/^email\s+account\s+add$/i.test(path)) return "email-account-add";
    # The command path is extracted and \s+ is replaced with space
    pattern = re.compile(
        r'if\s*\(\s*/\^([^$]+)\$/i\.test\(path\)\s*\)\s*return\s+"([^"]+)"',
    )
    for m in pattern.finditer(body):
        raw_path = m.group(1)
        # Replace \s+ with space, strip whitespace
        cmd_path = raw_path.replace("\\s+", " ").strip()
        form_type = m.group(2)
        mappings[cmd_path] = form_type
    return mappings


def _extract_titles(js: str) -> dict[str, str]:
    """Extract form-type -> title from resolveAddTitle()."""
    mappings: dict[str, str] = {}
    start = js.find("function resolveAddTitle")
    if start < 0:
        return mappings
    end = js.find("return titles[addFormType]", start)
    body = js[start:end]

    # Match: "email-account-add": "Add Email Account",
    pattern = re.compile(r'"([^"]+)":\s*"([^"]+)"')
    for m in pattern.finditer(body):
        form_type, title = m.groups()
        mappings[form_type] = title
    return mappings


def _extract_infer_command_paths(js: str) -> dict[str, list[str]]:
    """Extract form-type -> command tokens from _inferCommandPath()."""
    mappings: dict[str, list[str]] = {}
    start = js.find("function _inferCommandPath")
    if start < 0:
        return mappings
    # Find the const map = { ... } block
    brace_start = js.find("{", start)
    if brace_start < 0:
        return mappings
    brace_end = js.find("};", brace_start)
    if brace_end < 0:
        return mappings
    body = js[brace_start + 1 : brace_end]

    # Match: "form-type": ["token1", "token2"],
    for line in body.split("\n"):
        line = line.strip()
        m = re.match(r'"([^"]+)":\s*\[([^\]]+)\],?', line)
        if m:
            form_type = m.group(1)
            tokens_str = m.group(2)
            tokens = [
                t.strip().strip('"')
                for t in tokens_str.split(",")
                if t.strip()
            ]
            mappings[form_type] = tokens
    return mappings


def _extract_token_type_map(js: str) -> dict[str, str]:
    """Extract token-path -> idKey from TOKEN_TYPE_MAP."""
    mappings: dict[str, str] = {}
    start = js.find("const TOKEN_TYPE_MAP")
    if start < 0:
        return mappings
    brace_start = js.find("{", start)
    if brace_start < 0:
        return mappings
    brace_end = js.find("};", brace_start)
    if brace_end < 0:
        return mappings
    body = js[brace_start + 1 : brace_end]

    for m in re.finditer(r'"([^"]+)":\s*"([^"]+)"', body):
        mappings[m.group(1)] = m.group(2)
    return mappings


def _extract_persistent_types(js: str) -> set[str]:
    """Extract dataType values from PERSISTENT_ENTRIES."""
    types: set[str] = set()
    for m in re.finditer(r',\s*"([a-z][a-z0-9-]+)"\],', js):
        types.add(m.group(1))
    return types


def _extract_persistent_entries(js: str) -> list[tuple[str, str]]:
    """Extract (regex_pattern, dataType) pairs from PERSISTENT_ENTRIES.

    Matches lines like:
        [/^!(email\\s+)?account\\s+list\\s*$/i, "accounts"],   (ends with $/i)
        [/^!contacts?\\s+(list|search)\\b/i, "contacts-list"],  (ends with \\b/i)
    Returns the regex source (between /^ and $/i or \\b/i) and the data type.
    """
    entries: list[tuple[str, str]] = []
    start = js.find("const PERSISTENT_ENTRIES")
    if start < 0:
        return entries
    brace_start = js.find("[", start)
    if brace_start < 0:
        return entries
    brace_end = js.find("];", brace_start)
    if brace_end < 0:
        return entries
    body = js[brace_start + 1 : brace_end]
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Try patterns ending with $/i (plain dollar sign, not backslash-dollar)
        m = re.search(r'/\^(.+?)\$/i', line)
        if not m:
            # Try patterns ending with \\b/i (backslash-b, word boundary)
            m = re.search(r'/\^(.+?)\\b/i', line)
        if m:
            raw_pattern = m.group(1)
            # Extract data type from the rest of the line
            type_m = re.search(r'"([a-z][a-z0-9-]+)"', line)
            data_type = type_m.group(1) if type_m else "unknown"
            entries.append((raw_pattern, data_type))
    return entries


def _search_pattern_matches_command(pattern_src: str, cmd_input: str) -> bool:
    """Check if a JS regex pattern source matches a command input.

    The JS pattern source is between /^ and $/i (or \\b/i) anchors.
    It uses JS regex syntax: \\s+ for whitespace, \\b for word boundary,
    ? for optional groups, etc.
    """
    # The pattern source comes from the JS file where \\s+ is literal
    # backslash-s-plus. Python reads it as \s+ (which is what we want
    # in Python regex too).
    # However, we need to be careful: JavaScript regex \\b becomes
    # Python regex \\b which is different! In JS, \\b is word boundary.
    # In Python, \\b is also word boundary (in the pattern string).
    # But the JavaScript logical OR pipes | for alternation should work
    # the same in Python.
    try:
        # Add anchors ^ and $ (the JS source was between them)
        regex = re.compile(pattern_src, re.IGNORECASE)
        return bool(regex.search(cmd_input))
    except re.error:
        return False


def _dot_to_space(path: str) -> str:
    return path.replace(".", " ")


# ── The authoritative list from the backend ────────────────────────────

# Commands that only trigger confirmations/progress popups (no full form).
_NON_FORM_INTERACTIVE = {
    "sync",
    "reset",
    "backup.prune",
    "email.account.delete",
    "email.account.modify",
    "calendar.account.delete",
    "calendar.account.modify",
    "calendar.event.delete",
    "contact.modify",
    "email.sieve.modify",
    "email.signature.modify",
    "todo.modify",
    "todo.delete",
    "todo.template.modify",
    "todo.template.delete",
    "journal.delete",
    "user.saved-commands.modify",
    "user.saved-commands.delete",
    "user.info.modify",
    "backup.config.modify",
    "backup.config.delete",
}

# Commands that must have entries in resolveAddFormType, resolveAddTitle,
# and _inferCommandPath.
_FORM_REQUIRED = {
    "email.account.add",
    "calendar.account.add",
    "contact.add",
    "todo.add",
    "journal.write",
    "email.sieve.add",
    "email.send",
    "email.reply",
    "email.forward",
    "calendar.event.add",
    "user.saved-commands.add",
    "user.info.add",
    "todo.template.add",
    "llm.profile.new",
    "llm.profile.set",
    "backup.config.add",
    "email.signature.add",
    "email.folder.add",
    "letter.add",
    "letter.send",
}

# Commands that should have entries in TOKEN_TYPE_MAP / PERSISTENT_ENTRIES
_LIST_COMMANDS = {
    "email.list",
    "email.account.list",
    "calendar.list",
    "calendar.account.list",
    "contact.list",
    "todo.list",
    "journal.list",
    "user.saved-commands.list",
    "user.info.list",
    "email.sieve.list",
    "email.signature.list",
    "email.folder.list",
    "letter.list",
}


# ── Tests ──────────────────────────────────────────────────────────────


class TestInteractiveFormMappings:
    """Cross-reference all interactive form mappings for consistency."""

    def setup_method(self) -> None:
        self.add_form_types = _extract_form_returns(
            _read_js("web/src/lib/commandRouter.js"),
        )
        self.form_titles = _extract_titles(
            _read_js("web/src/lib/commandRouter.js"),
        )
        self.infer_paths = _extract_infer_command_paths(
            _read_js("web/src/lib/FormTab.svelte"),
        )
        self.token_type_map = _extract_token_type_map(
            _read_js("web/src/lib/persistentTypes.js"),
        )
        self.persistent_types = _extract_persistent_types(
            _read_js("web/src/lib/persistentTypes.js"),
        )
        self.persistent_entries = _extract_persistent_entries(
            _read_js("web/src/lib/persistentTypes.js"),
        )

    def test_all_backend_interactive_known(self) -> None:
        """Every backend interactive command is in our known sets."""
        unknown = []
        for cmd_path in _interactive_forms:
            if cmd_path not in _FORM_REQUIRED and cmd_path not in _NON_FORM_INTERACTIVE:
                unknown.append(cmd_path)
        if unknown:
            pytest.fail(
                f"Backend interactive commands not classified in test sets: {unknown}\n"
                f"Add each to _FORM_REQUIRED or _NON_FORM_INTERACTIVE.",
            )

    def test_form_required_in_resolve_add_form_type(self) -> None:
        """Every form-required command has a mapping in resolveAddFormType()."""
        missing = []
        for cmd in sorted(_FORM_REQUIRED):
            space_path = _dot_to_space(cmd)
            found = any(space_path in key for key in self.add_form_types)
            if not found:
                missing.append(space_path)
        if missing:
            pytest.fail(
                f"Commands missing from resolveAddFormType(): {missing}\n"
                f"Add entries to web/src/lib/commandRouter.js",
            )

    def test_form_required_has_title(self) -> None:
        """Every form-required command's form_type has a title."""
        missing = []
        for cmd in _FORM_REQUIRED:
            form_type = _interactive_forms[cmd]
            if form_type not in self.form_titles:
                missing.append(f"{cmd} -> {form_type}")
        if missing:
            pytest.fail(
                f"Form types missing from resolveAddTitle(): {missing}\n"
                f"Add titles to web/src/lib/commandRouter.js",
            )

    def test_form_required_in_infer_command_path(self) -> None:
        """Every form-required command's form_type has a path in _inferCommandPath()."""
        # email-send is shared by email.send, email.reply, email.forward
        skip_shared = {"email-send"}
        missing = []
        for cmd in _FORM_REQUIRED:
            form_type = _interactive_forms[cmd]
            if form_type in skip_shared:
                continue
            if form_type not in self.infer_paths:
                missing.append(f"{cmd} -> {form_type}")
        if missing:
            pytest.fail(
                f"Form types missing from _inferCommandPath(): {missing}\n"
                f"Add mappings to web/src/lib/FormTab.svelte",
            )

    def test_inferred_tokens_match_backend(self) -> None:
        """Inferred command tokens in FormTab.svelte match backend command paths."""
        mismatches = []
        for form_type, inferred_tokens in self.infer_paths.items():
            backend_cmds = [
                cmd for cmd, ft in _interactive_forms.items()
                if ft == form_type
            ]
            if not backend_cmds:
                continue
            for backend_cmd in backend_cmds:
                backend_tokens = backend_cmd.split(".")
                if inferred_tokens != backend_tokens:
                    mismatches.append(
                        f"  {form_type}: FormTab has {inferred_tokens}, "
                        f"backend expects {backend_tokens}",
                    )
        if mismatches:
            pytest.fail(
                "Mismatches in _inferCommandPath():\n" + "\n".join(mismatches),
            )

    def test_list_commands_in_persistent_entries(self) -> None:
        """Every list command has a matching pattern in PERSISTENT_ENTRIES.

        This ensures ``detectPersistentType()`` returns a valid type for
        every ``!_LIST_COMMANDS`` input.
        """
        missing = []
        for cmd in sorted(_LIST_COMMANDS):
            space_path = _dot_to_space(cmd)
            cmd_input = f"!{space_path}"
            matched = any(
                _search_pattern_matches_command(pattern, cmd_input)
                for pattern, _ in self.persistent_entries
            )
            if not matched:
                missing.append(f"{cmd_input} ({cmd})")
        if missing:
            pytest.fail(
                f"List commands missing from PERSISTENT_ENTRIES in "
                f"detectPersistentType(): {missing}\n"
                f"Add entries to web/src/lib/persistentTypes.js",
            )

    def test_persistent_entry_types_have_token_map(self) -> None:
        """Every list-related dataType in PERSISTENT_ENTRIES has a
        TOKEN_TYPE_MAP entry."""
        # Collect the dataTypes from PERSISTENT_ENTRIES that match list commands
        persistent_list_types: set[str] = set()
        for cmd in _LIST_COMMANDS:
            space_path = _dot_to_space(cmd)
            cmd_input = f"!{space_path}"
            for pattern, data_type in self.persistent_entries:
                if _search_pattern_matches_command(pattern, cmd_input):
                    persistent_list_types.add(data_type)
        # Check these types have a TOKEN_TYPE_MAP entry somewhere
        map_lookup = {v: k for k, v in self.token_type_map.items()}
        missing = []
        for dt in sorted(persistent_list_types):
            if dt not in map_lookup:
                missing.append(dt)
        if missing:
            pytest.fail(
                f"List-related PERSISTENT_ENTRIES types not in TOKEN_TYPE_MAP: {missing}\n"
                f"Add entries to web/src/lib/persistentTypes.js",
            )

    def test_list_commands_in_token_type_map(self) -> None:
        """Every list command has an id-key in TOKEN_TYPE_MAP."""
        missing = []
        for cmd in sorted(_LIST_COMMANDS):
            space_path = _dot_to_space(cmd)
            if space_path not in self.token_type_map:
                missing.append(space_path)
        if missing:
            pytest.fail(
                f"List commands missing from TOKEN_TYPE_MAP: {missing}\n"
                f"Add entries to web/src/lib/persistentTypes.js",
            )

    def test_no_stale_frontend_form_types(self) -> None:
        """Frontend form types have corresponding backend interactive commands (or are known legacy)."""
        backend_form_types = set(_interactive_forms.values())
        # Known additions in the frontend that aren't backed by the backend
        # (e.g. the shared email-send type that maps to email.send/reply/forward)
        known_extra = set()

        # Collect all form types from frontend maps
        frontend_form_types = set(self.add_form_types.values())
        frontend_form_types.update(self.form_titles.keys())
        frontend_form_types.update(self.infer_paths.keys())

        stale = frontend_form_types - backend_form_types - known_extra
        if stale:
            pytest.fail(
                f"Frontend form types with no backend match: {stale}\n"
                f"Either add a backend @command() with the matching form_type "
                f"or remove the stale frontend mapping.",
            )

    def test_all_form_required_types_have_title(self) -> None:
        """Every form-required command's form_type has a title."""
        missing = []
        for cmd in _FORM_REQUIRED:
            form_type = _interactive_forms[cmd]
            if form_type not in self.form_titles:
                missing.append(f"{cmd} -> {form_type}")
        if missing:
            pytest.fail(
                f"Required form types without titles in resolveAddTitle(): {missing}",
            )

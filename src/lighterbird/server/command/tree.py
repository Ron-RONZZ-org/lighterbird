"""Structured command tree for frontend autocomplete.

This is the single source of truth for the command hierarchy served via
``GET /api/v1/command/tree``. When adding new commands, the tree node
must be added here — otherwise it won't appear in frontend autocomplete.

Each node has:
    name        — the token the user types
    description — help text shown in autocomplete
    children    — sub-commands (non-leaf nodes)
    params      — positional arguments (leaf nodes)
    flags       — flag arguments (e.g. --calendar)
    interactive — if true, opens an interactive form popup
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Type helpers (for readability)
# ---------------------------------------------------------------------------

FlagDef = dict[str, Any]
"""A flag definition dict with keys: name, short (optional), type, help (optional)."""

ParamDef = dict[str, Any]
"""A parameter definition dict with keys: name, required, type, placeholder (optional),
repeatable (optional), uuidSource (optional), sensitive (optional)."""

CommandNode = dict[str, Any]
"""A node in the command tree with keys: name, description (optional), children (optional),
params (optional), flags (optional), interactive (optional)."""


# ---------------------------------------------------------------------------
# Tree data
# ---------------------------------------------------------------------------

def get_command_tree() -> list[CommandNode]:
    """Return the full structured command tree for autocomplete."""
    return [
        # ── Email ──────────────────────────────────────────────────────────
        {
            "name": "email",
            "description": "Email operations",
            "children": [
                {
                    "name": "list",
                    "description": "Show inbox messages",
                    "params": [],
                    "flags": [
                        {"name": "limit", "short": "l", "type": "number", "help": "Max messages (default 20)"},
                        {"name": "folder", "short": "f", "type": "string", "help": "Filter by folder(s); comma-separated", "uuidSource": "email.folders"},
                        {"name": "not-folder", "type": "string", "help": "Exclude folder(s); comma-separated"},
                        {"name": "all", "type": "flag", "help": "Include trash folder"},
                        {"name": "sort", "short": "s", "type": "string", "help": "Sort order: newest (default), oldest, sender"},
                        {"name": "group", "short": "g", "type": "string", "help": "Group by: conversation (default none)"},
                    ],
                },
                {
                    "name": "read",
                    "description": "Read a message by UUID",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "message-uuid", "uuidSource": "email.listMessages"},
                    ],
                },
                {
                    "name": "send",
                    "description": "Send an email",
                    "interactive": True,
                    "params": [
                        {"name": "to", "required": True, "type": "string", "placeholder": "recipient@example.com"},
                        {"name": "subject", "required": True, "type": "string"},
                        {"name": "body", "required": False, "type": "string"},
                    ],
                    "flags": [
                        {"name": "account", "short": "a", "type": "uuid", "help": "Account UUID (default: first)", "uuidSource": "email.listAccounts"},
                        {"name": "cc", "type": "string", "help": "CC recipient"},
                        {"name": "bcc", "type": "string", "help": "BCC recipient"},
                        {"name": "priority", "short": "p", "type": "number", "help": "Priority 1 (highest) to 5 (lowest)"},
                        {"name": "body-format", "type": "string", "help": "Body format: markdown (default), html, or plain"},
                        {"name": "in-reply-to", "type": "string", "help": "Message-ID being replied to (for threading)"},
                        {"name": "file", "short": "f", "type": "string", "help": "File attachment (name:base64, repeatable)"},
                        {"name": "cowrite", "type": "string", "help": "LLM co-writing instruction (e.g. 'make it formal')"},
                        {"name": "cowrite-diff", "type": "flag", "help": "Show unified diff before applying cowrite"},
                    ],
                },
                {
                    "name": "reply",
                    "description": "Reply to a message (opens compose form)",
                    "interactive": True,
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "message-uuid", "uuidSource": "email.listMessages"},
                    ],
                    "flags": [
                        {"name": "all", "type": "flag", "help": "Reply to all recipients"},
                    ],
                },
                {
                    "name": "forward",
                    "description": "Forward a message (opens compose form)",
                    "interactive": True,
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "message-uuid", "uuidSource": "email.listMessages"},
                    ],
                },
                {
                    "name": "search",
                    "description": "Search messages",
                    "flags": [
                        {"name": "from", "type": "string", "help": "Sender email"},
                        {"name": "subject", "type": "string", "help": "Subject text"},
                        {"name": "body", "type": "string", "help": "Body text"},
                        {"name": "after", "type": "date", "help": "Start date (YYYY-MM-DD)"},
                        {"name": "before", "type": "date", "help": "End date (YYYY-MM-DD)"},
                        {"name": "limit", "short": "l", "type": "number", "help": "Max results"},
                    ],
                },
                {
                    "name": "trash",
                    "description": "Move message to trash",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "message-uuid", "uuidSource": "email.listMessages"},
                    ],
                },
                {
                    "name": "archive",
                    "description": "Archive a message",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "message-uuid", "uuidSource": "email.listMessages"},
                    ],
                },
                {
                    "name": "sieve",
                    "description": "Manage Sieve email filters",
                    "children": [
                        {
                            "name": "list",
                            "description": "List Sieve scripts (with optional per-account activation status)",
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Account email or UUID to show activation status"},
                            ],
                        },
                        {
                            "name": "view",
                            "description": "View a Sieve script",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                            ],
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Account email or UUID to show activation"},
                            ],
                        },
                        {
                            "name": "add",
                            "description": "Create a new global Sieve script",
                            "interactive": True,
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                            ],
                            "flags": [
                                {"name": "file", "short": "f", "type": "string", "help": "Path to .sieve file (recommended over inline content)"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify a Sieve script",
                            "interactive": True,
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                            ],
                            "flags": [
                                {"name": "name", "type": "string", "help": "Rename to"},
                                {"name": "file", "short": "f", "type": "string", "help": "Path to .sieve file with new content"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete Sieve script(s) globally",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name", "repeatable": True},
                            ],
                        },
                        {
                            "name": "activate",
                            "description": "Activate a script on a specific account (requires --account)",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                            ],
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Account email or UUID (required)", "required": True},
                                {"name": "priority", "short": "p", "type": "number", "help": "Execution priority (0=lowest)"},
                            ],
                        },
                        {
                            "name": "deactivate",
                            "description": "Deactivate a script on a specific account (requires --account)",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                            ],
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Account email or UUID (required)", "required": True},
                            ],
                        },
                        {
                            "name": "priority",
                            "description": "Set execution priority for a script on an account",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "script-name"},
                                {"name": "priority", "required": True, "type": "number", "placeholder": "0-999"},
                            ],
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Account email or UUID (required)", "required": True},
                            ],
                        },
                    ],
                },
                {
                    "name": "account",
                    "description": "Manage email accounts",
                    "children": [
                        {
                            "name": "add",
                            "description": "Add a new email account (IMAP/SMTP auto-detected for common providers)",
                            "params": [
                                {"name": "email", "required": True, "type": "string", "placeholder": "user@example.com"},
                            ],
                            "flags": [
                                {"name": "name", "type": "string", "help": "Display name"},
                                {"name": "imap", "type": "string", "help": "IMAP server hostname (auto-detected if omitted)"},
                                {"name": "smtp", "type": "string", "help": "SMTP server hostname (auto-detected if omitted)"},
                                {"name": "password", "type": "string", "help": "Account password", "sensitive": True},
                            ],
                        },
                        {
                            "name": "list",
                            "description": "List email accounts",
                        },
                        {
                            "name": "modify",
                            "description": "Modify an account",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "account-uuid", "uuidSource": "email.listAccounts"},
                            ],
                            "flags": [
                                {"name": "name", "type": "string", "help": "New display name"},
                                {"name": "password", "type": "string", "help": "New password", "sensitive": True},
                                {"name": "imap_server", "type": "string", "help": "New IMAP server"},
                                {"name": "smtp_server", "type": "string", "help": "New SMTP server"},
                                {"name": "managesieve_host", "type": "string", "help": "ManageSieve server hostname"},
                                {"name": "managesieve_port", "type": "number", "help": "ManageSieve port (default 4190)"},
                                {"name": "managesieve-use-tls", "type": "string", "help": "ManageSieve TLS: true/false (default true)"},
                                {"name": "signature", "type": "string", "help": "Account email signature (plain text)"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete email account(s)",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "account-uuid", "uuidSource": "email.listAccounts", "repeatable": True},
                            ],
                        },
                    ],
                },
                {
                    "name": "draft",
                    "description": "List / recall saved email drafts",
                    "params": [
                        {"name": "uuid", "required": False, "type": "uuid", "placeholder": "draft-uuid", "uuidSource": "email.drafts"},
                    ],
                },
                {
                    "name": "signature",
                    "description": "Manage email account signatures",
                    "children": [
                        {
                            "name": "list",
                            "description": "List account signatures",
                            "flags": [
                                {"name": "account", "short": "a", "type": "string", "help": "Filter by account email"},
                            ],
                        },
                        {
                            "name": "add",
                            "description": "Set a signature for an account",
                            "params": [
                                {"name": "email", "required": True, "type": "string", "placeholder": "account-email"},
                                {"name": "text", "required": True, "type": "string"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify an account signature",
                            "params": [
                                {"name": "email", "required": True, "type": "string", "placeholder": "account-email"},
                                {"name": "text", "required": True, "type": "string"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete an account signature",
                            "params": [
                                {"name": "email", "required": True, "type": "string", "placeholder": "account-email"},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── Calendar ───────────────────────────────────────────────────────
        {
            "name": "calendar",
            "description": "Calendar operations",
            "children": [
                {
                    "name": "list",
                    "description": "List calendar events",
                    "params": [
                        {"name": "start", "required": False, "type": "date", "placeholder": "2000-01-01"},
                        {"name": "end", "required": False, "type": "date", "placeholder": "2099-12-31"},
                    ],
                    "flags": [
                        {"name": "calendar", "short": "c", "type": "uuid", "help": "Filter by calendar UUID", "uuidSource": "calendar.listCalendars"},
                        {"name": "query", "short": "q", "type": "string", "help": "Search text"},
                    ],
                },
                {
                    "name": "event",
                    "description": "Manage calendar events",
                    "children": [
                        {
                            "name": "draft",
                            "description": "List / recall saved calendar event drafts",
                            "params": [
                                {"name": "uuid", "required": False, "type": "uuid", "placeholder": "draft-uuid", "uuidSource": "calendar.drafts"},
                            ],
                        },
                        {
                            "name": "add",
                            "description": "Create a new event",
                            "interactive": True,
                            "params": [
                                {"name": "title", "required": True, "type": "string"},
                                {"name": "start", "required": True, "type": "datetime", "placeholder": "2024-06-15T09:00:00Z"},
                                {"name": "end", "required": True, "type": "datetime", "placeholder": "2024-06-15T10:00:00Z"},
                                {"name": "location", "required": False, "type": "string"},
                            ],
                            "flags": [
                                {"name": "calendar", "short": "c", "type": "uuid", "help": "Calendar UUID (defaults to only calendar if one exists)", "uuidSource": "calendar.listCalendars"},
                            ],
                        },
                        {
                            "name": "view",
                            "description": "View event details",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "event-uuid", "uuidSource": "calendar.listEvents"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify an event",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "event-uuid", "uuidSource": "calendar.listEvents"},
                            ],
                            "flags": [
                                {"name": "title", "type": "string", "help": "New title"},
                                {"name": "start", "type": "string", "help": "New start (ISO)"},
                                {"name": "end", "type": "string", "help": "New end (ISO)"},
                                {"name": "location", "type": "string", "help": "New location"},
                                {"name": "description", "type": "string", "help": "New description"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete event(s)",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "event-uuid", "uuidSource": "calendar.listEvents", "repeatable": True},
                            ],
                        },
                        {
                            "name": "search",
                            "description": "Search events",
                            "flags": [
                                {"name": "query", "short": "q", "type": "string", "help": "Search text"},
                                {"name": "start", "type": "date", "help": "Start date (YYYY-MM-DD)"},
                                {"name": "end", "type": "date", "help": "End date (YYYY-MM-DD)"},
                                {"name": "calendar", "short": "c", "type": "uuid", "help": "Calendar UUID filter", "uuidSource": "calendar.listCalendars"},
                            ],
                        },
                    ],
                },
                {
                    "name": "account",
                    "description": "Manage calendar accounts",
                    "children": [
                        {
                            "name": "add",
                            "description": "Add a CalDAV calendar",
                            "params": [
                                {"name": "url", "required": True, "type": "string", "placeholder": "https://..."},
                            ],
                            "flags": [
                                {"name": "username", "type": "string", "help": "CalDAV username"},
                                {"name": "password", "type": "string", "help": "CalDAV password"},
                            ],
                        },
                        {
                            "name": "list",
                            "description": "List calendars",
                        },
                        {
                            "name": "modify",
                            "description": "Modify a calendar",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "calendar-uuid", "uuidSource": "calendar.listCalendars"},
                            ],
                            "flags": [
                                {"name": "url", "type": "string", "help": "New URL"},
                                {"name": "username", "type": "string", "help": "New username"},
                                {"name": "password", "type": "string", "help": "New password", "sensitive": True},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete calendar(s)",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "calendar-uuid", "uuidSource": "calendar.listCalendars", "repeatable": True},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── Contact ────────────────────────────────────────────────────────
        {
            "name": "contact",
            "description": "Contact management",
            "children": [
                {
                    "name": "list",
                    "description": "List contacts",
                    "flags": [
                        {"name": "limit", "short": "l", "type": "number", "help": "Max results (default 50)"},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a contact",
                    "params": [],
                    "flags": [
                        {"name": "first-name", "type": "string", "help": "Given name (required)"},
                        {"name": "last-name", "type": "string", "help": "Family name"},
                        {"name": "email", "type": "string", "help": "Email address(es), tag:value,..."},
                        {"name": "phone", "type": "string", "help": "Phone number(s), tag:value,..."},
                        {"name": "organization", "type": "string", "help": "Organization"},
                        {"name": "notes", "type": "string", "help": "Notes"},
                        {"name": "middle-names", "type": "string", "help": "Middle names"},
                        {"name": "dob", "type": "date", "help": "Date of birth (YYYY-MM-DD)"},
                        {"name": "place-of-birth", "type": "string", "help": "Place of birth"},
                        {"name": "address", "type": "string", "help": "Street address"},
                        {"name": "post-code", "type": "string", "help": "Postal code"},
                        {"name": "position", "type": "string", "help": "Job title / position"},
                        {"name": "custom", "type": "string", "help": "Custom field (key:value, repeatable)"},
                    ],
                },
                {
                    "name": "view",
                    "description": "View contact details",
                    "params": [
                        {"name": "uuid-or-email", "required": True, "type": "string", "placeholder": "uuid or email"},
                    ],
                },
                {
                    "name": "modify",
                    "description": "Modify a contact",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "contact-uuid", "uuidSource": "contact.list"},
                    ],
                    "flags": [
                        {"name": "first-name", "type": "string", "help": "New given name"},
                        {"name": "last-name", "type": "string", "help": "New family name"},
                        {"name": "email", "type": "string", "help": "Email address(es), tag:value,..."},
                        {"name": "phone", "type": "string", "help": "Phone number(s), tag:value,..."},
                        {"name": "organization", "type": "string", "help": "New organization"},
                        {"name": "notes", "type": "string", "help": "New notes"},
                        {"name": "middle-names", "type": "string", "help": "Middle names"},
                        {"name": "dob", "type": "date", "help": "Date of birth (YYYY-MM-DD)"},
                        {"name": "place-of-birth", "type": "string", "help": "Place of birth"},
                        {"name": "address", "type": "string", "help": "Street address"},
                        {"name": "post-code", "type": "string", "help": "Postal code"},
                        {"name": "position", "type": "string", "help": "Job title / position"},
                        {"name": "custom", "type": "string", "help": "Custom field (key:value, repeatable)"},
                    ],
                },
                {
                    "name": "delete",
                    "description": "Delete contact(s)",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "contact-uuid", "uuidSource": "contact.list", "repeatable": True},
                    ],
                },
                {
                    "name": "search",
                    "description": "Search contacts",
                    "params": [
                        {"name": "query", "required": False, "type": "string", "placeholder": "search text"},
                    ],
                },
            ],
        },

        # ── Todo ───────────────────────────────────────────────────────────
        {
            "name": "todo",
            "description": "Task management",
            "children": [
                {
                    "name": "list",
                    "description": "List all todos (flat view)",
                    "flags": [
                        {"name": "status", "type": "string", "help": "Filter by status (pending|done)"},
                    ],
                },
                {
                    "name": "draft",
                    "description": "List / recall saved todo drafts",
                    "params": [
                        {"name": "uuid", "required": False, "type": "uuid", "placeholder": "draft-uuid", "uuidSource": "todo.drafts"},
                    ],
                },
                {
                    "name": "tree",
                    "description": "List todos (tree view with expand/collapse)",
                    "flags": [
                        {"name": "status", "type": "string", "help": "Filter by status (pending|done)"},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a new todo",
                    "interactive": True,
                    "listCommand": ["todo", "list"],
                    "params": [
                        {"name": "title", "required": True, "type": "string"},
                    ],
                    "flags": [
                        {"name": "due", "type": "date", "help": "Due date (YYYY-MM-DD)"},
                        {"name": "priority", "type": "number", "help": "Priority (1-10)"},
                        {"name": "description", "type": "string", "help": "Description"},
                        {"name": "parent", "type": "string", "help": "Parent UUID(s); comma-separated", "uuidSource": "todo.list"},
                        {"name": "dependency", "type": "string", "help": "Depends on UUID(s); comma-separated", "uuidSource": "todo.list"},
                        {"name": "file", "type": "string", "help": "Attach file(s); comma-separated paths/URLs"},
                        {"name": "template", "type": "string", "help": "Template name for structured fields"},
                        {"name": "cowrite", "type": "string", "help": "LLM co-writing instruction (e.g. 'add more detail')"},
                        {"name": "cowrite-diff", "type": "flag", "help": "Show unified diff before applying cowrite"},
                    ],
                },
                {
                    "name": "view",
                    "description": "View todo details",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "todo-uuid", "uuidSource": "todo.list"},
                    ],
                },
                {
                    "name": "done",
                    "description": "Mark todo as done",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "todo-uuid", "uuidSource": "todo.list", "repeatable": True},
                    ],
                },
                {
                    "name": "modify",
                    "description": "Modify a todo",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "todo-uuid", "uuidSource": "todo.list"},
                    ],
                    "flags": [
                        {"name": "title", "type": "string", "help": "New title"},
                        {"name": "description", "type": "string", "help": "New description"},
                        {"name": "priority", "type": "number", "help": "New priority (1-10)"},
                        {"name": "due", "type": "date", "help": "New due date"},
                        {"name": "status", "type": "string", "help": "New status (pending|done)"},
                        {"name": "parent", "type": "string", "help": "New parent UUID(s); comma-separated"},
                    ],
                },
                        {
                            "name": "delete",
                            "description": "Delete todo(s)",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "todo-uuid", "uuidSource": "todo.list", "repeatable": True},
                    ],
                },
                {
                    "name": "search",
                    "description": "Search todos",
                    "params": [
                        {"name": "query", "required": False, "type": "string", "placeholder": "search text"},
                    ],
                    "flags": [
                        {"name": "status", "type": "string", "help": "Filter by status"},
                    ],
                },
                {
                    "name": "template",
                    "description": "Manage todo templates",
                    "children": [
                        {
                            "name": "list",
                            "description": "List all templates",
                        },
                        {
                            "name": "add",
                            "description": "Create a new template",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "template-name"},
                            ],
                            "flags": [
                                {"name": "title-placeholder", "type": "string", "help": "Default title text"},
                                {"name": "text", "type": "string", "help": "A text field name (repeatable); prefix with ! for required"},
                                {"name": "file", "type": "string", "help": "A file field name (repeatable)"},
                                {"name": "markdown", "type": "string", "help": "A markdown field name (repeatable)"},
                            ],
                        },
                        {
                            "name": "view",
                            "description": "View a template's details",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "template-name"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify a template",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "template-name"},
                            ],
                            "flags": [
                                {"name": "new-name", "type": "string", "help": "Rename to"},
                                {"name": "title-placeholder", "type": "string", "help": "Default title text"},
                                {"name": "text", "type": "string", "help": "A text field name (repeatable)"},
                                {"name": "file", "type": "string", "help": "A file field name (repeatable)"},
                                {"name": "markdown", "type": "string", "help": "A markdown field name (repeatable)"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete a template",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "template-name"},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── Journal ────────────────────────────────────────────────────────
        {
            "name": "journal",
            "description": "Journal entries",
            "children": [
                {
                    "name": "list",
                    "description": "List journal entries",
                    "flags": [
                        {"name": "date", "type": "date", "help": "Filter by date (YYYY-MM-DD)"},
                        {"name": "limit", "short": "l", "type": "number", "help": "Max results"},
                    ],
                },
                {
                    "name": "draft",
                    "description": "List / recall saved journal drafts",
                    "params": [
                        {"name": "uuid", "required": False, "type": "uuid", "placeholder": "draft-uuid", "uuidSource": "journal.drafts"},
                    ],
                },
                {
                    "name": "write",
                    "description": "Write a journal entry",
                    "interactive": True,
                    "listCommand": ["journal", "list"],
                    "params": [
                        {"name": "title", "required": True, "type": "string"},
                    ],
                    "flags": [
                        {"name": "date", "type": "date", "help": "Date (YYYY-MM-DD, default: today)"},
                        {"name": "text", "type": "string", "help": "Entry text"},
                        {"name": "cowrite", "type": "string", "help": "LLM co-writing instruction (e.g. 'make it more reflective')"},
                        {"name": "cowrite-diff", "type": "flag", "help": "Show unified diff before applying cowrite"},
                    ],
                },
                {
                    "name": "view",
                    "description": "View a journal entry",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "entry-uuid", "uuidSource": "journal.list"},
                    ],
                },
                {
                    "name": "search",
                    "description": "Search journal entries",
                    "params": [
                        {"name": "query", "required": False, "type": "string", "placeholder": "search text"},
                    ],
                },
                {
                    "name": "delete",
                    "description": "Delete journal entry(s) by UUID",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "entry-uuid", "uuidSource": "journal.list", "repeatable": True},
                    ],
                },
            ],
        },

        # ── Backup ────────────────────────────────────────────────────────
        {
            "name": "backup",
            "description": "Database backup and restore",
            "children": [
                {
                    "name": "now",
                    "description": "Create timestamped backups of all databases",
                    "flags": [
                        {"name": "kind", "type": "string", "help": "What to back up: data|config|all (default: all)"},
                    ],
                },
                {
                    "name": "list",
                    "description": "List available backup snapshots",
                    "flags": [
                        {"name": "stem", "type": "string", "help": "Filter by database (email|calendar|contacts|todo|journal)"},
                        {"name": "strategy", "type": "string", "help": "Filter by strategy id"},
                    ],
                },
                {
                    "name": "restore",
                    "description": "Restore from the latest backup",
                    "flags": [
                        {"name": "timestamp", "type": "string", "help": "Restore a specific snapshot by timestamp prefix"},
                    ],
                },
                {
                    "name": "prune",
                    "description": "Delete old backups, keeping N newest per database",
                    "flags": [
                        {"name": "keep", "short": "k", "type": "number", "help": "Number of backups to keep per database (default: 10)"},
                    ],
                },
                {
                    "name": "config",
                    "description": "View backup config summary",
                    "children": [
                        {
                            "name": "list",
                            "description": "List backup strategies",
                        },
                        {
                            "name": "add",
                            "description": "Add a backup strategy",
                            "flags": [
                                {"name": "id", "type": "string", "help": "Strategy identifier (kebab-case)"},
                                {"name": "label", "type": "string", "help": "Human-readable name"},
                                {"name": "interval", "short": "i", "type": "number", "help": "Interval in minutes (e.g., 0=manual, 0.5=30s, 60=hourly, 1440=daily)"},
                                {"name": "max-copies", "short": "m", "type": "number", "help": "Max backups to keep"},
                                {"name": "target", "type": "string", "help": "local or absolute path"},
                                {"name": "enabled", "type": "string", "help": "true|false"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify a backup strategy",
                            "params": [
                                {"name": "id", "required": True, "type": "string", "placeholder": "strategy-id"},
                            ],
                            "flags": [
                                {"name": "label", "type": "string"},
                                {"name": "interval", "type": "number", "help": "Interval in minutes"},
                                {"name": "max-copies", "type": "number", "help": "Max backups to keep"},
                                {"name": "target", "type": "string", "help": "local or absolute path"},
                                {"name": "enabled", "type": "string", "help": "true|false"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete a backup strategy",
                            "params": [
                                {"name": "id", "required": True, "type": "string", "placeholder": "strategy-id"},
                            ],
                        },
                        {
                            "name": "test",
                            "description": "Test a strategy's target directory",
                            "params": [
                                {"name": "id", "required": True, "type": "string", "placeholder": "strategy-id"},
                            ],
                        },
                    ],
                },
                {
                    "name": "export",
                    "description": "Export all data to a portable directory",
                    "flags": [
                        {"name": "output", "short": "o", "type": "string", "help": "Output directory (default: current dir)"},
                    ],
                },
                {
                    "name": "import",
                    "description": "Import data from an exported directory",
                    "params": [
                        {"name": "path", "required": True, "type": "string", "placeholder": "/path/to/export"},
                    ],
                    "flags": [
                        {"name": "force", "type": "flag", "help": "Overwrite existing files"},
                    ],
                },
            ],
        },

        # ── Sync (unified) ─────────────────────────────────────────────────
        {
            "name": "sync",
            "description": "Synchronize data (email, calendar, todo attachments)",
            "flags": [
                {"name": "email", "type": "flag", "help": "Sync email only"},
                {"name": "calendar", "type": "flag", "help": "Sync calendar only"},
                {"name": "todo-attachments", "type": "flag", "help": "Resync cached attachment files"},
                {"name": "complete", "type": "flag", "help": "Force sync of large files (>5 MB)"},
                {"name": "account", "type": "uuid", "help": "Sync specific email account", "uuidSource": "email.listAccounts"},
                {"name": "calendar-uuid", "type": "uuid", "help": "Sync specific calendar", "uuidSource": "calendar.listCalendars"},
            ],
        },

        # ── LLM ────────────────────────────────────────────────────────────
        {
            "name": "llm",
            "description": "LLM provider configuration",
            "children": [
                {
                    "name": "prompt",
                    "description": "Show current system prompt",
                },
                {
                    "name": "profile",
                    "description": "Manage LLM profiles",
                    "children": [
                        {
                            "name": "show",
                            "description": "Show current LLM configuration",
                        },
                        {
                            "name": "new",
                            "description": "Create a new profile from scratch",
                            "params": [
                                {"name": "protocol", "required": True, "type": "string", "placeholder": "openai|ollama"},
                            ],
                            "flags": [
                                {"name": "alias", "type": "string", "help": "Save as a named profile (e.g. --alias my-work)"},
                                {"name": "api-key", "type": "string", "help": "API key"},
                                {"name": "base-url", "type": "string", "help": "API base URL"},
                                {"name": "model", "type": "string", "help": "Model name"},
                                {"name": "temperature", "type": "string", "help": "Temperature (0.0-2.0)"},
                                {"name": "max-tokens", "type": "string", "help": "Max tokens"},
                            ],
                        },
                        {
                            "name": "set",
                            "description": "Modify current profile settings",
                            "flags": [
                                {"name": "alias", "type": "string", "help": "Save as a named profile (e.g. --alias my-work)"},
                                {"name": "protocol", "type": "string", "help": "API protocol (openai|ollama)"},
                                {"name": "api-key", "type": "string", "help": "API key"},
                                {"name": "base-url", "type": "string", "help": "API base URL"},
                                {"name": "model", "type": "string", "help": "Model name"},
                                {"name": "temperature", "type": "string", "help": "Temperature (0.0-2.0)"},
                                {"name": "max-tokens", "type": "string", "help": "Max tokens"},
                            ],
                        },
                        {
                            "name": "clear",
                            "description": "Clear current profile configuration",
                        },
                        {
                            "name": "load",
                            "description": "Load a saved profile",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "profile-name"},
                            ],
                        },
                        {
                            "name": "list",
                            "description": "List saved profiles",
                        },
                        {
                            "name": "delete",
                            "description": "Delete a saved profile",
                            "params": [
                                {"name": "name", "required": True, "type": "string", "placeholder": "profile-name"},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── User (saved commands) ──────────────────────────────────────────
        {
            "name": "user",
            "description": "User settings, profiles, and saved commands",
            "children": [
                {
                    "name": "saved-commands",
                    "description": "Manage saved command aliases",
                    "children": [
                        {
                            "name": "list",
                            "description": "List all saved commands",
                        },
                        {
                            "name": "add",
                            "description": "Add a saved command alias",
                            "flags": [
                                {"name": "alias", "type": "string", "help": "Short alias name (e.g. ronzz)", "required": True},
                                {"name": "command", "type": "string", "help": "Command template (without !)", "required": True},
                                {"name": "hint", "type": "string", "help": "Description shown in autocomplete"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify a saved command",
                            "params": [
                                {"name": "alias", "required": True, "type": "string", "placeholder": "current-alias"},
                            ],
                            "flags": [
                                {"name": "command", "type": "string", "help": "New command template"},
                                {"name": "alias", "type": "string", "help": "Rename to new alias"},
                                {"name": "hint", "type": "string", "help": "New description"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete saved command(s)",
                            "params": [
                                {"name": "alias", "required": True, "type": "string", "placeholder": "alias", "repeatable": True},
                            ],
                        },
                    ],
                },
                {
                    "name": "info",
                    "description": "Manage user identity profiles",
                    "children": [
                        {
                            "name": "list",
                            "description": "List user profiles",
                        },
                        {
                            "name": "add",
                            "description": "Create a new user profile",
                            "interactive": True,
                            "params": [
                                {"name": "profile-name", "required": True, "type": "string", "placeholder": "work|home|..."},
                            ],
                            "flags": [
                                {"name": "first-name", "type": "string"},
                                {"name": "middle-names", "type": "string"},
                                {"name": "last-name", "type": "string"},
                                {"name": "dob", "type": "string", "help": "Date of birth (YYYY-MM-DD)"},
                                {"name": "place-of-birth", "type": "string"},
                                {"name": "email", "type": "string", "help": "Email (tag:value, repeatable)"},
                                {"name": "phone", "type": "string", "help": "Phone (tag:value, repeatable)"},
                                {"name": "address", "type": "string"},
                                {"name": "post-code", "type": "string"},
                                {"name": "organization", "type": "string"},
                                {"name": "position", "type": "string"},
                                {"name": "notes", "type": "string", "help": "Free-text notes"},
                                {"name": "custom", "type": "string", "help": "Custom field (key:value, repeatable)"},
                            ],
                        },
                        {
                            "name": "view",
                            "description": "View a profile",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "profile-uuid"},
                            ],
                        },
                        {
                            "name": "modify",
                            "description": "Modify a profile",
                            "interactive": True,
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "profile-uuid"},
                            ],
                            "flags": [
                                {"name": "first-name", "type": "string"},
                                {"name": "middle-names", "type": "string"},
                                {"name": "last-name", "type": "string"},
                                {"name": "dob", "type": "string", "help": "Date of birth (YYYY-MM-DD)"},
                                {"name": "place-of-birth", "type": "string"},
                                {"name": "email", "type": "string", "help": "Email (tag:value, repeatable)"},
                                {"name": "phone", "type": "string", "help": "Phone (tag:value, repeatable)"},
                                {"name": "address", "type": "string"},
                                {"name": "post-code", "type": "string"},
                                {"name": "organization", "type": "string"},
                                {"name": "position", "type": "string"},
                                {"name": "notes", "type": "string", "help": "Free-text notes"},
                                {"name": "custom", "type": "string", "help": "Custom field (key:value, repeatable)"},
                            ],
                        },
                        {
                            "name": "delete",
                            "description": "Delete a profile",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "profile-uuid", "repeatable": True},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── Letter ──────────────────────────────────────────────────────────
        {
            "name": "letter",
            "description": "Paper letter management",
            "children": [
                {
                    "name": "list",
                    "description": "List letters",
                    "flags": [
                        {"name": "direction", "type": "string", "help": "sent|received|all (default: all)"},
                        {"name": "limit", "short": "l", "type": "number", "help": "Max results (default 20)"},
                        {"name": "sort", "short": "s", "type": "string", "help": "Sort: newest (default), oldest, sender"},
                        {"name": "group", "short": "g", "type": "string", "help": "Group by: conversation (default none)"},
                        {"name": "tag", "type": "string", "help": "Filter by tag(s); comma-separated (AND semantics)"},
                    ],
                },
                {
                    "name": "draft",
                    "description": "List / recall saved letter drafts",
                    "params": [
                        {"name": "uuid", "required": False, "type": "uuid", "placeholder": "draft-uuid", "uuidSource": "letter.drafts"},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a received letter",
                    "interactive": True,
                    "params": [{"name": "object", "required": True, "type": "string"}],
                    "flags": [
                        {"name": "body", "short": "b", "type": "string", "help": "Path to letter file (.md/.html/.txt)"},
                        {"name": "body-text", "type": "string", "help": "Inline body text content"},
                        {"name": "body-format", "type": "string", "help": "Body format: markdown (default), html, text"},
                        {"name": "sender", "type": "string", "help": "Sender name/address (free text)"},
                        {"name": "recipient", "type": "string", "help": "Recipient name/address (free text)"},
                        {"name": "respond-to", "type": "uuid", "help": "UUID of letter this responds to", "uuidSource": "letter.list"},
                        {"name": "tag", "type": "string", "help": "Add tag(s); comma-separated"},
                    ],
                },
                {
                    "name": "send",
                    "description": "Send a new letter",
                    "interactive": True,
                    "params": [{"name": "recipient", "required": True, "type": "string"}],
                    "flags": [
                        {"name": "object", "type": "string", "help": "Letter subject/object"},
                        {"name": "body", "short": "b", "type": "string", "help": "Path to letter file (.md/.html/.txt)"},
                        {"name": "body-text", "type": "string", "help": "Inline body text content"},
                        {"name": "body-format", "type": "string", "help": "Body format: markdown (default), html, text"},
                        {"name": "sender", "type": "string", "help": "Sender name/address (free text)"},
                        {"name": "sender-profile", "type": "uuid", "help": "Your profile UUID from !user info", "uuidSource": "user.info.list"},
                        {"name": "recipient-contact", "type": "uuid", "help": "Contact UUID from !contact", "uuidSource": "contact.list"},
                        {"name": "respond-to", "type": "uuid", "help": "UUID of letter this responds to", "uuidSource": "letter.list"},
                        {"name": "tag", "type": "string", "help": "Add tag(s); comma-separated"},
                    ],
                },
                {
                    "name": "view",
                    "description": "View a letter",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "letter-uuid", "uuidSource": "letter.list"},
                    ],
                },
                {
                    "name": "pdf",
                    "description": "Export a letter as PDF",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "letter-uuid", "uuidSource": "letter.list"},
                    ],
                    "flags": [
                        {"name": "output", "short": "o", "type": "string", "help": "Output PDF file path"},
                    ],
                },
            ],
        },

        # ── Help ───────────────────────────────────────────────────────────
        {
            "name": "help",
            "description": "Show available commands",
        },
    ]


# ---------------------------------------------------------------------------
# Helper functions for form-required response resolution
# ---------------------------------------------------------------------------


def _find_command_depth(tokens: list[str]) -> int:
    """Walk the tree to find how many leading tokens form the command path."""
    tree = get_command_tree()
    current = tree
    for i, token in enumerate(tokens):
        found = None
        for node in current:
            if node["name"].lower() == token.lower():
                found = node
                break
        if found is None:
            return i
        children = found.get("children", [])
        if not children:
            return i + 1
        current = children
    return len(tokens)


def _get_param_names(tokens: list[str]) -> list[str]:
    """Get the param names for a leaf command node."""
    tree = get_command_tree()
    current = tree
    node = None
    for token in tokens:
        found = None
        for n in current:
            if n["name"].lower() == token.lower():
                found = n
                break
        if found is None:
            return []
        node = found
        children = node.get("children", [])
        if not children:
            break
        current = children
    if node is None:
        return []
    return [p["name"] for p in node.get("params", [])]

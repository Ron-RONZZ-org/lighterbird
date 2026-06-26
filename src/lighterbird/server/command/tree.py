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
repeatable (optional), uuidSource (optional)."""

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
                                {"name": "password", "type": "string", "help": "Account password"},
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
                                {"name": "password", "type": "string", "help": "New password"},
                                {"name": "imap_server", "type": "string", "help": "New IMAP server"},
                                {"name": "smtp_server", "type": "string", "help": "New SMTP server"},
                            ],
                        },
                        {
                            "name": "remove",
                            "description": "Remove email account(s)",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "account-uuid", "uuidSource": "email.listAccounts", "repeatable": True},
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
                            "name": "remove",
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
                                {"name": "password", "type": "string", "help": "New password"},
                            ],
                        },
                        {
                            "name": "remove",
                            "description": "Remove calendar(s)",
                            "params": [
                                {"name": "uuid", "required": True, "type": "uuid", "placeholder": "calendar-uuid", "uuidSource": "calendar.listCalendars", "repeatable": True},
                            ],
                        },
                    ],
                },
            ],
        },

        # ── Contacts ───────────────────────────────────────────────────────
        {
            "name": "contacts",
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
                    "params": [
                        {"name": "name", "required": True, "type": "string", "placeholder": "Full name"},
                    ],
                    "flags": [
                        {"name": "email", "type": "string", "help": "Email address"},
                        {"name": "phone", "type": "string", "help": "Phone number"},
                        {"name": "org", "type": "string", "help": "Organization"},
                        {"name": "notes", "type": "string", "help": "Notes"},
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
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "contact-uuid", "uuidSource": "contacts.list"},
                    ],
                    "flags": [
                        {"name": "name", "type": "string", "help": "New name"},
                        {"name": "email", "type": "string", "help": "New email"},
                        {"name": "phone", "type": "string", "help": "New phone"},
                        {"name": "org", "type": "string", "help": "New organization"},
                        {"name": "notes", "type": "string", "help": "New notes"},
                    ],
                },
                {
                    "name": "remove",
                    "description": "Remove contact(s)",
                    "params": [
                        {"name": "uuid", "required": True, "type": "uuid", "placeholder": "contact-uuid", "uuidSource": "contacts.list", "repeatable": True},
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
                    "description": "List all todos",
                    "flags": [
                        {"name": "status", "type": "string", "help": "Filter by status (pending|done)"},
                    ],
                },
                {
                    "name": "add",
                    "description": "Add a new todo",
                    "interactive": True,
                    "params": [
                        {"name": "title", "required": True, "type": "string"},
                    ],
                    "flags": [
                        {"name": "due", "type": "date", "help": "Due date (YYYY-MM-DD)"},
                        {"name": "priority", "type": "number", "help": "Priority (1-10)"},
                        {"name": "description", "type": "string", "help": "Description"},
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
                    ],
                },
                {
                    "name": "remove",
                    "description": "Remove todo(s)",
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
                    "name": "write",
                    "description": "Write a journal entry",
                    "interactive": True,
                    "params": [
                        {"name": "title", "required": True, "type": "string"},
                    ],
                    "flags": [
                        {"name": "date", "type": "date", "help": "Date (YYYY-MM-DD, default: today)"},
                        {"name": "text", "type": "string", "help": "Entry text"},
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
                                {"name": "schedule", "type": "string", "help": "manual|hourly|daily|weekly"},
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
                                {"name": "schedule", "type": "string", "help": "manual|hourly|daily|weekly"},
                                {"name": "max-copies", "type": "number", "help": "Max backups to keep"},
                                {"name": "target", "type": "string", "help": "local or absolute path"},
                                {"name": "enabled", "type": "string", "help": "true|false"},
                            ],
                        },
                        {
                            "name": "remove",
                            "description": "Remove a backup strategy",
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
            "description": "Synchronize data (email & calendar)",
            "flags": [
                {"name": "email", "type": "flag", "help": "Sync email only"},
                {"name": "calendar", "type": "flag", "help": "Sync calendar only"},
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
            "description": "User settings and saved commands",
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
                            "name": "remove",
                            "description": "Remove saved command(s)",
                            "params": [
                                {"name": "alias", "required": True, "type": "string", "placeholder": "alias", "repeatable": True},
                            ],
                        },
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

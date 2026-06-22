/** Command hierarchy — single source of truth for autocomplete.
 *
 * Each node has:
 *   name         — the token the user types
 *   description  — help text shown in autocomplete
 *   children     — sub-commands (non-leaf nodes)
 *   params       — positional arguments (leaf nodes)
 *   flags        — flag arguments (e.g. --calendar)
 *   interactive  — if true, opens an interactive form popup
 *   aliasFor     — if set, this is a backward-compat alias redirecting
 *                  to the canonical path (array of tokens)
 *
 * The frontend only uses the tree for autocomplete + help.
 * Command execution is handled by the backend via POST /api/v1/command.
 */

/** @typedef {{name:string, required:boolean, type:string, placeholder?:string, repeatable?:boolean, uuidSource?:string}} ParamDef */
/** @typedef {{name:string, short?:string, type:string, help?:string}} FlagDef */
/** @typedef {{name:string, description?:string, children?:CommandNode[], params?:ParamDef[], flags?:FlagDef[], interactive?:boolean, aliasFor?:string[]}} CommandNode */

/** @type {CommandNode[]} */
export const commandTree = [
  // ── Email ────────────────────────────────────────────────────────────
  {
    name: "email",
    description: "Email operations",
    children: [
      {
        name: "list",
        description: "Show inbox messages",
        params: [],
        flags: [
          { name: "limit", short: "l", type: "number", help: "Max messages (default 20)" },
        ],
      },
      {
        name: "read",
        description: "Read a message by UUID",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "message-uuid", uuidSource: "email.listMessages" },
        ],
      },
      {
        name: "send",
        description: "Send an email",
        interactive: true,
        params: [
          { name: "to", required: true, type: "string", placeholder: "recipient@example.com" },
          { name: "subject", required: true, type: "string" },
          { name: "body", required: false, type: "string" },
        ],
        flags: [
          { name: "account", short: "a", type: "uuid", help: "Account UUID (default: first)", uuidSource: "email.listAccounts" },
          { name: "cc", type: "string", help: "CC recipient" },
        ],
      },
      {
        name: "search",
        description: "Search messages",
        flags: [
          { name: "from", type: "string", help: "Sender email" },
          { name: "subject", type: "string", help: "Subject text" },
          { name: "body", type: "string", help: "Body text" },
          { name: "after", type: "date", help: "Start date (YYYY-MM-DD)" },
          { name: "before", type: "date", help: "End date (YYYY-MM-DD)" },
          { name: "limit", short: "l", type: "number", help: "Max results" },
        ],
      },
      {
        name: "sync",
        description: "Fetch new email",
        params: [
          { name: "uuid", required: false, type: "uuid", placeholder: "account-uuid (optional)", uuidSource: "email.listAccounts" },
        ],
      },
      {
        name: "trash",
        description: "Move message to trash",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "message-uuid", uuidSource: "email.listMessages" },
        ],
      },
      {
        name: "archive",
        description: "Archive a message",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "message-uuid", uuidSource: "email.listMessages" },
        ],
      },
      {
        name: "account",
        description: "Manage email accounts",
        children: [
          {
            name: "add",
            description: "Add a new email account",
            params: [
              { name: "email", required: true, type: "string", placeholder: "user@example.com" },
              { name: "imap_server", required: false, type: "string", placeholder: "imap.example.com" },
              { name: "smtp_server", required: false, type: "string", placeholder: "smtp.example.com" },
              { name: "password", required: false, type: "string", placeholder: "(prompt)" },
            ],
            flags: [
              { name: "name", type: "string", help: "Display name" },
            ],
          },
          {
            name: "list",
            description: "List email accounts",
          },
          {
            name: "modify",
            description: "Modify an account",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "account-uuid", uuidSource: "email.listAccounts" },
            ],
            flags: [
              { name: "name", type: "string", help: "New display name" },
              { name: "password", type: "string", help: "New password" },
              { name: "imap_server", type: "string", help: "New IMAP server" },
              { name: "smtp_server", type: "string", help: "New SMTP server" },
            ],
          },
          {
            name: "remove",
            description: "Remove email account(s)",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "account-uuid", uuidSource: "email.listAccounts", repeatable: true },
            ],
          },
        ],
      },
    ],
  },

  // ── Calendar ─────────────────────────────────────────────────────────
  {
    name: "calendar",
    description: "Calendar operations",
    children: [
      {
        name: "list",
        description: "List calendar events",
        params: [
          { name: "start", required: false, type: "date", placeholder: "2000-01-01" },
          { name: "end", required: false, type: "date", placeholder: "2099-12-31" },
        ],
        flags: [
          { name: "calendar", short: "c", type: "uuid", help: "Filter by calendar UUID", uuidSource: "calendar.listCalendars" },
          { name: "query", short: "q", type: "string", help: "Search text" },
        ],
      },
      {
        name: "event",
        description: "Manage calendar events",
        children: [
          {
            name: "add",
            description: "Create a new event",
            interactive: true,
            params: [
              { name: "calendar-uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars" },
              { name: "title", required: true, type: "string" },
              { name: "start", required: true, type: "datetime", placeholder: "2024-06-15T09:00:00Z" },
              { name: "end", required: true, type: "datetime", placeholder: "2024-06-15T10:00:00Z" },
              { name: "location", required: false, type: "string" },
            ],
          },
          {
            name: "view",
            description: "View event details",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "event-uuid", uuidSource: "calendar.listEvents" },
            ],
          },
          {
            name: "modify",
            description: "Modify an event",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "event-uuid", uuidSource: "calendar.listEvents" },
            ],
            flags: [
              { name: "title", type: "string", help: "New title" },
              { name: "start", type: "string", help: "New start (ISO)" },
              { name: "end", type: "string", help: "New end (ISO)" },
              { name: "location", type: "string", help: "New location" },
              { name: "description", type: "string", help: "New description" },
            ],
          },
          {
            name: "remove",
            description: "Delete event(s)",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "event-uuid", uuidSource: "calendar.listEvents", repeatable: true },
            ],
          },
          {
            name: "search",
            description: "Search events",
            flags: [
              { name: "query", short: "q", type: "string", help: "Search text" },
              { name: "start", type: "date", help: "Start date (YYYY-MM-DD)" },
              { name: "end", type: "date", help: "End date (YYYY-MM-DD)" },
              { name: "calendar", short: "c", type: "uuid", help: "Calendar UUID filter", uuidSource: "calendar.listCalendars" },
            ],
          },
        ],
      },
      {
        name: "account",
        description: "Manage calendar accounts",
        children: [
          {
            name: "add",
            description: "Add a CalDAV calendar",
            params: [
              { name: "url", required: true, type: "string", placeholder: "https://..." },
            ],
            flags: [
              { name: "username", type: "string", help: "CalDAV username" },
              { name: "password", type: "string", help: "CalDAV password" },
            ],
          },
          {
            name: "list",
            description: "List calendars",
          },
          {
            name: "modify",
            description: "Modify a calendar",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars" },
            ],
            flags: [
              { name: "url", type: "string", help: "New URL" },
              { name: "username", type: "string", help: "New username" },
              { name: "password", type: "string", help: "New password" },
            ],
          },
          {
            name: "remove",
            description: "Remove calendar(s)",
            params: [
              { name: "uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars", repeatable: true },
            ],
          },
        ],
      },
      {
        name: "sync",
        description: "Sync calendar(s) by UUID",
        params: [
          { name: "uuid", required: false, type: "uuid", placeholder: "calendar-uuid (optional)", uuidSource: "calendar.listCalendars" },
        ],
      },
    ],
  },

  // ── Contacts ─────────────────────────────────────────────────────────
  {
    name: "contacts",
    description: "Contact management",
    children: [
      {
        name: "list",
        description: "List contacts",
        flags: [
          { name: "limit", short: "l", type: "number", help: "Max results (default 50)" },
        ],
      },
      {
        name: "add",
        description: "Add a contact",
        params: [
          { name: "email", required: true, type: "string", placeholder: "email@example.com" },
          { name: "name", required: false, type: "string", placeholder: "Full name" },
          { name: "phone", required: false, type: "string", placeholder: "Phone number" },
        ],
      },
      {
        name: "view",
        description: "View contact details",
        params: [
          { name: "uuid-or-email", required: true, type: "string", placeholder: "uuid or email" },
        ],
      },
      {
        name: "modify",
        description: "Modify a contact",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "contact-uuid", uuidSource: "contacts.list" },
        ],
        flags: [
          { name: "name", type: "string", help: "New name" },
          { name: "email", type: "string", help: "New email" },
          { name: "phone", type: "string", help: "New phone" },
          { name: "org", type: "string", help: "New organization" },
          { name: "notes", type: "string", help: "New notes" },
        ],
      },
      {
        name: "remove",
        description: "Remove contact(s)",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "contact-uuid", uuidSource: "contacts.list", repeatable: true },
        ],
      },
      {
        name: "search",
        description: "Search contacts",
        params: [
          { name: "query", required: false, type: "string", placeholder: "search text" },
        ],
      },
    ],
  },

  // ── Todo ─────────────────────────────────────────────────────────────
  {
    name: "todo",
    description: "Task management",
    children: [
      {
        name: "list",
        description: "List all todos",
        flags: [
          { name: "status", type: "string", help: "Filter by status (pending|done)" },
        ],
      },
      {
        name: "add",
        description: "Add a new todo",
        params: [
          { name: "title", required: true, type: "string" },
        ],
        flags: [
          { name: "due", type: "date", help: "Due date (YYYY-MM-DD)" },
          { name: "priority", type: "number", help: "Priority (1-10)" },
          { name: "description", type: "string", help: "Description" },
        ],
      },
      {
        name: "view",
        description: "View todo details",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "todo-uuid", uuidSource: "todo.list" },
        ],
      },
      {
        name: "done",
        description: "Mark todo as done",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "todo-uuid", uuidSource: "todo.list", repeatable: true },
        ],
      },
      {
        name: "modify",
        description: "Modify a todo",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "todo-uuid", uuidSource: "todo.list" },
        ],
        flags: [
          { name: "title", type: "string", help: "New title" },
          { name: "description", type: "string", help: "New description" },
          { name: "priority", type: "number", help: "New priority (1-10)" },
          { name: "due", type: "date", help: "New due date" },
          { name: "status", type: "string", help: "New status (pending|done)" },
        ],
      },
      {
        name: "remove",
        description: "Remove todo(s)",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "todo-uuid", uuidSource: "todo.list", repeatable: true },
        ],
      },
      {
        name: "search",
        description: "Search todos",
        params: [
          { name: "query", required: false, type: "string", placeholder: "search text" },
        ],
        flags: [
          { name: "status", type: "string", help: "Filter by status" },
        ],
      },
    ],
  },

  // ── Journal ──────────────────────────────────────────────────────────
  {
    name: "journal",
    description: "Journal entries",
    children: [
      {
        name: "list",
        description: "List journal entries",
        flags: [
          { name: "date", type: "date", help: "Filter by date (YYYY-MM-DD)" },
          { name: "limit", short: "l", type: "number", help: "Max results" },
        ],
      },
      {
        name: "write",
        description: "Write a journal entry",
        params: [
          { name: "title", required: true, type: "string" },
        ],
        flags: [
          { name: "date", type: "date", help: "Date (YYYY-MM-DD, default: today)" },
          { name: "text", type: "string", help: "Entry text" },
        ],
      },
      {
        name: "view",
        description: "View a journal entry",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "entry-uuid", uuidSource: "journal.list" },
        ],
      },
      {
        name: "search",
        description: "Search journal entries",
        params: [
          { name: "query", required: false, type: "string", placeholder: "search text" },
        ],
      },
    ],
  },

  // ── Sync ─────────────────────────────────────────────────────────────
  {
    name: "sync",
    description: "Synchronize all data (email & calendar)",
    flags: [
      { name: "email", type: "flag", help: "Sync email only" },
      { name: "calendar", type: "flag", help: "Sync calendar only" },
    ],
  },

  // ── Help ─────────────────────────────────────────────────────────────
  {
    name: "help",
    description: "Show available commands",
  },

  // ── Backward-compat aliases ──────────────────────────────────────────
  {
    name: "inbox",
    description: "Show inbox (alias for !email list)",
    aliasFor: ["email", "list"],
  },
  {
    name: "new",
    description: "Fetch new email (alias for !email sync)",
    aliasFor: ["email", "sync"],
  },
  {
    name: "read",
    description: "Read message (alias for !email read)",
    aliasFor: ["email", "read"],
    params: [
      { name: "uuid", required: true, type: "uuid", placeholder: "message-uuid", uuidSource: "email.listMessages" },
    ],
  },
  {
    name: "send",
    description: "Send email (alias for !email send)",
    aliasFor: ["email", "send"],
    interactive: true,
    params: [
      { name: "to", required: true, type: "string", placeholder: "recipient@example.com" },
      { name: "subject", required: true, type: "string" },
      { name: "body", required: true, type: "string" },
    ],
  },
  {
    name: "search",
    description: "Search messages (alias for !email search)",
    aliasFor: ["email", "search"],
    flags: [
      { name: "from", type: "string", help: "Sender email" },
      { name: "subject", type: "string", help: "Subject text" },
      { name: "body", type: "string", help: "Body text" },
      { name: "after", type: "date", help: "Start date" },
      { name: "before", type: "date", help: "End date" },
      { name: "limit", short: "l", type: "number", help: "Max results" },
    ],
  },
  {
    name: "addevent",
    description: "Create event (alias for !calendar event add)",
    aliasFor: ["calendar", "event", "add"],
    interactive: true,
    params: [
      { name: "calendar-uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars" },
      { name: "title", required: true, type: "string" },
      { name: "start", required: true, type: "datetime", placeholder: "2024-06-15T09:00:00" },
      { name: "end", required: true, type: "datetime", placeholder: "2024-06-15T10:00:00" },
      { name: "location", required: false, type: "string" },
    ],
  },
  {
    name: "events",
    description: "List events (alias for !calendar list)",
    aliasFor: ["calendar", "list"],
    params: [
      { name: "start", required: false, type: "date", placeholder: "2000-01-01" },
      { name: "end", required: false, type: "date", placeholder: "2099-12-31" },
    ],
    flags: [
      { name: "calendar", short: "c", type: "uuid", help: "Filter by calendar UUID", uuidSource: "calendar.listCalendars" },
      { name: "query", short: "q", type: "string", help: "Search text" },
    ],
  },
  {
    name: "account",
    description: "Manage accounts (alias for !email account ...)",
    children: [
      {
        name: "add",
        description: "Add account (alias for !email account add)",
        aliasFor: ["email", "account", "add"],
        params: [
          { name: "email", required: true, type: "string", placeholder: "user@example.com" },
          { name: "imap_server", required: false, type: "string", placeholder: "imap.example.com" },
          { name: "smtp_server", required: false, type: "string", placeholder: "smtp.example.com" },
          { name: "password", required: false, type: "string" },
        ],
      },
      {
        name: "list",
        description: "List accounts (alias for !email account list)",
        aliasFor: ["email", "account", "list"],
      },
      {
        name: "remove",
        description: "Remove accounts (alias for !email account remove)",
        aliasFor: ["email", "account", "remove"],
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "account-uuid", uuidSource: "email.listAccounts", repeatable: true },
        ],
      },
    ],
  },
];

/** Build a flat list of all root-level command names (for initial ! completion). */
export function getRootNames() {
  return commandTree.map((n) => n.name);
}

/** Find the deepest node matching a path of tokens (case-insensitive).
 *
 * Stops at leaf nodes — remaining tokens are parameter values.
 * If the matched node has `aliasFor`, the effective path changes.
 * Returns `null` if zero tokens match.
 */
export function findNode(tokens) {
  let current = commandTree;
  let node = null;
  for (const token of tokens) {
    const matched = current.find(
      (n) => n.name.toLowerCase() === token.toLowerCase(),
    );
    if (!matched) return node;
    node = matched;

    // If node is an alias, use the canonical path for further resolution
    if (node.aliasFor) {
      // We stop here — the alias redirect is handled at dispatch time
      return node;
    }

    // Stop at leaf (no children) — remaining tokens are parameter values
    if (!node.children || node.children.length === 0) return node;
    current = node.children;
  }
  return node;
}

/** Check if a node is an alias for another command. */
export function isAlias(node) {
  return node && Array.isArray(node.aliasFor) && node.aliasFor.length > 0;
}

/** Resolve an alias node to its canonical path tokens. */
export function resolveAlias(node) {
  return node.aliasFor || [];
}

/** Get all children that match a prefix (case-insensitive). */
export function matchChildren(nodes, prefix) {
  const p = prefix.toLowerCase();
  return nodes.filter((n) => n.name.toLowerCase().startsWith(p));
}

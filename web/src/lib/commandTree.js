/** Command hierarchy — single source of truth for autocomplete and execution.
 *
 * Each node has:
 *   name         — the token the user types
 *   description  — help text
 *   children     — sub-commands (non-leaf nodes)
 *   params       — positional arguments (leaf nodes)
 *   flags        — flag arguments (e.g. --calendar)
 *   apiMethod    — "email.listAccounts" maps to api.email.listAccounts()
 *   responseType — hint for popup rendering ("status"|"email"|"events"|"help"|"form")
 */

/** @typedef {{name:string, required:boolean, type:string, placeholder?:string, repeatable?:boolean, uuidSource?:string}} ParamDef */
/** @typedef {{name:string, short?:string, type:string, help?:string}} FlagDef */
/** @typedef {{name:string, description?:string, children?:CommandNode[], params?:ParamDef[], flags?:FlagDef[], apiMethod?:string, responseType?:string}} CommandNode */

/** @type {CommandNode[]} */
export const commandTree = [
  // ── Account ──────────────────────────────────────────────────────────
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
        apiMethod: "email.createAccount",
        responseType: "status",
      },
      {
        name: "list",
        description: "List email accounts",
        apiMethod: "email.listAccounts",
        responseType: "status",
      },
      {
        name: "remove",
        description: "Remove email account(s)",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "account-uuid", uuidSource: "email.listAccounts", repeatable: true },
        ],
        apiMethod: "email.deleteAccount",
        responseType: "status",
      },
    ],
  },

  // ── Calendar ─────────────────────────────────────────────────────────
  {
    name: "calendar",
    description: "Manage calendars",
    children: [
      {
        name: "add",
        description: "Add a CalDAV calendar",
        params: [
          { name: "url", required: true, type: "string", placeholder: "https://..." },
          { name: "username", required: false, type: "string" },
          { name: "password", required: false, type: "string" },
        ],
        apiMethod: "calendar.createCalendar",
        responseType: "status",
      },
      {
        name: "list",
        description: "List calendars",
        apiMethod: "calendar.listCalendars",
        responseType: "status",
      },
      {
        name: "sync",
        description: "Sync calendar(s) by UUID",
        params: [
          { name: "uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars", repeatable: true },
        ],
        apiMethod: "calendar.sync",
        responseType: "status",
      },
    ],
  },

  // ── Add Event ────────────────────────────────────────────────────────
  {
    name: "addevent",
    description: "Create a new calendar event",
    params: [
      { name: "calendar-uuid", required: true, type: "uuid", placeholder: "calendar-uuid", uuidSource: "calendar.listCalendars" },
      { name: "title", required: true, type: "string" },
      { name: "start", required: true, type: "datetime", placeholder: "2024-06-15T09:00:00Z" },
      { name: "end", required: true, type: "datetime", placeholder: "2024-06-15T10:00:00Z" },
      { name: "location", required: false, type: "string" },
    ],
    apiMethod: "calendar.createEvent",
    responseType: "status",
  },

  // ── Events (list) ────────────────────────────────────────────────────
  {
    name: "events",
    description: "List calendar events",
    params: [
      { name: "start", required: false, type: "date", placeholder: "2000-01-01" },
      { name: "end", required: false, type: "date", placeholder: "2099-12-31" },
    ],
    flags: [
      { name: "calendar", short: "c", type: "uuid", help: "Filter by calendar UUID" },
      { name: "query", short: "q", type: "string", help: "Search text" },
    ],
    apiMethod: "calendar.listEvents",
    responseType: "events",
  },

  // ── Help ─────────────────────────────────────────────────────────────
  {
    name: "help",
    description: "Show available commands",
    apiMethod: "builtin.help",
    responseType: "help",
  },

  // ── Inbox ────────────────────────────────────────────────────────────
  {
    name: "inbox",
    description: "Show inbox messages",
    flags: [
      { name: "limit", short: "l", type: "number", help: "Max messages (default 20)" },
    ],
    apiMethod: "email.listMessages",
    responseType: "status",
  },

  // ── New ──────────────────────────────────────────────────────────────
  {
    name: "new",
    description: "Fetch new email",
    apiMethod: "email.sync",
    responseType: "status",
  },

  // ── Read ─────────────────────────────────────────────────────────────
  {
    name: "read",
    description: "Read a message by UUID",
    params: [
      { name: "uuid", required: true, type: "uuid", placeholder: "message-uuid", uuidSource: "email.listMessages" },
    ],
    apiMethod: "email.getMessage",
    responseType: "email",
  },

  // ── Search ───────────────────────────────────────────────────────────
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
    apiMethod: "email.listMessages",
    responseType: "status",
  },

  // ── Send ─────────────────────────────────────────────────────────────
  {
    name: "send",
    description: "Send an email",
    params: [
      { name: "to", required: true, type: "string", placeholder: "recipient@example.com" },
      { name: "subject", required: true, type: "string" },
      { name: "body", required: true, type: "string" },
    ],
    apiMethod: "email.send",
    responseType: "status",
  },

  // ── Sync ─────────────────────────────────────────────────────────────
  {
    name: "sync",
    description: "Synchronize data",
    children: [
      {
        name: "all",
        description: "Sync all accounts and calendars",
        apiMethod: "admin.syncAll",
        responseType: "status",
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
 * Stops at leaf nodes (those with an ``apiMethod``) — remaining tokens
 * are parameter values, not sub-commands. Returns ``null`` if zero tokens
 * match (no root node found).
 */
export function findNode(tokens) {
  let current = commandTree;
  let node = null;
  for (const token of tokens) {
    const matched = current.find(
      (n) => n.name.toLowerCase() === token.toLowerCase(),
    );
    if (!matched) return node; // Return deepest match so far (may be null)
    node = matched;
    // Stop at leaf — remaining tokens are parameter values
    if (node.apiMethod) return node;
    current = matched.children || [];
  }
  return node;
}

/** Get all children that match a prefix (case-insensitive). */
export function matchChildren(nodes, prefix) {
  const p = prefix.toLowerCase();
  return nodes.filter((n) => n.name.toLowerCase().startsWith(p));
}

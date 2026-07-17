/**
 * Shared persistent type resolution — single source of truth for
 * mapping commands to persistent tab types and list id keys.
 *
 * Imported by App.svelte, HomeTab.svelte, and commandRouter.js
 * to prevent the same mapping logic from drifting across files.
 *
 * The authoritative command metadata lives in the backend
 * (``server/command/tree.py`` / ``registry.py``). This module is a
 * frontend convenience — when adding a new interactive command,
 * add entries here AND in the backend ``_INTERACTIVE_FORMS`` dict.
 */

// ── Persistent type map (command pattern → dataType) ───────────────
// Ordered list of [regex, dataType]. First match wins.
const PERSISTENT_ENTRIES = [
  [/^!(email\s+)?account\s+list\s*$/i, "accounts"],
  [/^!(calendar\s+)?account\s+list\s*$/i, "calendars"],
  [/^!contacts?\s+(list|search)\b/i, "contacts-list"],
  [/^!todo\s+(list|search|tree)\b/i, "todo-list"],
  [/^!journal\s+(list|search)\b/i, "journal-list"],
  [/^!calendar\s+(list|search)\b/i, "calendar-events"],
  [/^!email\s+list\s+trash\b/i, "email-trash-list"],
  [/^!email\s+list\s+draft\b/i, "email-draft-list"],
  [/^!email\s+draft\s+list\b/i, "email-draft-list"],
  [/^!email\s+(list|search)\b/i, "email-list"],
  [/^!email\s+folder\s+list\s*$/i, "folder-list"],
  [/^!email\s+folders\s*$/i, "folder-list"],
  [/^!email\s+signature\s+list\s*$/i, "signature-list"],
  [/^!user\s+saved-commands\s+list\s*$/i, "saved-commands"],
  [/^!user\s+info\s+list\s*$/i, "user-info-list"],
  [/^!email\s+sieve\s+list\s*$/i, "sieve-list"],
  [/^!letter\s+(list|search)\b/i, "letter-list"],
];

// ── Token-path → dataType map (used by resolveListIdKey) ──────────
const TOKEN_TYPE_MAP = {
  "email account list": "accounts",
  "calendar account list": "calendars",
  "contact list": "contacts-list",
  "todo list": "todo-list",
  "journal list": "journal-list",
  "calendar list": "calendar-events",
  "email list": "email-list",
  "email list trash": "email-trash-list",
  "email list draft": "email-draft-list",
  "email draft list": "email-draft-list",
  "user saved-commands list": "saved-commands",
  "user info list": "user-info-list",
  "email sieve list": "sieve-list",
  "email signature list": "signature-list",
  "email folder list": "folder-list",
  "letter list": "letter-list",
};

/**
 * Detect the persistent tab type from a raw command input string.
 * @param {string} input — e.g. "!email list" or "!todo search inbox"
 * @returns {string|null} — e.g. "email-list" or null
 */
export function detectPersistentType(input) {
  const t = input.trim();
  for (const [pattern, type] of PERSISTENT_ENTRIES) {
    if (pattern.test(t)) return type;
  }
  return null;
}

/**
 * Resolve the persistent idKey from a list command token array.
 * @param {string[]} listTokens — e.g. ["email", "list"]
 * @returns {string|null} — e.g. "email-list" or null
 */
export function resolveListIdKey(listTokens) {
  const path = listTokens.join(" ");
  return TOKEN_TYPE_MAP[path] || null;
}

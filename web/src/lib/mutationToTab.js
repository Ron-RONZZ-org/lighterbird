/**
 * Mutation-to-list-tab mapping for post-mutation navigation.
 *
 * After a !command mutation (add/modify/delete) succeeds, the frontend
 * redirects to the corresponding list tab with a brief highlight on the
 * affected entry. This module provides the mapping from mutation token
 * paths to list tab metadata.
 *
 * ## Usage
 *
 *   import { isMutationCommand, extractHighlightUuid } from "./mutationToTab.js";
 *
 *   // After a command succeeds:
 *   const { tokens } = parseCommand(input);
 *   const cfg = isMutationCommand(tokens);
 *   if (cfg) {
 *     const highlight = extractHighlightUuid(result, cfg.isDelete);
 *     // cfg.listTokens, cfg.listIdKey — navigate to list tab
 *   }
 */

import { journal as journalApi, todo as todoApi, contacts as contactsApi,
         calendar as calendarApi, letters as lettersApi, email as emailApi } from "./api.js";

// ── Token-path → list metadata ──────────────────────────────────────
//
// Key: joined tokens of the mutation action verb and its domain prefix.
// Value: { listTokens, listIdKey, type, isDelete, title }
//
// Matching: longest-prefix match on the action tokens (["todo","add"]
// matches key "todo add"; ["calendar","event","modify"] matches
// "calendar event modify").
//
// When adding a new domain, add an entry here AND in FormTab.svelte's
// command-path inference map AND in commandRouter.js (resolveAddFormType).

const MUTATION_MAP = {
  // ── Todo ─────────────────────────────────────────────────────────
  "todo add": {
    listTokens: ["todo", "list"],
    listIdKey: "todo-list",
    type: "todo-list",
    isDelete: false,
    title: "Todos",
  },
  "todo modify": {
    listTokens: ["todo", "list"],
    listIdKey: "todo-list",
    type: "todo-list",
    isDelete: false,
    title: "Todos",
  },
  "todo delete": {
    listTokens: ["todo", "list"],
    listIdKey: "todo-list",
    type: "todo-list",
    isDelete: true,
    title: "Todos",
  },

  // ── Contact ──────────────────────────────────────────────────────
  "contact add": {
    listTokens: ["contact", "list"],
    listIdKey: "contacts-list",
    type: "contacts-list",
    isDelete: false,
    title: "Contacts",
  },
  "contact modify": {
    listTokens: ["contact", "list"],
    listIdKey: "contacts-list",
    type: "contacts-list",
    isDelete: false,
    title: "Contacts",
  },
  "contact delete": {
    listTokens: ["contact", "list"],
    listIdKey: "contacts-list",
    type: "contacts-list",
    isDelete: true,
    title: "Contacts",
  },

  // ── Journal ──────────────────────────────────────────────────────
  "journal write": {
    listTokens: ["journal", "list"],
    listIdKey: "journal-list",
    type: "journal-list",
    isDelete: false,
    title: "Journal",
  },
  "journal delete": {
    listTokens: ["journal", "list"],
    listIdKey: "journal-list",
    type: "journal-list",
    isDelete: true,
    title: "Journal",
  },

  // ── Calendar events ──────────────────────────────────────────────
  "calendar event add": {
    listTokens: ["calendar", "list"],
    listIdKey: "calendar-events",
    type: "calendar-events",
    isDelete: false,
    title: "Calendar Events",
  },
  "calendar event modify": {
    listTokens: ["calendar", "list"],
    listIdKey: "calendar-events",
    type: "calendar-events",
    isDelete: false,
    title: "Calendar Events",
  },
  "calendar event delete": {
    listTokens: ["calendar", "list"],
    listIdKey: "calendar-events",
    type: "calendar-events",
    isDelete: true,
    title: "Calendar Events",
  },

  // ── Email ────────────────────────────────────────────────────────
  "email send": {
    listTokens: ["email", "list"],
    listIdKey: "email-list",
    type: "email-list",
    isDelete: false,
    title: "Inbox",
  },
  "email trash": {
    listTokens: ["email", "list"],
    listIdKey: "email-list",
    type: "email-list",
    isDelete: true,
    title: "Inbox",
  },
  "email archive": {
    listTokens: ["email", "list"],
    listIdKey: "email-list",
    type: "email-list",
    isDelete: true,
    title: "Inbox",
  },

  // ── Sieve scripts ────────────────────────────────────────────────
  "email sieve add": {
    listTokens: ["email", "sieve", "list"],
    listIdKey: "sieve-list",
    type: "sieve-list",
    isDelete: false,
    title: "Sieve Scripts",
  },
  "email sieve modify": {
    listTokens: ["email", "sieve", "list"],
    listIdKey: "sieve-list",
    type: "sieve-list",
    isDelete: false,
    title: "Sieve Scripts",
  },
  "email sieve delete": {
    listTokens: ["email", "sieve", "list"],
    listIdKey: "sieve-list",
    type: "sieve-list",
    isDelete: true,
    title: "Sieve Scripts",
  },

  // ── Letters ──────────────────────────────────────────────────────
  "letter add": {
    listTokens: ["letter", "list"],
    listIdKey: "letter-list",
    type: "letter-list",
    isDelete: false,
    title: "Letters",
  },
  "letter send": {
    listTokens: ["letter", "list"],
    listIdKey: "letter-list",
    type: "letter-list",
    isDelete: false,
    title: "Letters",
  },
  "letter delete": {
    listTokens: ["letter", "list"],
    listIdKey: "letter-list",
    type: "letter-list",
    isDelete: true,
    title: "Letters",
  },
};

/**
 * Look up mutation config for a token array.
 * Tries longest match first (e.g. "calendar event modify" before "calendar").
 *
 * @param {string[]} tokens — command tokens (e.g. ["todo", "add"])
 * @returns {object|null} — mutation config or null if not a mutation
 */
export function isMutationCommand(tokens) {
  if (!tokens || tokens.length === 0) return null;
  // Try full length first, then decreasing
  for (let len = tokens.length; len >= 1; len--) {
    const path = tokens.slice(0, len).join(" ");
    if (MUTATION_MAP[path]) return MUTATION_MAP[path];
  }
  return null;
}

/**
 * Extract the UUID to highlight from a mutation result.
 * Returns null for deletes (the entry is gone) or when no uuid is present.
 *
 * @param {object} result — the command execution result
 * @param {boolean} isDelete — whether the command was a delete
 * @returns {string|null} — uuid to highlight, or null
 */
export function extractHighlightUuid(result, isDelete) {
  if (isDelete) return null;
  // Most mutations return data.uuid
  if (result.data?.uuid) return result.data.uuid;
  return null;
}

/**
 * List tab data refreshers — keyed by persistent idKey.
 *
 * Each function accepts an optional highlight UUID and fetches fresh
 * list data with that highlight injected.
 *
 * Extracted from FormTab.svelte for sharing with the direct-execution
 * path in App.svelte.
 */
export const LIST_REFRESHERS = {
  "persistent-journal-list":         (highlight) => journalApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
  "persistent-todo-list":            (highlight) => todoApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
  "persistent-contacts-list":        (highlight) => contactsApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
  "persistent-calendar-events":      (highlight) => calendarApi.listEvents({ limit: 50 }).then(r => ({ ...r, highlight })),
  "persistent-letter-list":          (highlight) => lettersApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
  "persistent-email-list":           (highlight) => emailApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
};

/**
 * Get the persistent idKey for a listIdKey configured in MUTATION_MAP.
 *
 * @param {string} listIdKey — e.g. "todo-list", "contacts-list"
 * @returns {string} — e.g. "persistent-todo-list", "persistent-contacts-list"
 */
export function persistentIdKey(listIdKey) {
  return `persistent-${listIdKey}`;
}

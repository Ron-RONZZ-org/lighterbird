/**
 * Command router — intercepts add/write commands with missing required params
 * and routes to the appropriate list tab with an interactive add dialog.
 *
 * The interception is purely a frontend UX enhancement. If the router is unsure
 * (tree not loaded, unknown command), it returns { intercept: false } and the
 * command is sent to the backend as normal.
 */

import { parseCommand, hasTrailingSpace } from "./parser.js";
import { findNode, commandTree } from "./commandTree.js";

/**
 * Determine whether a !command should be intercepted and routed to a list+form.
 *
 * @param {string} input — raw user input (e.g. "!email account add")
 * @returns {{
 *   intercept: boolean,
 *   listTokens?: string[],         // tokens for the list command, e.g. ["email","account","list"]
 *   listIdKey?: string,            // persistent idKey for the list tab
 *   addFormType?: string,          // "email" | "calendar" | "contacts" | "todo" | "journal-write" | ...
 *   addTitle?: string,             // tab title for the add form
 *   initialData?: object,          // pre-filled form fields from typed args
 * }}
 */
export function shouldIntercept(input) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("!")) return { intercept: false };

  const { tokens, flags, partial } = parseCommand(trimmed);
  const trailing = hasTrailingSpace(trimmed);

  // Reconstruct effective tokens from the parse
  let effectiveTokens = tokens;
  if (trailing && partial) {
    effectiveTokens = [...tokens, partial];
  } else if (!trailing && partial) {
    // Check if tokens+partial resolves to a deeper node
    const nodeWithPartial = findNode([...tokens, partial]);
    if (nodeWithPartial) {
      effectiveTokens = [...tokens, partial];
    }
  }

  if (effectiveTokens.length === 0) return { intercept: false };

  const node = findNode(effectiveTokens);
  if (!node) return { intercept: false };

  const leafName = effectiveTokens[effectiveTokens.length - 1];

  // ── Determine if this command should be intercepted ──────────────
  const isAddOrWrite = leafName === "add" || leafName === "write";
  const isInteractive = node.interactive === true;

  // Only intercept "add"/"write" commands (including interactive ones)
  if (!isAddOrWrite && !isInteractive) return { intercept: false };

  // ── Check for missing required params ────────────────────────────
  const cmdTokenCount = countCommandTokens(effectiveTokens);
  const consumed = effectiveTokens.length - cmdTokenCount;

  const missingRequired = node.params?.some(
    (p, i) => p.required && i >= consumed,
  );

  // Only intercept if required params are missing
  if (!missingRequired) return { intercept: false };

  // ── Resolve the list command for this add command ─────────────────
  const listTokens = resolveListCommand(node, effectiveTokens);
  if (!listTokens) return { intercept: false };  // no known list → fall through

  // ── Resolve the persistent idKey ─────────────────────────────────
  const listIdKey = resolveListIdKey(listTokens);

  // ── Build initial data from typed args ───────────────────────────
  const paramTokens = effectiveTokens.slice(cmdTokenCount);
  const initialData = buildInitialData(node, leafName, paramTokens, flags);

  // ── Resolve the add form type for StatusPopup ────────────────────
  const addFormType = resolveAddFormType(effectiveTokens, leafName);
  const addTitle = resolveAddTitle(addFormType);

  return {
    intercept: true,
    listTokens,
    listIdKey,
    addFormType,
    addTitle,
    initialData,
  };
}

/**
 * Count how many leading tokens are command path tokens (not param values).
 * Walks the command tree level by level.
 */
function countCommandTokens(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find(
      (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
    );
    if (!found) return i;
    if (!found.children || found.children.length === 0) return i + 1;
    current = found.children || [];
  }
  return tokens.length;
}

/**
 * Resolve the list command for a given node + tokens.
 * Priority: explicit listCommand > convention (add→list, write→list).
 *
 * @param {object} node — the resolved command node
 * @param {string[]} tokens — full effective tokens
 * @returns {string[]|null} — token path for the list command, or null
 */
function resolveListCommand(node, tokens) {
  // 1. Explicit listCommand on the node
  if (node.listCommand && Array.isArray(node.listCommand)) {
    return node.listCommand;
  }

  // 2. Convention: replace last token "add"/"write" with "list"
  const leafName = tokens[tokens.length - 1];
  if (leafName === "add" || leafName === "write") {
    const listTokens = tokens.slice(0, -1);
    listTokens.push("list");
    // Verify the resolved list node exists
    const listNode = findNode(listTokens);
    if (listNode) return listTokens;
  }

  return null;
}

/**
 * Resolve the persistent idKey for a list command path.
 * Matches the patterns in HomeTab/App detectPersistentType.
 */
function resolveListIdKey(listTokens) {
  const path = listTokens.join(" ");
  if (/^email(\s+account)?\s+list$/i.test(path)) return "accounts";
  if (/^calendar(\s+account)?\s+list$/i.test(path)) return "calendars";
  if (/^contacts\s+list$/i.test(path)) return "contacts";
  if (/^todo\s+list$/i.test(path)) return "todos";
  if (/^journal\s+list$/i.test(path)) return "journal-list";
  if (/^email\s+list$/i.test(path)) return "email-list";
  if (/^user\s+saved-commands\s+list$/i.test(path)) return "saved-commands";
  if (/^email\s+sieve\s+list$/i.test(path)) return "sieve-list";
  return null;
}

/**
 * Build initial data object for the add form from typed args.
 * Maps positional args + flags to form field names.
 */
function buildInitialData(node, leafName, paramTokens, flags) {
  const data = {};

  // Map positional args to form field names
  if (node.params) {
    for (let i = 0; i < paramTokens.length && i < node.params.length; i++) {
      const paramName = node.params[i].name;
      data[paramName] = paramTokens[i];
    }
  }

  // Merge flags (flag names already match form field names)
  for (const [key, val] of Object.entries(flags)) {
    if (val && typeof val === "string" && val.length > 0) {
      data[key] = val;
    }
  }

  return data;
}

/**
 * Determine the addFormType for StatusPopup based on the command path.
 * This tells StatusPopup which form overlay to show.
 */
function resolveAddFormType(tokens, leafName) {
  const path = tokens.join(" ");

  if (/^email\s+account\s+add$/i.test(path)) return "email";
  if (/^calendar\s+account\s+add$/i.test(path)) return "calendar";
  if (/^contacts\s+add$/i.test(path)) return "contacts";
  if (/^todo\s+add$/i.test(path)) return "todo";
  if (/^journal\s+write$/i.test(path)) return "journal-write";
  if (/^email\s+sieve\s+add$/i.test(path)) return "sieve";
  if (/^email\s+send$/i.test(path)) return "email-send";
  if (/^calendar\s+event\s+add$/i.test(path)) return "calendar-event-add";

  // Fallback: use leaf name
  return leafName;
}

/**
 * Human-readable title for the add form dialog.
 */
function resolveAddTitle(addFormType) {
  const titles = {
    email: "Add Email Account",
    calendar: "Add Calendar Account",
    contacts: "Add Contact",
    todo: "Add Todo",
    "journal-write": "Write Journal Entry",
    sieve: "Add Sieve Script",
    "email-send": "Compose Email",
    "calendar-event-add": "Add Calendar Event",
  };
  return titles[addFormType] || "Add";
}

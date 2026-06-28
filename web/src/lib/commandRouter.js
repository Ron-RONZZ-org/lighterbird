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

  // ── Check for missing required params or flags ──────────────────
  const cmdTokenCount = countCommandTokens(effectiveTokens);
  const consumed = effectiveTokens.length - cmdTokenCount;

  const missingRequiredParam = node.params?.some(
    (p, i) => p.required && i >= consumed,
  );

  // Also check for required flags (e.g. user.saved-commands.add --alias)
  const missingRequiredFlag = node.flags?.some(
    (f) => f.required && !(f.name in flags),
  );

  // Only intercept if required params or flags are missing
  if (!missingRequiredParam && !missingRequiredFlag) return { intercept: false };

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
  // 1. Explicit listCommand on the node (highest priority)
  if (node.listCommand && Array.isArray(node.listCommand)) {
    return node.listCommand;
  }

  // 2. Convention: replace last token "add"/"write" with "list"
  const leafName = tokens[tokens.length - 1];
  if (leafName === "add" || leafName === "write") {
    const listTokens = tokens.slice(0, -1);
    listTokens.push("list");
    const listNode = findNode(listTokens);
    if (listNode) return listTokens;
  }

  // 3. For interactive commands that aren't add/write (e.g. "send", "modify"),
  // try replacing action verb with "list" using the parent domain as root
  if (node.interactive && tokens.length >= 2) {
    // Try "domain list" e.g. ["email", "list"] for ["email", "send"]
    const domain = tokens[0];
    const listTokens = [domain, "list"];
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
  if (/^contacts\s+list$/i.test(path)) return "contacts-list";
  if (/^todo\s+list$/i.test(path)) return "todo-list";
  if (/^journal\s+list$/i.test(path)) return "journal-list";
  if (/^calendar\s+list$/i.test(path)) return "calendar-events";
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

  if (/^email\s+account\s+add$/i.test(path)) return "email-account-add";
  if (/^calendar\s+account\s+add$/i.test(path)) return "calendar-account-add";
  if (/^contacts\s+add$/i.test(path)) return "contacts-add";
  if (/^todo\s+add$/i.test(path)) return "todo-add";
  if (/^journal\s+write$/i.test(path)) return "journal-write";
  if (/^email\s+sieve\s+add$/i.test(path)) return "email-sieve-add";
  if (/^email\s+send$/i.test(path)) return "email-send";
  if (/^calendar\s+event\s+add$/i.test(path)) return "calendar-event-add";
  if (/^user\s+saved-commands\s+add$/i.test(path)) return "user-saved-commands-add";
  if (/^user\s+saved-commands\s+modify$/i.test(path)) return "user-saved-commands-modify";
  if (/^todo\s+template\s+add$/i.test(path)) return "todo-template-add";
  if (/^todo\s+template\s+modify$/i.test(path)) return "todo-template-modify";
  if (/^llm\s+profile\s+new$/i.test(path)) return "llm-profile-new";
  if (/^llm\s+profile\s+set$/i.test(path)) return "llm-profile-set";
  if (/^backup\s+config\s+add$/i.test(path)) return "backup-config-add";
  if (/^backup\s+config\s+modify$/i.test(path)) return "backup-config-modify";

  // Fallback: use leaf name
  return leafName;
}

/**
 * Human-readable title for the add form dialog.
 */
function resolveAddTitle(addFormType) {
  const titles = {
    "email-account-add": "Add Email Account",
    "calendar-account-add": "Add Calendar Account",
    "contacts-add": "Add Contact",
    "todo-add": "Add Todo",
    "journal-write": "Write Journal Entry",
    "email-sieve-add": "Add Sieve Script",
    "email-send": "Compose Email",
    "calendar-event-add": "Add Calendar Event",
    "user-saved-commands-add": "New Saved Command",
    "user-saved-commands-modify": "Edit Saved Command",
    "todo-template-add": "New Todo Template",
    "todo-template-modify": "Edit Todo Template",
    "llm-profile-new": "New LLM Profile",
    "llm-profile-set": "Set LLM Profile",
    "backup-config-add": "Add Backup Strategy",
    "backup-config-modify": "Modify Backup Strategy",
  };
  return titles[addFormType] || "Add";
}

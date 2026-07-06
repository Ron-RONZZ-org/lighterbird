/** Command completion engine — level-by-level suggestions.
 *
 * Levels:
 *   0: Root command (after !)
 *   1-N: Children of the current node
 *   N+1: Parameters and flags of a leaf node
 *
 * ``/*`` prompt commands are also supported — see :func:`getPromptCompletions`.
 */

import { commandTree, promptCommands, findNode, matchChildren } from "./commandTree.js";
import { parseCommand, parsePromptCommand, hasTrailingSpace } from "./parser.js";

/**
 * @param {string} input — raw user input
 * @returns {{
 *   completions: string[],          // suggested completions for current level
 *   hints: string[],                // parameter/flag hints (shown below the input)
 *   node: object|null,              // resolved leaf node
 *   level: string,                  // "root" | "child" | "params" | "flags"
 *   positionals: {name:string, entered:boolean, required:boolean}[],
 * }}
 */
export function getCompletions(input) {
  const { tokens, flags, partial } = parseCommand(input);
  const trailing = hasTrailingSpace(input);

  // Fix: when trailing space is present, the 'partial' token is actually a
  // complete token that the parser couldn't distinguish (split loses trailing
  // empty string). Promote it to tokens for correct tree walking.
  const effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
  const effectivePartial = trailing ? "" : partial;

  // Root level: after !
  if (effectiveTokens.length === 0 && !trailing) {
    const prefix = effectivePartial.replace(/^!/, "");
    if (!prefix) {
      // Just "!" — show root names with ! prefix for consistency
      return {
        completions: commandTree.map((n) => `!${n.name}`),
        hints: commandTree.map((n) => n.description || ""),
        node: null,
        level: "root",
        positionals: [],
      };
    }
    const matches = matchChildren(commandTree, prefix);
    return {
      completions: matches.map((n) => `!${n.name}`),
      hints: matches.map((n) => n.description || ""),
      node: null,
      level: "root",
      positionals: [],
    };
  }

  // If user is at root with trailing space and nothing typed after !
  if (effectiveTokens.length === 0 && trailing) {
    return {
      completions: commandTree.map((n) => `!${n.name}`),
      hints: commandTree.map((n) => n.description || ""),
      node: null,
      level: "root",
      positionals: [],
    };
  }

  // Walk the command tree to find current position
  const node = findNode(effectiveTokens);

  if (!node) {
    // Partial token at this level — find suggestions
    const parent = findNode(effectiveTokens.slice(0, -1));
    const partialToken = effectiveTokens[effectiveTokens.length - 1];
    if (parent && parent.children) {
      const matches = matchChildren(parent.children, partialToken);
      return {
        completions: matches.map((n) => n.name),
        hints: matches.map((n) => n.description || ""),
        node: null,
        level: "child",
        positionals: [],
      };
    }
    if (!parent) {
      const matches = matchChildren(commandTree, partialToken);
      return {
        completions: matches.map((n) => `!${n.name}`),
        hints: matches.map((n) => n.description || ""),
        node: null,
        level: "root",
        positionals: [],
      };
    }
    if (parent.params || parent.flags) {
      const paramHints = buildParamHints(parent, effectiveTokens.slice(findNodeIndex(effectiveTokens) + 1), flags, effectivePartial);
      const posInfo = buildPositionalInfo(parent, effectiveTokens.slice(findNodeIndex(effectiveTokens) + 1));
      return {
        completions: paramHints.map((h) => h.text),
        hints: paramHints.map((h) => h.desc),
        node: parent,
        level: "params",
        positionals: posInfo,
      };
    }
    return { completions: [], hints: [], node: null, level: "root", positionals: [] };
  }

  // Exact node found
  if (node.children) {
    if (trailing) {
      return {
        completions: node.children.map((c) => c.name),
        hints: node.children.map((c) => c.description || ""),
        node,
        level: "child",
        positionals: [],
      };
    }
    if (effectivePartial) {
      // If partial looks like --help, show all children as help
      if (effectivePartial.startsWith("--") &&
          ("help".startsWith(effectivePartial.slice(2).toLowerCase()) ||
           effectivePartial.slice(2).toLowerCase().startsWith("help"))) {
        return {
          completions: node.children.map((c) => c.name),
          hints: node.children.map((c) => c.description || ""),
          node,
          level: "child",
          positionals: [],
        };
      }
      const matches = matchChildren(node.children, effectivePartial);
      return {
        completions: matches.map((c) => c.name),
        hints: matches.map((c) => c.description || ""),
        node,
        level: "child",
        positionals: [],
      };
    }
    return { completions: [], hints: [], node, level: "child", positionals: [] };
  }

  // Leaf node — show flags and positional info
  if (trailing || effectivePartial) {
    const consumed = effectiveTokens.slice(findNodeIndex(effectiveTokens) + 1);
    const paramHints = buildParamHints(node, consumed, flags, effectivePartial);
    const posInfo = buildPositionalInfo(node, consumed);
    return {
      completions: paramHints.map((h) => h.text),
      hints: paramHints.map((h) => h.desc),
      node,
      level: "params",
      positionals: posInfo,
    };
  }

  return { completions: [], hints: [], node, level: "params", positionals: [] };
}

/**
 * Build positional tracker info: which params are entered vs pending.
 * @param {object} node — leaf command node
 * @param {string[]} consumedTokens — positional tokens already typed
 * @returns {{name:string, entered:boolean, required:boolean}[]}
 */
function buildPositionalInfo(node, consumedTokens) {
  if (!node.params || node.params.length === 0) return [];
  return node.params.map((p, i) => ({
    name: p.name,
    entered: i < consumedTokens.length,
    required: p.required,
  }));
}

/**
 * Build parameter/flag hints for a leaf command node.
 * Only flag completions are returned — positional args are shown
 * via the tracker row (buildPositionalInfo) instead.
 * @param {string} [partial] — partial input for filtering flags (e.g. "--c")
 */
function buildParamHints(node, consumedTokens, flags, partial = "") {
  const hints = [];
  const isFlagPartial = partial.startsWith("--");

  // If user is typing a flag (e.g. "--c"), show only matching flags
  if (isFlagPartial) {
    const partialFlag = partial.slice(2).toLowerCase();

    // Synthetic --help flag: show all params and flags of this command
    if (partialFlag === "help" || "help".startsWith(partialFlag)) {
      if (node.params) {
        for (const p of node.params) {
          const required = p.required ? " (required)" : "";
          hints.push({
            text: `<${p.name}>`,
            desc: `${p.type}${required}${p.placeholder ? ` e.g. ${p.placeholder}` : ""}`,
          });
        }
      }
      if (node.flags) {
        for (const f of node.flags) {
          const short = f.short ? `-${f.short}, ` : "";
          const repeatable = f.repeatable ? " (repeatable)" : "";
          const uuidSrc = f.uuidSource ? " (auto-complete)" : "";
          hints.push({
            text: `--${f.name}`,
            desc: `${short}${f.help || f.type}${repeatable}${uuidSrc}`,
          });
        }
      }
      return hints;
    }

    if (node.flags) {
      for (const f of node.flags) {
        if (f.name.toLowerCase().startsWith(partialFlag)) {
          hints.push({
            text: `--${f.name}`,
            desc: `${f.short ? `-${f.short}, ` : ""}${f.help || f.type}`,
          });
        }
      }
    }
    return hints;
  }

  // Available flags (only if user isn't already filling one)
  if (!partial && node.flags) {
    const usedFlags = new Set(Object.keys(flags));
    for (const f of node.flags) {
      if (!usedFlags.has(f.name)) {
        const short = f.short ? `-${f.short}, ` : "";
        hints.push({
          text: `--${f.name}`,
          desc: `${short}${f.help || f.type}`,
        });
      }
    }
  }

  return hints;
}

function findNodeIndex(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find(
      (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
    );
    if (!found) return i - 1;
    // Leaf node — no children means this is the command name
    if (!found.children || found.children.length === 0) return i;
    current = found.children || [];
  }
  return tokens.length - 1;
}

/**
 * Fetch context-aware completions (UUIDs) from the cache.
 * @param {object} cachedData — { accounts, calendars, contacts, todos, journal }
 * @param {string} [uuidSource] — optional filter like "email.listAccounts" or "contacts.list"
 * @returns {{ uuid: string, label: string }[]}
 */
export function getDataCompletionsFromCache(cachedData, uuidSource) {
  if (!cachedData) return [];
  const result = [];

  if (!uuidSource) {
    // Return everything
    addAccounts(cachedData, result);
    addCalendars(cachedData, result);
    addContacts(cachedData, result);
    return result;
  }

  if (uuidSource.startsWith("email.")) addAccounts(cachedData, result);
  if (uuidSource.startsWith("calendar.")) addCalendars(cachedData, result);
  if (uuidSource.startsWith("contacts.")) addContacts(cachedData, result);
  if (uuidSource.startsWith("todo.")) addTodos(cachedData, result);
  if (uuidSource.startsWith("journal.")) addJournal(cachedData, result);
  if (uuidSource === "email.folders") addFolders(cachedData, result);

  return result;
}

function addAccounts(cache, result) {
  if (cache.accounts) {
    for (const a of cache.accounts) {
      result.push({ uuid: a.uuid, label: `${a.email} (${a.name || ""})` });
    }
  }
}

function addCalendars(cache, result) {
  if (cache.calendars) {
    for (const c of cache.calendars) {
      result.push({ uuid: c.uuid, label: c.url });
    }
  }
}

function addContacts(cache, result) {
  if (cache.contacts) {
    for (const c of cache.contacts) {
      result.push({ uuid: c.uuid, label: `${c.nomo || ""} <${c.retposto || ""}>` });
    }
  }
}

function addTodos(cache, result) {
  if (cache.todos) {
    for (const t of cache.todos) {
      result.push({ uuid: t.uuid, label: t.title || "(untitled)" });
    }
  }
}

function addJournal(cache, result) {
  if (cache.journal) {
    for (const e of cache.journal) {
      result.push({ uuid: e.uuid, label: `${e.date || ""} — ${e.title || ""}` });
    }
  }
}

function addFolders(cache, result) {
  if (cache.folders) {
    for (const f of cache.folders) {
      // Folders use value-based completion (folder name, not UUID)
      result.push({
        uuid: f.folder_name,
        label: f.label || `${f.account_email}/${f.folder_name}`,
        value: f.label || `${f.account_email}/${f.folder_name}`,
      });
    }
  }
}

/**
 * Get autocomplete completions for prompt commands (/* prefix).
 *
 * When input starts with ``/`` or ``/*``, returns matching prompt command names
 * with descriptions as hints. Otherwise returns empty arrays.
 *
 * @param {string} input — the raw user input
 * @returns {{ completions: string[], hints: string[] }}
 */
export function getPromptCompletions(input) {
  const parsed = parsePromptCommand(input);
  if (!parsed) {
    // Check if input starts with just "/" (but not "/*")
    const trimmed = input.trim();
    if (trimmed.startsWith("/") && !trimmed.startsWith("/*")) {
      // Show all prompt commands when user types just "/"
      return {
        completions: promptCommands.map((c) => `/*${c.name}`),
        hints: promptCommands.map((c) => c.description || ""),
      };
    }
    return { completions: [], hints: [] };
  }

  // User has typed "/*" or "/*name"
  const prefix = parsed.name.toLowerCase();
  if (!prefix) {
    // Just "/*" — show all
    return {
      completions: promptCommands.map((c) => `/*${c.name}`),
      hints: promptCommands.map((c) => c.description || ""),
    };
  }

  // Filter by prefix
  const matches = promptCommands.filter((c) =>
    c.name.toLowerCase().startsWith(prefix),
  );
  return {
    completions: matches.map((c) => `/*${c.name}`),
    hints: matches.map((c) => c.description || ""),
  };
}

/** Command completion engine — level-by-level suggestions.
 *
 * Levels:
 *   0: Root command (after !)
 *   1-N: Children of the current node
 *   N+1: Parameters and flags of a leaf node
 */

import { commandTree, findNode, matchChildren } from "./commandTree.js";
import { parseCommand, hasTrailingSpace } from "./parser.js";

/**
 * @param {string} input — raw user input
 * @returns {{
 *   completions: string[],    // suggested completions for current level
 *   hints: string[],          // parameter/flag hints (shown below the input)
 *   node: object|null,        // resolved leaf node
 *   level: string,            // "root" | "child" | "params" | "flags"
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
      };
    }
    const matches = matchChildren(commandTree, prefix);
    return {
      completions: matches.map((n) => `!${n.name}`),
      hints: matches.map((n) => n.description || ""),
      node: null,
      level: "root",
    };
  }

  // If user is at root with trailing space and nothing typed after !
  if (effectiveTokens.length === 0 && trailing) {
    return {
      completions: commandTree.map((n) => `!${n.name}`),
      hints: commandTree.map((n) => n.description || ""),
      node: null,
      level: "root",
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
      };
    }
    if (!parent) {
      const matches = matchChildren(commandTree, partialToken);
      return {
        completions: matches.map((n) => `!${n.name}`),
        hints: matches.map((n) => n.description || ""),
        node: null,
        level: "root",
      };
    }
    if (parent.params || parent.flags) {
      const paramHints = buildParamHints(parent, effectiveTokens.slice(1), flags, effectivePartial);
      return {
        completions: paramHints.map((h) => h.text),
        hints: paramHints.map((h) => h.desc),
        node: parent,
        level: "params",
      };
    }
    return { completions: [], hints: [], node: null, level: "root" };
  }

  // Exact node found
  if (node.children) {
    if (trailing) {
      return {
        completions: node.children.map((c) => c.name),
        hints: node.children.map((c) => c.description || ""),
        node,
        level: "child",
      };
    }
    if (effectivePartial) {
      const matches = matchChildren(node.children, effectivePartial);
      return {
        completions: matches.map((c) => c.name),
        hints: matches.map((c) => c.description || ""),
        node,
        level: "child",
      };
    }
    return { completions: [], hints: [], node, level: "child" };
  }

  // Leaf node — show params and flags
  if (trailing || effectivePartial) {
    const consumed = effectiveTokens.slice(findNodeIndex(effectiveTokens) + 1);
    const paramHints = buildParamHints(node, consumed, flags, effectivePartial);
    return {
      completions: paramHints.map((h) => h.text),
      hints: paramHints.map((h) => h.desc),
      node,
      level: "params",
    };
  }

  return { completions: [], hints: [], node, level: "params" };
}

/**
 * Build parameter/flag hints for a leaf command node.
 * @param {string} [partial] — partial input for filtering flags (e.g. "--c")
 */
function buildParamHints(node, consumedTokens, flags, partial = "") {
  const hints = [];
  const isFlagPartial = partial.startsWith("--");

  // If user is typing a flag (e.g. "--c"), show only matching flags
  if (isFlagPartial) {
    const partialFlag = partial.slice(2).toLowerCase();
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

  // Positional params not yet filled.
  // Skip params with uuidSource — they get real completions from
  // fetchDataCompletions() instead of a <placeholder> hint.
  if (node.params) {
    const filledCount = consumedTokens.length;
    for (let i = filledCount; i < node.params.length; i++) {
      const p = node.params[i];
      if (p.uuidSource) continue; // Provided by fetchDataCompletions
      const prefix = p.required ? "<" : "[";
      const suffix = p.required ? ">" : "]";
      hints.push({
        text: `${prefix}${p.name}${suffix}`,
        desc: p.placeholder || p.name,
      });
    }
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
    if (found.apiMethod) return i;
    current = found.children || [];
  }
  return tokens.length - 1;
}

/**
 * Fetch context-aware completions (UUIDs) from the cache.
 * @param {object} cachedData — { accounts: [...], calendars: [...] }
 * @param {string} [uuidSource] — optional filter like "email.listAccounts" or "calendar.listCalendars"
 * @returns {{ uuid: string, label: string }[]}
 */
export function getDataCompletionsFromCache(cachedData, uuidSource) {
  if (!cachedData) return [];
  const result = [];
  // If uuidSource is specified, only return matching type
  const wantAccounts = !uuidSource || uuidSource.startsWith("email.");
  const wantCalendars = !uuidSource || uuidSource.startsWith("calendar.");
  if (wantAccounts && cachedData.accounts && cachedData.accounts.length > 0) {
    for (const a of cachedData.accounts) {
      result.push({ uuid: a.uuid, label: `${a.email} (${a.name || ""})` });
    }
  }
  if (wantCalendars && cachedData.calendars && cachedData.calendars.length > 0) {
    for (const c of cachedData.calendars) {
      result.push({ uuid: c.uuid, label: c.url });
    }
  }
  return result;
}

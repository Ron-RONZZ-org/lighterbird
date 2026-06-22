/** Parse user input into tokens, flags, and cursor position.
 *
 * Handles:
 *   "!account add"        → { tokens:["account","add"], flags:{}, partial:"" }
 *   "!events --calendar"  → { tokens:["events"], flags:{}, partial:"--calendar" }
 *   "!events --limit 10"  → { tokens:["events"], flags:{limit:"10"}, partial:"" }
 *   "!ac"                 → { tokens:[], flags:{}, partial:"ac" }
 *   "!account "           → { tokens:["account"], flags:{}, partial:"" }
 */

/**
 * @param {string} input — the raw input string
 * @returns {{ tokens:string[], flags:Record<string,string>, partial:string }}
 */
export function parseCommand(input) {
  const trimmed = input.trim();
  if (!trimmed || !trimmed.startsWith("!")) {
    // Everything before ! or without ! goes to LLM (future)
    return { tokens: [], flags: {}, partial: trimmed.replace(/^!/, "") };
  }

  const withoutBang = trimmed.slice(1).trimStart();
  const parts = withoutBang.split(/\s+/);
  const tokens = [];
  const flags = {};
  let partial = "";
  let i = 0;

  while (i < parts.length) {
    const p = parts[i];
    const isLast = i === parts.length - 1;

    if (p.startsWith("--")) {
      const flagName = p.slice(2);
      const eqIdx = flagName.indexOf("=");
      if (eqIdx >= 0) {
        // --flag=value
        flags[flagName.slice(0, eqIdx)] = flagName.slice(eqIdx + 1);
      } else if (isLast) {
        // Trailing --flag (incomplete — user hasn't typed value yet)
        partial = p;
      } else {
        // --flag value
        flags[flagName] = parts[++i];
      }
    } else if (p.startsWith("-") && p.length > 1 && !p.startsWith("--")) {
      // Short flag -f (we keep it as partial for now, expand later)
      partial = p;
    } else {
      // Positional token
      if (isLast) {
        // Could be a complete token or a partial (user still typing)
        // We treat it as a token if there's a trailing space
        // But we can't detect trailing space from split input alone
        partial = p;
      } else {
        tokens.push(p);
      }
    }
    i++;
  }

  return { tokens, flags, partial };
}

/**
 * Check if the input has a trailing space (meaning user is ready for next level).
 * @param {string} input
 * @returns {boolean}
 */
export function hasTrailingSpace(input) {
  return input.endsWith(" ");
}

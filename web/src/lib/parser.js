/** Parse user input into tokens, flags, and cursor position.
 *
 * Handles:
 *   "!email list"             → { tokens:["email","list"], flags:{}, partial:"" }
 *   "!email send to@x.com 'Subj' 'Body'"  → { tokens:["email","send","to@x.com","Subj","Body"], ... }
 *   "!events --calendar"      → { tokens:["events"], flags:{}, partial:"--calendar" }
 *   "!events --limit 10"      → { tokens:["events"], flags:{limit:"10"}, partial:"" }
 *   "!contacts add --phone X" → { tokens:["contacts","add"], flags:{phone:"X"}, partial:"" }
 *   "!ac"                     → { tokens:[], flags:{}, partial:"ac" }
 *   "!email "                 → { tokens:["email"], flags:{}, partial:"" }
 */

/**
 * @param {string} input — the raw input string
 * @returns {{ tokens:string[], flags:Record<string,string>, partial:string }}
 */
export function parseCommand(input) {
  const trimmed = input.trim();
  if (!trimmed || !trimmed.startsWith("!")) {
    return { tokens: [], flags: {}, partial: trimmed.replace(/^!/, "") };
  }

  const withoutBang = trimmed.slice(1).trimStart();
  const tokens = [];
  const flags = {};
  let partial = "";
  let inFlag = null;     // Set to flag name when expecting a flag value
  let inQuote = false;   // True while inside double quotes
  let current = "";      // Current token being built
  let i = 0;

  const trailing = input.endsWith(" ");

  /** Complete the current flag or positional token. */
  function flush() {
    if (current === "") return;
    if (current.startsWith("--") && inFlag === null) {
      // Looks like a flag (e.g. --phone) — start expecting its value
      inFlag = current.slice(2);
      current = "";
    } else if (inFlag !== null) {
      // A value for the current flag
      flags[inFlag] = current;
      inFlag = null;
      current = "";
    } else {
      // Plain positional token
      tokens.push(current);
      current = "";
    }
  }

  while (i < withoutBang.length) {
    const ch = withoutBang[i];
    const isLast = i === withoutBang.length - 1;

    if (ch === '"') {
      if (inQuote) {
        // Closing quote — flush the accumulated text
        inQuote = false;
        flush();
      } else {
        // Opening quote — start accumulating
        inQuote = true;
        if (current !== "") {
          // Could be --flag="value" case
          const eqIdx = current.indexOf("=");
          if (current.startsWith("--") && eqIdx > 0) {
            inFlag = current.slice(2, eqIdx);
            current = "";
          } else {
            // Text before quote — flush it, then start quoted section
            flush();
          }
        }
      }
    } else if (inQuote) {
      // Inside quotes — accumulate everything
      current += ch;
    } else if (ch === " " || ch === "\t") {
      // Whitespace — complete the current token
      flush();
    } else if (ch === "=" && current.startsWith("--")) {
      // --flag=value inline syntax
      inFlag = current.slice(2);
      current = "";
    } else {
      // Regular character
      current += ch;
    }
    i++;
  }

  // Handle remaining content after the loop
  if (inQuote) {
    // Unclosed quote — treat as partial
    partial = current;
  } else if (current !== "") {
    if (current.startsWith("--")) {
      // Trailing incomplete flag
      partial = current;
    } else if (inFlag !== null) {
      // Flag with value at end (no trailing space)
      flags[inFlag] = current;
    } else if (trailing) {
      // Trailing space means this token is complete
      tokens.push(current);
    } else {
      // No trailing space — user may still be typing
      partial = current;
    }
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

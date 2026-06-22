/** Command dispatcher — resolves user input to API call.
 *
 * Walks the command tree, validates required params, builds API args,
 * and executes the call via api.js.
 */

import { commandTree, findNode } from "./commandTree.js";
import { parseCommand } from "./parser.js";
import { email, calendar, admin } from "./api.js";

const api = { email, calendar, admin };

/** Built-in commands that don't call an API endpoint. */
const builtins = {
  help: async () => {
    const lines = [];
    function walk(nodes, indent) {
      for (const n of nodes) {
        const prefix = `!${"  ".repeat(indent)}`;
        if (n.children) {
          lines.push({ name: `${prefix}${n.name}`, description: n.description || "" });
          walk(n.children, indent + 1);
        } else {
          const params = (n.params || [])
            .map((p) => (p.required ? `<${p.name}>` : `[${p.name}]`))
            .join(" ");
          const flags = (n.flags || [])
            .map((f) => `--${f.name}`)
            .join(" ");
          const fullName = `${prefix}${n.name} ${params} ${flags}`.trim();
          lines.push({ name: fullName, description: n.description || "" });
        }
      }
    }
    walk(commandTree, 0);
    return { type: "help", title: "Available Commands", data: lines };
  },
};

/**
 * Execute a user command and return a popup response.
 *
 * @param {string} input — raw user input (e.g. "!account list")
 * @returns {{ type: string, title: string, data: any }}
 */
export async function execute(input) {
  const trimmed = input.trim();

  if (!trimmed.startsWith("!")) {
    // LLM chat — not implemented in MVP
    return {
      type: "status",
      title: "LLM Chat",
      data: { message: "LLM mode coming in v0.2. Use ! commands for now." },
    };
  }

  const { tokens, flags, partial } = parseCommand(trimmed);

  // At dispatch time (Enter pressed), all input is final.
  // The parser may have put the last token in `partial` due to no trailing
  // space — promote it to a real token for correct tree walking.
  const effectiveTokens = partial ? [...tokens, partial] : tokens;

  if (effectiveTokens.length === 0) {
    return { type: "status", title: "Error", data: { message: "No command specified." } };
  }

  // Find the leaf node
  const node = findNode(effectiveTokens);

  if (!node) {
    return {
      type: "error",
      title: "Unknown Command",
      data: { message: `Unknown command: !${effectiveTokens.join(" ")}. Type !help to see commands.` },
    };
  }

  // If node has children, user didn't go deep enough
  if (node.children) {
    const subs = node.children.map((c) => c.name).join(", ");
    return {
      type: "status",
      title: `!${effectiveTokens.join(" ")}`,
      data: { message: `Available subcommands: ${subs}` },
    };
  }

  // Handle built-in commands
  if (node.apiMethod && node.apiMethod.startsWith("builtin.")) {
    const builtinKey = node.apiMethod.split(".")[1];
    if (builtins[builtinKey]) {
      return await builtins[builtinKey]();
    }
  }

  // Validate required params
  if (node.params) {
    // Positional params come after the command tokens
    const paramTokens = effectiveTokens.slice(countCommandTokens(effectiveTokens));
    for (let i = 0; i < node.params.length; i++) {
      const p = node.params[i];
      if (p.required && i >= paramTokens.length) {
        return {
          type: "error",
          title: "Missing Parameter",
          data: { message: `Required parameter <${p.name}> is missing.`, suggestion: `Type !${node.name} for usage hints.` },
        };
      }
    }
  }

  // Build API call
  if (node.apiMethod) {
    const parts = node.apiMethod.split(".");
    const module = parts[0];
    const method = parts[1];
    const apiModule = api[module];
    if (!apiModule || !apiModule[method]) {
      return {
        type: "error",
        title: "Internal Error",
        data: { message: `API method not found: ${node.apiMethod}` },
      };
    }

    // Build args from params and flags using the command tree definitions
    const paramTokens = effectiveTokens.slice(countCommandTokens(effectiveTokens));
    const args = {};

    // Special cases (commands with non-standard param→API mapping)
    if (node.name === "send") {
      args.to = paramTokens[0] ? [paramTokens[0]] : [];
      args.subject = paramTokens[1] || "";
      args.body = paramTokens.slice(2).join(" ") || "";
    } else if (node.name === "add" && effectiveTokens[0] === "account") {
      args.email = paramTokens[0] || "";
      args.imap_server = paramTokens[1] || "";
      args.smtp_server = paramTokens[2] || "";
      args.password = paramTokens[3] || "";
    } else if (node.name === "events") {
      args.start = paramTokens[0] || "2000-01-01";
      args.end = paramTokens[1] || "2099-12-31";
    } else {
      // General mapper: param name → API arg name (replace hyphens with underscores)
      const p = node.params || [];
      for (let i = 0; i < p.length; i++) {
        const apiName = p[i].name.replace(/-/g, "_");
        args[apiName] = paramTokens[i] || "";
      }
    }

    // Add flags
    Object.assign(args, flags);

    try {
      // API functions have different signatures:
      //   - No args:      email.listAccounts(), calendar.listCalendars()
      //   - Single UUID:  email.deleteAccount(uuid), email.getMessage(uuid),
      //                   calendar.sync(uuid), calendar.getEvent(uuid),
      //                   calendar.deleteEvent(uuid)
      //   - Repeatable:   !account remove uuid1 uuid2 → one call per token
      //   - Object:       email.createAccount(data), calendar.createEvent(data)
      //
      const hasRepeatableUuid = node.params?.length === 1 &&
        node.params[0].repeatable && node.params[0].type === "uuid";
      const hasSingleUuidParam = !hasRepeatableUuid &&
        node.params?.length === 1 && node.params[0].type === "uuid";
      const hasFlags = Object.keys(flags).length > 0;
      let data;
      if (hasRepeatableUuid && !hasFlags && paramTokens.length > 0) {
        const succeeded = [];
        const errors = [];
        for (const uuid of paramTokens) {
          try {
            const result = await apiModule[method](uuid);
            succeeded.push(uuid.slice(0, 8));
          } catch (err) {
            errors.push(`${uuid.slice(0, 8)}: ${err.message}`);
          }
        }
        const statusText = errors.length === 0
          ? `${succeeded.length} done`
          : `${succeeded.length} done, ${errors.length} failed`;
        data = { status: statusText, details: errors.length > 0 ? errors : undefined };
      } else if (hasSingleUuidParam && !hasFlags) {
        data = await apiModule[method](paramTokens[0] || "");
      } else if (Object.keys(args).length === 0) {
        data = await apiModule[method]();
      } else {
        data = await apiModule[method](args);
      }
      const responseType = node.responseType || "status";
      const title = node.description || node.name;
      return { type: responseType, title, data };
    } catch (err) {
      return {
        type: "error",
        title: "Command Failed",
        data: { message: err.message, suggestion: err.suggestion || "" },
      };
    }
  }

  return {
    type: "status",
    title: "OK",
    data: { message: "Command executed." },
  };
}

/** Count how many tokens at the start describe the command path.
 *
 * Stops at the first leaf node (one with an ``apiMethod``).
 * Returns the index of the first parameter token.
 */
function countCommandTokens(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find(
      (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
    );
    if (!found) return i;
    if (found.apiMethod) return i + 1; // Leaf — this and all after are params
    current = found.children || [];
  }
  return tokens.length;
}

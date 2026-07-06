/** Command hierarchy — single source of truth for autocomplete.
 *
 * The authoritative tree lives in ``tree.py`` (backend) and is served via
 * ``GET /api/v1/command/tree``. This file starts empty and fetches the
 * live tree on startup via :func:`initCommandTree`.
 *
 * ``/*`` prompt commands are also fetched from the backend and appended as
 * a virtual root node with children. See :func:`initPromptCommands`.
 *
 * There is NO hardcoded fallback — the only source of truth is the backend.
 * See ``src/lighterbird/server/command/tree.py``.
 */

/** @typedef {{name:string, required:boolean, type:string, placeholder?:string, repeatable?:boolean, uuidSource?:string}} ParamDef */
/** @typedef {{name:string, short?:string, type:string, help?:string}} FlagDef */
/** @typedef {{name:string, description?:string, children?:CommandNode[], params?:ParamDef[], flags?:FlagDef[], interactive?:boolean}} CommandNode */

/**
 * The live command tree — initially empty, populated by :func:`initCommandTree`.
 * @type {CommandNode[]}
 */
export let commandTree = [];

/**
 * List of prompt commands (/* prefix) — flat array of {name, description}.
 * Populated by :func:`initPromptCommands`.
 * @type {{name:string, description:string}[]}
 */
export let promptCommands = [];

/* ── Dynamic fetch from backend ────────────────────────────────────────── */

/**
 * Fetch the authoritative command tree from the backend and replace the
 * live ``commandTree`` binding. The tree starts empty and is populated
 * by this function.
 *
 * Call this once on app startup. Because ``commandTree`` is declared with
 * ``let``, ES module live bindings propagate the new value to every
 * consumer without a reload.
 */
export async function initCommandTree() {
  try {
    const resp = await fetch("/api/v1/command/tree");
    if (resp.ok) {
      commandTree = await resp.json();
    }
  } catch {
    // Fetch failed — tree stays empty until next page load.
    // The app degrades gracefully: autocomplete shows nothing, but
    // commands still work via direct backend dispatch.
  }
}

/**
 * Fetch prompt commands from the backend and populate the ``promptCommands``
 * list. Also appends a virtual ``/*`` node to ``commandTree`` for autocomplete.
 *
 * Call this alongside :func:`initCommandTree` on app startup.
 */
export async function initPromptCommands() {
  try {
    const resp = await fetch("/api/v1/prompt-commands/list");
    if (resp.ok) {
      const cmds = await resp.json();
      promptCommands = cmds;

      // Append virtual /* root node to the command tree
      if (cmds.length > 0) {
        const existing = commandTree.find((n) => n.name === "/*");
        if (!existing) {
          commandTree.push({
            name: "/*",
            description: "Prompt commands",
            children: cmds.map((c) => ({
              name: c.name,
              description: c.description,
            })),
          });
        }
      }
    }
  } catch {
    // Fetch failed — degrade gracefully: no prompt command autocomplete,
    // but /* commands still work via direct backend execution.
  }
}

// Auto-init on module load. The tree starts empty; the dynamic fetch
// replaces it when the response arrives (typically <100ms on localhost).
initCommandTree();

// Also fetch prompt commands. Both fetches run in parallel.
initPromptCommands();

/** Build a flat list of all root-level command names (for initial ! completion). */
export function getRootNames() {
  return commandTree.map((n) => n.name);
}

/** Find the deepest node matching a path of tokens (case-insensitive).
 *
 * Stops at leaf nodes — remaining tokens are parameter values.
 * Returns ``null`` if zero tokens match.
 */
export function findNode(tokens) {
  let current = commandTree;
  let node = null;
  for (const token of tokens) {
    const matched = current.find(
      (n) => n.name.toLowerCase() === token.toLowerCase(),
    );
    if (!matched) return node;
    node = matched;

    // Stop at leaf (no children) — remaining tokens are parameter values
    if (!node.children || node.children.length === 0) return node;
    current = node.children;
  }
  return node;
}

/** Get all children that match a prefix (case-insensitive). */
export function matchChildren(nodes, prefix) {
  const p = prefix.toLowerCase();
  return nodes.filter((n) => n.name.toLowerCase().startsWith(p));
}

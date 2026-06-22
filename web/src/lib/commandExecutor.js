/** Command executor — thin proxy to POST /api/v1/command.
 *
 * The frontend parses input tokens and sends them to the backend.
 * The backend owns validation, alias resolution, and execution.
 * The frontend only handles autocomplete (local, instant).
 */

import { parseCommand } from "./parser.js";

const COMMAND_ENDPOINT = "/api/v1/command";

/**
 * Execute a user command and return a popup response.
 *
 * @param {string} input — raw user input (e.g. "!email list")
 * @returns {{ type: string, title: string, data: any }}
 */
export async function execute(input) {
  const trimmed = input.trim();

  if (!trimmed.startsWith("!")) {
    return {
      type: "status",
      title: "LLM Chat",
      data: { message: "LLM mode coming in v0.2. Use ! commands for now." },
    };
  }

  const { tokens, flags, partial } = parseCommand(trimmed);
  const effectiveTokens = partial ? [...tokens, partial] : tokens;

  if (effectiveTokens.length === 0) {
    return {
      type: "error",
      title: "Error",
      data: { message: "No command specified." },
    };
  }

  // Send to backend for alias resolution + validation + execution
  try {
    const resp = await fetch(COMMAND_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tokens: effectiveTokens,
        flags,
        raw_input: input,
      }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      const detail = data.detail || {};
      const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
      const suggestion = detail.suggestion || "";
      return {
        type: "error",
        title: "Command Failed",
        data: { message: msg, suggestion },
      };
    }

    return data;
  } catch (err) {
    const msg = err.cause?.code === "ECONNREFUSED"
      ? "Cannot connect to the backend. Is `uv run python -m lighterbird` running?"
      : `Network error: ${err.message}`;
    return {
      type: "error",
      title: "Connection Error",
      data: { message: msg },
    };
  }
}

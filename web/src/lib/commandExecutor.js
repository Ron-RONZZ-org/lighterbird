/** Command executor — thin proxy to POST /api/v1/command and /api/v1/chat.
 *
 * The frontend parses input tokens and sends them to the backend.
 * The backend owns validation, alias resolution, and execution.
 * The frontend only handles autocomplete (local, instant).
 *
 * Non-``!`` input is sent to the LLM chat endpoint.``!`` commands go
 * to the command endpoint.
 */

import { parseCommand } from "./parser.js";

const COMMAND_ENDPOINT = "/api/v1/command";
const CHAT_ENDPOINT = "/api/v1/chat";

/**
 * Execute a user command or send a natural language query to the LLM.
 *
 * @param {string} input — raw user input (e.g. "!email list" or "show my inbox")
 * @returns {{ type: string, title: string, data: any }}
 */
export async function execute(input) {
  const trimmed = input.trim();

  // ── Natural language → LLM chat ─────────────────────────────────────
  if (!trimmed.startsWith("!")) {
    try {
      const resp = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const msg = detail.detail?.error || detail.error || `HTTP ${resp.status}`;
        return {
          type: "error",
          title: "Chat Failed",
          data: { message: msg },
        };
      }
      return await resp.json();
    } catch (err) {
      return {
        type: "error",
        title: "Connection Error",
        data: { message: `Chat error: ${err.message}` },
      };
    }
  }

  // ── Structured !command → command endpoint ──────────────────────────
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

/** Command executor — thin proxy to POST /api/v1/command and /api/v1/chat.
 *
 * The frontend parses input tokens and sends them to the backend.
 * The backend owns validation, alias resolution, and execution.
 * The frontend only handles autocomplete (local, instant).
 *
 * ``/*name`` prompt commands go to the prompt-commands endpoint.
 * ``!command`` goes to the command endpoint.
 * Plain text goes to the LLM chat endpoint.
 */

import { parseCommand, parsePromptCommand } from "./parser.js";

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

  // ── Prompt command (/*name) → prompt-commands execute endpoint ──────
  if (trimmed.startsWith("/*")) {
    const parsed = parsePromptCommand(trimmed);
    if (!parsed || !parsed.name) {
      return {
        type: "error",
        title: "Invalid Command",
        data: { message: "Usage: /*command-name [args...]" },
      };
    }
    try {
      const resp = await fetch("/api/v1/prompt-commands/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: parsed.name, args: parsed.args }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const msg = detail.detail?.error || detail.error || `HTTP ${resp.status}`;
        return {
          type: "error",
          title: "Prompt Command Failed",
          data: { message: msg },
        };
      }
      return await resp.json();
    } catch (err) {
      return {
        type: "error",
        title: "Connection Error",
        data: { message: `Prompt command error: ${err.message}` },
      };
    }
  }

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

    // Check content-type before parsing JSON — avoids cryptic
    // "JSON.parse: unexpected end of data" on non-JSON error pages.
    const ct = resp.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      const text = await resp.text().catch(() => "");
      return {
        type: "error",
        title: "Backend Error",
        data: {
          message: text
            ? `Backend returned ${ct || "unknown"} content (HTTP ${resp.status})`
            : `Backend returned empty response (HTTP ${resp.status}). Is the backend running? Try: uv run python -m lighterbird`,
        },
      };
    }

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
    const BACKEND_HELP =
      "Is the Python backend running? Run `uv run python -m lighterbird` in another terminal.";
    const msg = err.cause?.code === "ECONNREFUSED"
      ? `Cannot connect to the backend. ${BACKEND_HELP}`
      : `Network error: ${err.message}. ${BACKEND_HELP}`;
    return {
      type: "error",
      title: "Connection Error",
      data: { message: msg },
    };
  }
}

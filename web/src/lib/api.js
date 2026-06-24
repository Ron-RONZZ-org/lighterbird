/** Thin fetch() wrapper for lighterbird REST API. */

const BASE = "/api/v1";

const BACKEND_HELP =
  "Is the Python backend running? Run `uv run python -m lighterbird` in another terminal.";

async function request(method, path, body = null) {
  let resp;
  try {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== null) {
      opts.body = JSON.stringify(body);
    }
    resp = await fetch(`${BASE}${path}`, opts);
  } catch (err) {
    // Network error (backend not running, DNS failure, etc.)
    const msg = err.cause?.code === "ECONNREFUSED"
      ? `Cannot connect to the backend server on port 8000. ${BACKEND_HELP}`
      : `Network error: ${err.message}. ${BACKEND_HELP}`;
    const e = new Error(msg);
    e.code = "CONNECTION_REFUSED";
    e.status = 0;
    throw e;
  }

  if (resp.status === 204) return null;

  // Parse response body
  let data;
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    try {
      data = await resp.json();
    } catch {
      data = null;
    }
  } else {
    const text = await resp.text();
    // Proxy error (Vite dev server can't reach backend)
    if (resp.status === 502 || resp.status === 504) {
      const e = new Error(
        `Backend server not reachable (HTTP ${resp.status}). ${BACKEND_HELP}`
      );
      e.code = "BACKEND_UNREACHABLE";
      e.status = resp.status;
      throw e;
    }
    data = {
      error: text
        ? `Server returned ${ct || "unknown"} content (HTTP ${resp.status})`
        : `Server returned empty response (HTTP ${resp.status}). ${BACKEND_HELP}`,
    };
  }

  if (!resp.ok) {
    // Handle validation error arrays (FastAPI 422) and object details
    let msg;
    if (Array.isArray(data?.detail)) {
      msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    } else if (typeof data?.detail === "object" && data?.detail !== null) {
      msg = data.detail.error || data.detail.message || JSON.stringify(data.detail);
    } else {
      msg = data?.detail;
    }
    const err = new Error(data?.error || msg || `HTTP ${resp.status}`);
    err.code = data?.code || "UNKNOWN";
    err.suggestion = data?.suggestion || BACKEND_HELP;
    err.status = resp.status;
    throw err;
  }
  return data;
}

// ── Email API ─────────────────────────────────────────────────────────

export const email = {
  listAccounts: () => request("GET", "/email/accounts"),

  createAccount: (data) => request("POST", "/email/accounts", data),

  updateAccount: (uuid, data) => request("PATCH", `/email/accounts/${uuid}`, data),

  deleteAccount: (uuid) => request("DELETE", `/email/accounts/${uuid}`),

  sync: (accountUuid = null) =>
    request("POST", "/email/sync", accountUuid ? { account_uuid: accountUuid } : {}),

  listMessages: (params = {}) => {
    const q = new URLSearchParams();
    if (params.account_uuid) q.set("account_uuid", params.account_uuid);
    if (params.folder) q.set("folder", params.folder);
    if (params.query) q.set("query", params.query);
    if (params.from) q.set("from", params.from);
    if (params.subject) q.set("subject", params.subject);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    return request("GET", `/email/messages?${q}`);
  },

  getMessage: (uuid) => request("GET", `/email/messages/${uuid}`),

  send: (data) => request("POST", "/email/send", data),

  markRead: (uuid, read = true) =>
    request("PATCH", `/email/messages/${uuid}/read`, { read }),

  trash: (uuid) => request("POST", `/email/messages/${uuid}/trash`),

  batchDelete: (uuids) => request("POST", "/email/messages/batch-delete", { uuids }),

  batchMove: (uuids, destinationFolderUuid) =>
    request("POST", "/email/messages/batch-move", { uuids, destination_folder_uuid: destinationFolderUuid }),

  listFolders: () => request("GET", "/email/folders"),
};

// ── Calendar API ──────────────────────────────────────────────────────

export const calendar = {
  listCalendars: () => request("GET", "/calendar/calendars"),

  createCalendar: (data) => request("POST", "/calendar/calendars", data),

  updateCalendar: (uuid, data) => request("PATCH", `/calendar/calendars/${uuid}`, data),

  deleteCalendar: (uuid) => request("DELETE", `/calendar/calendars/${uuid}`),

  sync: (uuid) => request("POST", `/calendar/sync/${uuid}`),

  listEvents: (params = {}) => {
    const q = new URLSearchParams();
    if (params.start) q.set("start", params.start);
    if (params.end) q.set("end", params.end);
    if (params.calendar_uuid) q.set("calendar_uuid", params.calendar_uuid);
    if (params.query) q.set("query", params.query);
    return request("GET", `/calendar/events?${q}`);
  },

  createEvent: (data) => request("POST", "/calendar/events", data),

  getEvent: (uuid) => request("GET", `/calendar/events/${uuid}`),

  deleteEvent: (uuid) => request("DELETE", `/calendar/events/${uuid}`),
};

// ── Contacts API ──────────────────────────────────────────────────────

export const contacts = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.query) q.set("query", params.query);
    if (params.limit) q.set("limit", String(params.limit));
    return request("GET", `/contacts/contacts?${q}`);
  },

  create: (data) => request("POST", "/contacts/contacts", data),

  get: (uuid) => request("GET", `/contacts/contacts/${uuid}`),

  update: (uuid, data) => request("PATCH", `/contacts/contacts/${uuid}`, data),

  delete: (uuid) => request("DELETE", `/contacts/contacts/${uuid}`),
};

// ── Todo API ──────────────────────────────────────────────────────────

export const todo = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.limit) q.set("limit", String(params.limit));
    return request("GET", `/todo/todos?${q}`);
  },

  create: (data) => request("POST", "/todo/todos", data),

  get: (uuid) => request("GET", `/todo/todos/${uuid}`),

  update: (uuid, data) => request("PATCH", `/todo/todos/${uuid}`, data),

  markDone: (uuid) => request("POST", `/todo/todos/${uuid}/done`),

  delete: (uuid) => request("DELETE", `/todo/todos/${uuid}`),
};

// ── Journal API ───────────────────────────────────────────────────────

export const journal = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.date) q.set("date_str", params.date);
    if (params.query) q.set("query", params.query);
    if (params.limit) q.set("limit", String(params.limit));
    return request("GET", `/journal/entries?${q}`);
  },

  create: (data) => request("POST", "/journal/entries", data),

  get: (uuid) => request("GET", `/journal/entries/${uuid}`),

  update: (uuid, data) => request("PATCH", `/journal/entries/${uuid}`, data),

  delete: (uuid) => request("DELETE", `/journal/entries/${uuid}`),
};

// ── LLM API ───────────────────────────────────────────────────────────

export const llm = {
  getConfig: () => request("GET", "/llm/config"),

  configure: (data) => request("POST", "/llm/configure", data),

  resetConfig: () => request("POST", "/llm/reset"),

  listProfiles: () => request("GET", "/llm/profiles"),

  createProfile: (data) => request("POST", "/llm/profiles", data),

  getProfile: (name) => request("GET", `/llm/profiles/${encodeURIComponent(name)}`),

  updateProfile: (name, data) =>
    request("PATCH", `/llm/profiles/${encodeURIComponent(name)}`, data),

  deleteProfile: (name) => request("DELETE", `/llm/profiles/${encodeURIComponent(name)}`),

  loadProfile: (name) => request("POST", `/llm/profiles/${encodeURIComponent(name)}/load`),
};

// ── Admin API ─────────────────────────────────────────────────────────

export const admin = {
  health: () => request("GET", "/health"),
  syncAll: () => request("POST", "/sync/all"),
};

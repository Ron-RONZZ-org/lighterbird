/** Thin fetch() wrapper for lighterbird REST API. */

const BASE = "/api/v1";

const BACKEND_HELP =
  "Is the Python backend running? Run `uv run python -m lighterbird` in another terminal.";

/**
 * Fetch with exponential backoff retry for transient failures.
 * Retries on network errors and HTTP 5xx responses (not 4xx client errors).
 */
async function fetchWithRetry(url, options, retries = 3, baseBackoff = 500) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(url, options);
      // Retry on server errors (5xx) only, not client errors (4xx)
      if (resp.status >= 500 && resp.status < 600 && attempt < retries) {
        await sleep(baseBackoff * 2 ** attempt);
        continue;
      }
      return resp;
    } catch (err) {
      // Network errors (TypeError, ECONNREFUSED) — retry
      if (attempt < retries) {
        await sleep(baseBackoff * 2 ** attempt);
        continue;
      }
      throw err;
    }
  }
  // Unreachable — all attempts exhausted
  throw new Error("Request failed after retries");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request(method, path, body = null, opts = {}) {
  const retry = opts.retry ?? (method === "GET");
  let resp;
  try {
    const fetchOpts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== null) {
      fetchOpts.body = JSON.stringify(body);
    }
    // Pass signal from opts to fetch for AbortController support
    if (opts.signal) {
      fetchOpts.signal = opts.signal;
    }
    resp = retry
      ? await fetchWithRetry(`${BASE}${path}`, fetchOpts)
      : await fetch(`${BASE}${path}`, fetchOpts);
  } catch (err) {
    const msg = err.cause?.code === "ECONNREFUSED"
      ? `Cannot connect to the backend server. ${BACKEND_HELP}`
      : `Network error: ${err.message}. ${BACKEND_HELP}`;
    const e = new Error(msg);
    e.code = "CONNECTION_REFUSED";
    e.status = 0;
    throw e;
  }

  if (resp.status === 204) return null;

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

// ── Email API (natural keys: accounts by email, folders by name) ────────

export const email = {
  listAccounts: () => request("GET", "/email/accounts"),

  createAccount: (data) => request("POST", "/email/accounts", data),

  updateAccount: (email, data) => request("PATCH", `/email/accounts/${encodeURIComponent(email)}`, data),

  deleteAccount: (email) => request("DELETE", `/email/accounts/${encodeURIComponent(email)}`),

  sync: (accountEmail = null) =>
    request("POST", "/email/sync", accountEmail ? { account_email: accountEmail } : {}, { retry: true }),

  syncStart: (accountEmail = null, opts = {}) => {
    const body = {};
    if (accountEmail) body.account_email = accountEmail;
    if (opts.folderName) body.folder_name = opts.folderName;
    if (opts.foldersOnly) body.folders_only = true;
    return request("POST", "/email/sync/start", body);
  },

  getSyncProgress: (taskId) =>
    request("GET", `/email/sync/progress/${encodeURIComponent(taskId)}`),

  getSyncStatus: () =>
    request("GET", "/email/sync/status"),

  listMessages: (params = {}, signal = null) => {
    const q = new URLSearchParams();
    if (params.account_email) q.set("account_email", params.account_email);
    if (params.folder) q.set("folder", params.folder);
    if (params.query) q.set("query", params.query);
    if (params.from) q.set("from", params.from);
    if (params.sender) q.set("sender", params.sender);
    if (params.subject) q.set("subject", params.subject);
    if (params.to) q.set("to", params.to);
    if (params.cc) q.set("cc", params.cc);
    if (params.bcc) q.set("bcc", params.bcc);
    if (params.participant) q.set("participant", params.participant);
    if (params.priority) q.set("priority", String(params.priority));
    if (params.body) q.set("body", "true");
    if (params.header) q.set("header", "true");
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    if (params.sort) q.set("sort", params.sort);
    if (params.group) q.set("group", params.group);
    if (params.cursor) q.set("cursor", params.cursor);
    const fetchOpts = {};
    if (signal) fetchOpts.signal = signal;
    return request("GET", `/email/messages?${q}`, null, fetchOpts);
  },

  getMessage: (uuid) => request("GET", `/email/messages/${uuid}`),

  listSignatures: () => request("GET", "/email/signatures"),

  updateSignature: (uuid, data) => request("PATCH", `/email/signatures/${uuid}`, data),

  deleteSignature: (uuid) => request("DELETE", `/email/signatures/${uuid}`),

  send: (data) => request("POST", "/email/send", data),

  markRead: (uuid, read = true) =>
    request("PATCH", `/email/messages/${uuid}/read`, { read }),

  trash: (uuid) => request("POST", `/email/messages/${uuid}/trash`),

  listAttachments: (uuid) => request("GET", `/email/messages/${uuid}/attachments`),

  downloadAttachment: (attUuid) => {
    window.open(`/api/v1/email/attachments/${attUuid}/download`, "_blank");
  },

  batchDelete: (uuids) => request("POST", "/email/messages/batch-delete", { uuids }),
  batchDeleteHard: (uuids) => request("POST", "/email/messages/batch-delete-hard", { uuids }),

  clearTrash: () => request("POST", "/email/trash/clear"),

  batchMove: (uuids, destinationFolder) =>
    request("POST", "/email/messages/batch-move", { uuids, destination_folder: destinationFolder }),

  listBlocks: () => request("GET", "/email/blocks"),

  updateBlock: (uuid, data) => request("PATCH", `/email/blocks/${uuid}`, data),

  deleteBlock: (uuid) => request("DELETE", `/email/blocks/${uuid}`),

  listFolders: () => request("GET", "/email/folders"),

  createFolder: (accountEmail, folderName) =>
    request("POST", `/email/folders?account_email=${encodeURIComponent(accountEmail)}&folder_name=${encodeURIComponent(folderName)}`),

  renameFolder: (accountEmail, oldName, newName) =>
    request("PATCH", `/email/folders/${encodeURIComponent(oldName)}?account_email=${encodeURIComponent(accountEmail)}&new_name=${encodeURIComponent(newName)}`),

  deleteFolder: (accountEmail, folderName) =>
    request("DELETE", `/email/folders/${encodeURIComponent(folderName)}?account_email=${encodeURIComponent(accountEmail)}`),
};

// ── Calendar API ──────────────────────────────────────────────────────

export const calendar = {
  listCalendars: () => request("GET", "/calendar/calendars"),

  createCalendar: (data) => request("POST", "/calendar/calendars", data),

  updateCalendar: (uuid, data) => request("PATCH", `/calendar/calendars/${uuid}`, data),

  deleteCalendar: (uuid) => request("DELETE", `/calendar/calendars/${uuid}`),

  sync: (uuid) => request("POST", `/calendar/sync/${uuid}`, null, { retry: true }),

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

  updateEvent: (uuid, data) => request("PATCH", `/calendar/events/${uuid}`, data),

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
    if (params.tree) q.set("tree", "true");
    if (params.query) q.set("query", params.query);
    if (params.tags) q.set("tags", params.tags);
    if (params.sort) q.set("sort", params.sort);
    return request("GET", `/todo/todos?${q}`);
  },

  searchTitles: (q) => request("GET", `/todo/todos/search-titles?q=${encodeURIComponent(q)}`),

  create: (data) => request("POST", "/todo/todos", data),

  get: (uuid) => request("GET", `/todo/todos/${uuid}`),

  update: (uuid, data) => request("PATCH", `/todo/todos/${uuid}`, data),

  markDone: (uuid) => request("POST", `/todo/todos/${uuid}/done`),

  delete: (uuid) => request("DELETE", `/todo/todos/${uuid}`),

  addDependency: (uuid, dependsOn) =>
    request("POST", `/todo/todos/${uuid}/dependencies`, { depends_on: dependsOn }),

  removeDependency: (uuid, depUuid) =>
    request("DELETE", `/todo/todos/${uuid}/dependencies/${depUuid}`),

  getDependencies: (uuid) => request("GET", `/todo/todos/${uuid}/dependencies`),

  addAttachment: (uuid, data) =>
    request("POST", `/todo/todos/${uuid}/attachments`, data),

  removeAttachment: (uuid, attUuid) =>
    request("DELETE", `/todo/todos/${uuid}/attachments/${attUuid}`),

  listTemplates: () => request("GET", "/todo/templates"),

  getTemplate: (name) => request("GET", `/todo/templates/${encodeURIComponent(name)}`),

  createTemplate: (data) => request("POST", "/todo/templates", data),

  updateTemplate: (name, data) =>
    request("PATCH", `/todo/templates/${encodeURIComponent(name)}`, data),

  deleteTemplate: (name) => request("DELETE", `/todo/templates/${encodeURIComponent(name)}`),
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

// ── Sieve API (scripts by name, accounts by email) ───────────────────────

export const sieve = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.account_email) q.set("account_email", params.account_email);
    const qs = q.toString();
    return request("GET", `/email/sieve/scripts${qs ? `?${qs}` : ""}`);
  },

  get: (name, accountEmail) => {
    const q = accountEmail ? `?account_email=${encodeURIComponent(accountEmail)}` : "";
    return request("GET", `/email/sieve/scripts/${encodeURIComponent(name)}${q}`);
  },

  create: (data) => request("POST", "/email/sieve/scripts", data),

  update: (name, data) => request("PATCH", `/email/sieve/scripts/${encodeURIComponent(name)}`, data),

  delete: (name) => request("DELETE", `/email/sieve/scripts/${encodeURIComponent(name)}`),

  activate: (name, accountEmail, priority = 0) =>
    request("POST", `/email/sieve/scripts/${encodeURIComponent(name)}/activate`, { account_email: accountEmail, priority }),

  deactivate: (name, accountEmail) =>
    request("POST", `/email/sieve/scripts/${encodeURIComponent(name)}/deactivate`, { account_email: accountEmail }),

  setPriority: (name, accountEmail, priority) =>
    request("POST", `/email/sieve/scripts/${encodeURIComponent(name)}/priority`, { account_email: accountEmail, priority }),

  analyze: (scripts) => request("POST", "/email/sieve/analyze", { scripts }),

  validate: (content) => request("POST", "/email/sieve/validate", { content }),
};

// ── Letters API ──────────────────────────────────────────────────────

export const letters = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.direction) q.set("direction", params.direction);
    if (params.sort) q.set("sort", params.sort);
    if (params.group) q.set("group", params.group);
    if (params.limit) q.set("limit", String(params.limit));
    return request("GET", `/letters/letters?${q}`);
  },

  get: (uuid) => request("GET", `/letters/letters/${uuid}`),

  getBody: (uuid) => request("GET", `/letters/letters/${uuid}/body`),

  create: (data) => request("POST", "/letters/letters", data),

  delete: (uuid) => request("DELETE", `/letters/letters/${uuid}`),
};

// ── Admin API ─────────────────────────────────────────────────────────

export const admin = {
  health: () => request("GET", "/health"),
  syncAll: () => request("POST", "/sync/all", null, { retry: true }),
};

// ── Profiles API ──────────────────────────────────────────────────────

export const profiles = {
  list: (params = {}) => {
    const q = new URLSearchParams();
    if (params.query) q.set("query", params.query);
    if (params.limit) q.set("limit", String(params.limit));
    return request("GET", `/profiles/profiles?${q}`);
  },

  get: (uuid) => request("GET", `/profiles/profiles/${uuid}`),
};

// ── Prompt Commands API (/* prefix) ─────────────────────────────────────

export const promptCommands = {
  list: () => request("GET", "/prompt-commands/list"),

  expand: (name, args = []) =>
    request("POST", "/prompt-commands/expand", { name, args }),

  execute: (name, args = []) =>
    request("POST", "/prompt-commands/execute", { name, args }),
};

// ── Drafts API (Ctrl+S save / !{domain} draft recall) ──────────────────

export const drafts = {
  save: (domain, title, data, uuid = null) => request("POST", "/drafts", { domain, title, data, uuid }),
  list: (domain) => request("GET", `/drafts?domain=${encodeURIComponent(domain)}`),
  getAll: () => request("GET", "/drafts"),
  get: (uuid) => request("GET", `/drafts/${encodeURIComponent(uuid)}`),
  delete: (uuid) => request("DELETE", `/drafts/${encodeURIComponent(uuid)}`),
};

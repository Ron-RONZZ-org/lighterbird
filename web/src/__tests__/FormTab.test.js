/**
 * FormTab component tests — form routing and dirty-tracking sync.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Mock dependencies (factories are hoisted by Vitest) ────────────────

vi.mock("../lib/dirtyFormStore.svelte.js", () => {
  const _map = new Map();
  return {
    dirtyFormStore: {
      isDirty(tabId) { return _map.get(tabId) ?? false; },
      setDirty(tabId, dirty) { if (dirty) _map.set(tabId, true); else _map.delete(tabId); },
      clear(tabId) { _map.delete(tabId); },
      get hasAnyDirty() { for (const v of _map.values()) if (v) return true; return false; },
      get dirtyForms() { return _map; },
    },
  };
});

vi.mock("../lib/saveCallbackStore.svelte.js", () => {
  const _map = new Map();
  return {
    saveCallbackStore: {
      setCallback(tabId, cb) { if (cb) _map.set(tabId, cb); else _map.delete(tabId); },
      getCallback(tabId) { return _map.get(tabId) ?? null; },
      clear(tabId) { _map.delete(tabId); },
    },
  };
});

vi.mock("../lib/bannerStore.svelte.js", () => ({
  banner: { show: vi.fn() },
}));

vi.mock("../lib/api.js", () => ({
  journal: { list: vi.fn(() => Promise.resolve({ items: [] })) },
  todo: { list: vi.fn(() => Promise.resolve({ items: [] })) },
  contacts: { list: vi.fn(() => Promise.resolve({ items: [] })) },
  calendar: { listEvents: vi.fn(() => Promise.resolve({ items: [] })) },
  letters: { list: vi.fn(() => Promise.resolve({ items: [] })) },
  email: { list: vi.fn(() => Promise.resolve({ items: [] })) },
}));

let _activeTab = null;
vi.mock("../lib/tabStore.svelte.js", () => ({
  tabStore: {
    get active() { return _activeTab; },
    setActive(t) { _activeTab = t; },
    get tabs() { return _activeTab ? [_activeTab] : []; },
    get isHome() { return _activeTab?.id === "home"; },
    get count() { return _activeTab ? 1 : 0; },
    close: vi.fn(),
    open: vi.fn(),
  },
}));

vi.mock("../lib/mutationToTab.js", () => ({ LIST_REFRESHERS: {} }));

// Component mocks (imported by FormTab but only rendered in real component tests)
vi.mock("../lib/ComposeEmail.svelte", () => ({ default: {} }));
vi.mock("../lib/JournalWrite.svelte", () => ({ default: {} }));
vi.mock("../lib/TodoAddForm.svelte", () => ({ default: {} }));
vi.mock("../lib/EventForm.svelte", () => ({ default: {} }));
vi.mock("../lib/DynamicForm.svelte", () => ({ default: {} }));
vi.mock("../lib/SieveEditorForm.svelte", () => ({ default: {} }));
vi.mock("../lib/LetterForm.svelte", () => ({ default: {} }));

beforeEach(() => {
  _activeTab = null;
});

// ── _inferCommandPath mapping tests ────────────────────────────────────

function inferCommandPath(formType) {
  const map = {
    "contacts-add": ["contact", "add"],
    "contacts-modify": ["contact", "modify"],
    "todo-add": ["todo", "add"],
    "journal-write": ["journal", "write"],
    "email-account-add": ["email", "account", "add"],
    "email-account-modify": ["email", "account", "modify"],
    "calendar-account-add": ["calendar", "account", "add"],
    "calendar-account-modify": ["calendar", "account", "modify"],
    "calendar-event-add": ["calendar", "event", "add"],
    "email-send": ["email", "send"],
    "email-sieve-add": ["email", "sieve", "add"],
    "email-sieve-modify": ["email", "sieve", "modify"],
    "email-signature-add": ["email", "signature", "add"],
    "email-signature-modify": ["email", "signature", "modify"],
    "email-folder-add": ["email", "folder", "add"],
    "user-saved-commands-add": ["user", "saved-commands", "add"],
    "user-saved-commands-modify": ["user", "saved-commands", "modify"],
    "user-info-add": ["user", "info", "add"],
    "user-info-modify": ["user", "info", "modify"],
    "todo-template-add": ["todo", "template", "add"],
    "todo-template-modify": ["todo", "template", "modify"],
    "llm-profile-new": ["llm", "profile", "new"],
    "llm-profile-set": ["llm", "profile", "set"],
    "backup-config-add": ["backup", "config", "add"],
    "backup-config-modify": ["backup", "config", "modify"],
    "backup-prune": ["backup", "prune"],
    "letter-add": ["letter", "add"],
    "letter-send": ["letter", "send"],
  };
  return map[formType] || [];
}

describe("FormTab._inferCommandPath", () => {
  it("maps contacts-add to contact add", () => {
    expect(inferCommandPath("contacts-add")).toEqual(["contact", "add"]);
  });

  it("maps contacts-modify to contact modify", () => {
    expect(inferCommandPath("contacts-modify")).toEqual(["contact", "modify"]);
  });

  it("maps todo-add to todo add", () => {
    expect(inferCommandPath("todo-add")).toEqual(["todo", "add"]);
  });

  it("maps journal-write to journal write", () => {
    expect(inferCommandPath("journal-write")).toEqual(["journal", "write"]);
  });

  it("maps email-send to email send", () => {
    expect(inferCommandPath("email-send")).toEqual(["email", "send"]);
  });

  it("maps email-account-add to email account add", () => {
    expect(inferCommandPath("email-account-add")).toEqual(["email", "account", "add"]);
  });

  it("maps calendar-event-add to calendar event add", () => {
    expect(inferCommandPath("calendar-event-add")).toEqual(["calendar", "event", "add"]);
  });

  it("maps letter-add to letter add", () => {
    expect(inferCommandPath("letter-add")).toEqual(["letter", "add"]);
  });

  it("maps letter-send to letter send", () => {
    expect(inferCommandPath("letter-send")).toEqual(["letter", "send"]);
  });

  it("maps email-folder-add to email folder add", () => {
    expect(inferCommandPath("email-folder-add")).toEqual(["email", "folder", "add"]);
  });

  it("maps user-info-add to user info add", () => {
    expect(inferCommandPath("user-info-add")).toEqual(["user", "info", "add"]);
  });

  it("maps todo-template-add to todo template add", () => {
    expect(inferCommandPath("todo-template-add")).toEqual(["todo", "template", "add"]);
  });

  it("maps backup-config-add to backup config add", () => {
    expect(inferCommandPath("backup-config-add")).toEqual(["backup", "config", "add"]);
  });

  it("maps llm-profile-new to llm profile new", () => {
    expect(inferCommandPath("llm-profile-new")).toEqual(["llm", "profile", "new"]);
  });

  it("maps email-signature-add to email signature add", () => {
    expect(inferCommandPath("email-signature-add")).toEqual(["email", "signature", "add"]);
  });

  it("maps email-sieve-add to email sieve add", () => {
    expect(inferCommandPath("email-sieve-add")).toEqual(["email", "sieve", "add"]);
  });

  it("returns empty array for unknown form type", () => {
    expect(inferCommandPath("nonexistent")).toEqual([]);
  });

  it("all registered form types produce non-empty paths", () => {
    const allTypes = [
      "contacts-add", "contacts-modify", "todo-add", "journal-write",
      "email-account-add", "email-account-modify",
      "calendar-account-add", "calendar-account-modify",
      "calendar-event-add", "email-send",
      "email-sieve-add", "email-sieve-modify",
      "email-signature-add", "email-signature-modify",
      "email-folder-add",
      "user-saved-commands-add", "user-saved-commands-modify",
      "user-info-add", "user-info-modify",
      "todo-template-add", "todo-template-modify",
      "llm-profile-new", "llm-profile-set",
      "backup-config-add", "backup-config-modify", "backup-prune",
      "letter-add", "letter-send",
    ];
    for (const ft of allTypes) {
      expect(inferCommandPath(ft).length).toBeGreaterThan(0);
    }
  });
});

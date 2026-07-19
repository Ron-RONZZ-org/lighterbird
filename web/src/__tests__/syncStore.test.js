/**
 * syncStore tests — reactive sync state store for the email sync status.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { flushSync } from "svelte";

// Must be mocked BEFORE any import of syncStore
vi.mock("../lib/api.js", () => ({
  email: {
    getSyncStatus: vi.fn(),
  },
}));

async function loadStore() {
  // Dynamic import so the mock is in place before module evaluation
  const mod = await import("../lib/syncStore.svelte.js");
  return mod;
}

describe("syncStore", () => {
  let store;
  let mockGetSyncStatus;

  beforeEach(async () => {
    vi.useFakeTimers();
    mockGetSyncStatus = (await import("../lib/api.js")).email.getSyncStatus;
    mockGetSyncStatus.mockReset();
    store = await loadStore();
    // Reset module-level state by re-importing
    vi.resetModules();
    store = await loadStore();
  });

  afterEach(() => {
    store.stopPolling();
    vi.useRealTimers();
  });

  // ── Initial state ────────────────────────────────────────────────────

  it("initialises startupComplete to true (optimistic default)", () => {
    expect(store.syncState.startupComplete).toBe(true);
  });

  it("initialises accounts to empty array", () => {
    expect(store.syncState.accounts).toEqual([]);
  });

  it("initialises isStartupRunning to false", () => {
    expect(store.syncState.isStartupRunning).toBe(false);
  });

  it("returns empty summary when no accounts", () => {
    expect(store.syncState.summary).toBe("");
  });

  it("returns 'offline' statusClass initially (no accounts, optimistic startupComplete)", () => {
    // Initial state: startupComplete=true but no accounts → no idle → offline
    expect(store.syncState.statusClass).toBe("offline");
  });

  // ── State transitions ───────────────────────────────────────────────

  it("updates startupComplete from _fetchStatus response", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: false,
      accounts: [{ account_email: "a@b.com", status: "startup-syncing" }],
    });

    // Manually trigger fetch (like startPolling does on first call)
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    // flush Svelte reactive updates
    flushSync();

    expect(store.syncState.startupComplete).toBe(false);
    expect(store.syncState.accounts).toHaveLength(1);
    expect(store.syncState.isStartupRunning).toBe(true);
  });

  it("detects startup-complete transition via _fetchStatus", async () => {
    // First poll: startup not complete
    mockGetSyncStatus.mockResolvedValueOnce({
      startup_complete: false,
      accounts: [{ account_email: "a@b.com", status: "startup-syncing" }],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();
    expect(store.syncState.startupComplete).toBe(false);

    // Second poll: startup complete
    mockGetSyncStatus.mockResolvedValueOnce({
      startup_complete: true,
      accounts: [{ account_email: "a@b.com", status: "idle", idle_alive: true }],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.startupComplete).toBe(true);
    expect(store.syncState.isStartupRunning).toBe(false);
  });

  it("keeps startupComplete true when API call fails", async () => {
    mockGetSyncStatus.mockRejectedValue(new Error("Network error"));
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    // Initial true should be preserved (silent error handling)
    expect(store.syncState.startupComplete).toBe(true);
    expect(store.syncState.accounts).toEqual([]);
  });

  // ── Summary text ────────────────────────────────────────────────────

  it("summary shows syncing count", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: false,
      accounts: [
        { account_email: "a@b.com", status: "startup-syncing" },
        { account_email: "c@d.com", status: "idle", idle_alive: true },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.summary).toContain("Syncing");
    expect(store.syncState.summary).toContain("1 account");
  });

  it("summary shows idle when all accounts idle", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "idle", idle_alive: true },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.summary).toContain("Live");
  });

  it("summary shows partial idle when mixed", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "idle", idle_alive: true },
        { account_email: "c@d.com", status: "disabled", idle_alive: false },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.summary).toContain("1 live");
    expect(store.syncState.summary).toContain("1 offline");
  });

  it("summary shows errors when present", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "error", last_error: "Conn failed" },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.summary).toContain("1 account with sync errors");
  });

  it("summary shows offline when all disabled", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "disabled", idle_alive: false },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();

    expect(store.syncState.summary).toContain("Offline (no IDLE)");
  });

  // ── Status class ────────────────────────────────────────────────────

  it("statusClass is 'syncing' when startup not complete", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: false,
      accounts: [{ account_email: "a@b.com", status: "startup-syncing" }],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();
    expect(store.syncState.statusClass).toBe("syncing");
  });

  it("statusClass is 'error' when any account errored", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "error" },
        { account_email: "c@d.com", status: "idle", idle_alive: true },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();
    expect(store.syncState.statusClass).toBe("error");
  });

  it("statusClass is 'idle' when at least one account idle", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "idle", idle_alive: true },
        { account_email: "c@d.com", status: "disabled", idle_alive: false },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();
    expect(store.syncState.statusClass).toBe("idle");
  });

  it("statusClass is 'offline' when no accounts idle", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [
        { account_email: "a@b.com", status: "disabled", idle_alive: false },
      ],
    });
    store.refreshSyncStatus();
    await vi.runAllTimersAsync();
    flushSync();
    expect(store.syncState.statusClass).toBe("offline");
  });

  // ── Polling lifecycle ───────────────────────────────────────────────

  it("startPolling calls _fetchStatus immediately and starts interval", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [],
    });

    store.startPolling();
    // First fetch should have been called
    expect(mockGetSyncStatus).toHaveBeenCalledTimes(1);

    // Advance past the poll interval
    await vi.advanceTimersByTimeAsync(10000);
    expect(mockGetSyncStatus).toHaveBeenCalledTimes(2);

    store.stopPolling();
  });

  it("stopPolling clears the interval", async () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [],
    });

    store.startPolling();
    store.stopPolling();

    const callsBefore = mockGetSyncStatus.mock.calls.length;
    await vi.advanceTimersByTimeAsync(20000);
    // No new calls after stopping
    expect(mockGetSyncStatus.mock.calls.length).toBe(callsBefore);
  });

  it("startPolling is idempotent", () => {
    mockGetSyncStatus.mockResolvedValue({
      startup_complete: true,
      accounts: [],
    });

    store.startPolling();
    store.startPolling(); // second call should be no-op
    store.startPolling(); // third call should be no-op

    expect(mockGetSyncStatus).toHaveBeenCalledTimes(1);
    store.stopPolling();
  });
});

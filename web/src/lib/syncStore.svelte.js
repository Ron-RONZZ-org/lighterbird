/**
 * syncStore.svelte.js — Reactive sync state store.
 *
 * Polls GET /api/v1/email/sync/status and provides reactive state
 * about per-account sync status and whether the startup sync is
 * complete.
 *
 * Usage:
 *   import { syncState, startPolling, stopPolling } from "./syncStore.svelte.js";
 *   $effect(() => {
 *     if (syncState.startupComplete) { ... }
 *   });
 */

import { email as emailApi } from "./api.js";

/** @type {{ startupComplete: boolean, accounts: Array, _pollTimer: any }} */
let _state = $state({
  startupComplete: true,
  accounts: [],
});

let _pollTimer = null;
let _pollInterval = 10000; // 10 seconds

/**
 * Poll the sync status endpoint once and update the reactive store.
 */
async function _fetchStatus() {
  try {
    const data = await emailApi.getSyncStatus();
    if (data) {
      _state.startupComplete = data.startup_complete;
      _state.accounts = data.accounts || [];
    }
  } catch {
    // Silently ignore — server may not be ready yet
  }
}

/**
 * Start polling the sync status endpoint.
 * Call on mount of a component that needs sync state.
 */
export function startPolling() {
  if (_pollTimer) return;
  // Immediate first fetch
  _fetchStatus();
  _pollTimer = setInterval(_fetchStatus, _pollInterval);
}

/**
 * Stop polling the sync status endpoint.
 * Call on unmount of the polling component.
 */
export function stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

/**
 * Force a refresh of the sync status immediately.
 */
export function refreshSyncStatus() {
  _fetchStatus();
}

/**
 * Reactive sync state — consumed via $state binding.
 */
export const syncState = {
  get startupComplete() { return _state.startupComplete; },
  get accounts() { return _state.accounts; },

  /**
   * Check if any account is still in startup-syncing state.
   */
  get isStartupRunning() {
    return !_state.startupComplete;
  },

  /**
   * Get the status summary string for display.
   */
  get summary() {
    if (_state.accounts.length === 0) return "";

    const syncing = _state.accounts.filter((a) => a.status === "startup-syncing" || a.status === "syncing");
    const errored = _state.accounts.filter((a) => a.status === "error");
    const idle = _state.accounts.filter((a) => a.status === "idle" && a.idle_alive);
    const disabled = _state.accounts.filter((a) => a.status === "disabled");

    if (syncing.length > 0) {
      return `⟳ Syncing ${syncing.length} account${syncing.length > 1 ? "s" : ""}…`;
    }
    if (errored.length > 0) {
      return `⚠ ${errored.length} account${errored.length > 1 ? "s" : ""} with sync errors`;
    }
    if (idle.length > 0 && idle.length === _state.accounts.length) {
      return "✓ Live";
    }
    if (idle.length > 0) {
      return `✓ ${idle.length} live, ${disabled.length} offline`;
    }
    if (disabled.length === _state.accounts.length) {
      return "⟳ Offline (no IDLE)";
    }
    return "";
  },

  /**
   * Get a CSS class for the status bar based on overall health.
   */
  get statusClass() {
    if (!_state.startupComplete) return "syncing";
    const errored = _state.accounts.filter((a) => a.status === "error");
    if (errored.length > 0) return "error";
    const idle = _state.accounts.filter((a) => a.idle_alive);
    if (idle.length > 0) return "idle";
    return "offline";
  },
};

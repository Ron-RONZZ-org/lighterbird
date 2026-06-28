/**
 * Email config store — localStorage-backed persistence for email list view state.
 *
 * Two layers:
 *   1. ``lastConfig`` (hidden) — auto-saved on every change (500ms debounce),
 *      restored at tab open. Provides "show last view" behavior.
 *   2. User configs (visible) — explicitly saved/activated/managed snapshots.
 *
 * CLI flags and GUI toggles both write to lastConfig. Named configs are
 * only modified by explicit "Save" / "Activate" actions.
 *
 * Usage:
 *   ```js
 *   let config = createEmailConfigStore();
 *   // Apply saved config defaults, merge with CLI flags
 *   let filters = config.mergeWithCliFlags(cliFlags);
 *   // User changes sort in dropdown
 *   config.autoSave({ sort: "oldest" });
 *   // User saves current view as named config
 *   config.saveAs("Work");
 *   // User activates a saved config
 *   config.activate("Home");
 *   ```
 */

const LS_LAST = "lighterbird:email:lastConfig";
const LS_USER = "lighterbird:email:userConfigs";

const DEFAULT_CONFIG = {
  version: 1,
  folderVisibility: {},   // { "account/folder": true/false }
  expandedFolders: [],    // ["account", "account/folder"]
  sort: "newest",         // "newest" | "oldest" | "sender"
  groupByConversation: false,
};

function loadFromStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { ...fallback };
    const parsed = JSON.parse(raw);
    // Merge with defaults to handle schema evolution
    return { ...fallback, ...parsed };
  } catch {
    return { ...fallback };
  }
}

function saveToStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch { /* localStorage full or unavailable — best-effort */ }
}

/**
 * Create a reactive email config store.
 * Returns plain functions (not Svelte $state) so it works outside .svelte files.
 */
export function createEmailConfigStore() {
  let _lastConfig = loadFromStorage(LS_LAST, DEFAULT_CONFIG);
  let _userConfigs = loadFromStorage(LS_USER, {});
  let _activeConfigName = null; // name of the currently activated user config
  let _saveTimer = null;

  function getLastConfig() {
    return { ..._lastConfig };
  }

  function getUserConfigs() {
    return { ..._userConfigs };
  }

  function getActiveConfigName() {
    return _activeConfigName;
  }

  /** Auto-save view changes to lastConfig (debounced 500ms). */
  function autoSave(updates) {
    _lastConfig = { ..._lastConfig, ...updates };
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => {
      saveToStorage(LS_LAST, _lastConfig);
    }, 500);
  }

  /** Save current lastConfig as a named user config. */
  function saveAs(name) {
    const trimmed = name.trim();
    if (!trimmed) return;
    _userConfigs = { ..._userConfigs, [trimmed]: { ..._lastConfig } };
    saveToStorage(LS_USER, _userConfigs);
  }

  /** Delete a named user config. */
  function remove(name) {
    const next = { ..._userConfigs };
    delete next[name];
    _userConfigs = next;
    saveToStorage(LS_USER, _userConfigs);
    if (_activeConfigName === name) {
      _activeConfigName = null;
    }
  }

  /** Activate a named config — replaces lastConfig with its state. */
  function activate(name) {
    const cfg = _userConfigs[name];
    if (!cfg) return;
    _lastConfig = { ...cfg };
    _activeConfigName = name;
    // Persist the activated state as lastConfig immediately
    saveToStorage(LS_LAST, _lastConfig);
  }

  /** Deactivate — stop tracking active config (lastConfig remains). */
  function deactivate() {
    _activeConfigName = null;
  }

  /**
   * Merge CLI flags into lastConfig to produce effective filters.
   * CLI flags always win over lastConfig defaults.
   * This does NOT modify lastConfig — CLI overrides are ephemeral.
   */
  function mergeWithCliFlags(cliFlags) {
    const merged = { ..._lastConfig };

    // CLI --folder overrides folderVisibility
    if (cliFlags.folder) {
      merged.folderVisibility = { [cliFlags.folder]: true };
    }

    // CLI --sort overrides sort
    if (cliFlags.sort) {
      merged.sort = cliFlags.sort;
    }

    // CLI --group overrides groupByConversation
    if (cliFlags.group === "conversation") {
      merged.groupByConversation = true;
    } else if (cliFlags.group === "") {
      // Explicitly no group
    }

    // CLI --limit
    if (cliFlags.limit) {
      merged.limit = parseInt(cliFlags.limit, 10);
    }

    return merged;
  }

  /** Flush pending auto-save immediately (call on tab close). */
  function flush() {
    if (_saveTimer) {
      clearTimeout(_saveTimer);
      _saveTimer = null;
    }
    saveToStorage(LS_LAST, _lastConfig);
  }

  return {
    getLastConfig,
    getUserConfigs,
    getActiveConfigName,
    autoSave,
    saveAs,
    remove,
    activate,
    deactivate,
    mergeWithCliFlags,
    flush,
  };
}

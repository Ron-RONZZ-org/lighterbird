/** Reactive popup state and data cache — delegates to tabStore for display.
 *
 *  Kept for backward compatibility so existing code (App.svelte, CommandBar)
 *  continues to work. New code should use ``tabStore`` directly.
 */

import { tabStore } from "./tabStore.svelte.js";

let _dataCache = $state({
  accounts: [],
  calendars: [],
  contacts: [],
  todos: [],
  journal: [],
});
let _persistentDataType = $state(null);

function _cacheData(data) {
  if (!data) return;
  const update = {};
  if (data.accounts) update.accounts = data.accounts;
  if (data.calendars) update.calendars = data.calendars;
  if (data.contacts) update.contacts = data.contacts;
  if (data.todos) update.todos = data.todos;
  if (data.entries) update.journal = data.entries;
  if (Object.keys(update).length > 0) {
    _dataCache = {
      accounts: update.accounts ?? _dataCache.accounts,
      calendars: update.calendars ?? _dataCache.calendars,
      contacts: update.contacts ?? _dataCache.contacts,
      todos: update.todos ?? _dataCache.todos,
      journal: update.journal ?? _dataCache.journal,
    };
  }
}

/** Close all loading tabs currently open. */
function _closeLoadingTabs() {
  // Collect first, then close (avoid mutation during iteration)
  const ids = tabStore.tabs.filter((t) => t.type === "loading").map((t) => t.id);
  for (const id of ids) {
    tabStore.close(id);
  }
}

export const popup = {
  get current() {
    return tabStore.active;
  },

  get persistentDataType() {
    return _persistentDataType;
  },

  /** Show a transient popup (opens a new tab). */
  show(type, title, data) {
    // Close any stale loading tabs before showing the real result
    _closeLoadingTabs();
    tabStore.open(type, title, data, {
      idKey: type === "email" ? `email-${data?.uuid}` : null,
    });
    _persistentDataType = null;
    _cacheData(data);
  },

  /** Show a persistent live-view tab. */
  showPersistent(type, title, data, dataType) {
    _closeLoadingTabs();
    tabStore.open(type, title, data, { idKey: `persistent-${dataType}` });
    _persistentDataType = dataType;
    _cacheData(data);
  },

  /** Replace the data in the active tab without closing it. */
  updatePersistent(data) {
    const active = tabStore.active;
    if (active) {
      tabStore.update(active.id, data);
    }
    _cacheData(data);
  },

  showLoading(title) {
    // Always append a new loading tab (never replaces existing tabs)
    tabStore.open("loading", title, null, { closable: false });
  },

  close() {
    if (tabStore.active && tabStore.active.closable) {
      tabStore.close(tabStore.active.id);
    }
    _persistentDataType = null;
  },

  get cache() {
    return _dataCache;
  },

  updateCache(data) {
    if (!data) return;
    _dataCache = {
      accounts: data.accounts ?? _dataCache.accounts,
      calendars: data.calendars ?? _dataCache.calendars,
      contacts: data.contacts ?? _dataCache.contacts,
      todos: data.todos ?? _dataCache.todos,
      journal: data.journal ?? _dataCache.journal,
    };
  },
};

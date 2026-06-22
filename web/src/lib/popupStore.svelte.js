/** Reactive popup state and data cache — module-level $state. */

let _current = $state(null);
let _dataCache = $state({ accounts: [], calendars: [] });
/** When non-null, the popup shows a live view of this data type and persists
 *  across commands. Set by list commands, cleared on manual close. */
let _persistentDataType = $state(null);

function _cacheData(data) {
  if (!data) return;
  const update = {};
  if (data.accounts) update.accounts = data.accounts;
  if (data.calendars) update.calendars = data.calendars;
  if (Object.keys(update).length > 0) {
    _dataCache = {
      accounts: update.accounts ?? _dataCache.accounts,
      calendars: update.calendars ?? _dataCache.calendars,
    };
  }
}

export const popup = {
  get current() {
    return _current;
  },

  get persistentDataType() {
    return _persistentDataType;
  },

  /** Show a transient popup (replaces any current popup, clears persistence). */
  show(type, title, data) {
    _current = { type, title, data, isLoading: false };
    _persistentDataType = null;
    _cacheData(data);
  },

  /** Show a persistent live-view popup that stays across commands.
   *
   *  ``dataType`` identifies the kind of data shown ("accounts", "calendars").
   *  Mutation commands affecting this type will auto-refresh it. */
  showPersistent(type, title, data, dataType) {
    _current = { type, title, data, isLoading: false };
    _persistentDataType = dataType;
    _cacheData(data);
  },

  /** Replace the data in the current popup without clearing persistence. */
  updatePersistent(data) {
    if (!_current) return;
    _current = { ..._current, data };
    _cacheData(data);
  },

  showLoading(title) {
    _current = { type: "loading", title, data: null, isLoading: true };
  },

  close() {
    _current = null;
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
    };
  },
};

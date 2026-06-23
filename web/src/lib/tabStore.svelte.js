/** Reactive tab store — manages multiple open tabs. */

let _tabs = $state([]);
let _activeId = $state(null);
let _nextId = 1;

function genId() {
  return `tab-${_nextId++}-${Date.now()}`;
}

export const tabStore = {
  get tabs() {
    return _tabs;
  },

  get active() {
    return _tabs.find((t) => t.id === _activeId) || null;
  },

  get activeIndex() {
    return _tabs.findIndex((t) => t.id === _activeId);
  },

  get count() {
    return _tabs.length;
  },

  /**
   * Open a new tab (or activate an existing one if same idKey is provided).
   *
   * @param {"status"|"email"|"events"|"error"|"help"|"loading"} type
   * @param {string} title
   * @param {any} data
   * @param {object} [opts]
   * @param {string} [opts.idKey]  — if a tab with this idKey exists, activate it instead of creating new
   * @param {boolean} [opts.closable=true]
   * @param {boolean} [opts.replaceable=false] — if true, replaces the active tab instead of appending
   */
  open(type, title, data, opts = {}) {
    const { idKey, closable = true, replaceable = false } = opts;

    // If idKey is provided, find existing tab with same idKey
    if (idKey) {
      const existing = _tabs.find((t) => t.idKey === idKey);
      if (existing) {
        _activeId = existing.id;
        // Update data
        _tabs = _tabs.map((t) => (t.id === existing.id ? { ...t, title, data } : t));
        return existing.id;
      }
    }

    let newTabs;
    const tab = { id: genId(), type, title, data, idKey: idKey || null, closable };

    if (replaceable && _tabs.length > 0) {
      // Replace active tab
      const idx = _tabs.findIndex((t) => t.id === _activeId);
      newTabs = [..._tabs];
      newTabs[idx] = tab;
    } else {
      newTabs = [..._tabs, tab];
    }

    _tabs = newTabs;
    _activeId = tab.id;
    return tab.id;
  },

  close(id) {
    if (_tabs.length === 0) return;
    const idx = _tabs.findIndex((t) => t.id === id);
    if (idx === -1) return;

    const newTabs = _tabs.filter((t) => t.id !== id);
    _tabs = newTabs;

    // If we removed the active tab, activate the nearest one
    if (id === _activeId) {
      if (newTabs.length === 0) {
        _activeId = null;
      } else if (idx >= newTabs.length) {
        _activeId = newTabs[newTabs.length - 1].id;
      } else {
        _activeId = newTabs[idx].id;
      }
    }
  },

  setActive(id) {
    const exists = _tabs.find((t) => t.id === id);
    if (exists) _activeId = id;
  },

  /**
   * Activate tab at a 0-based index.
   */
  setActiveIndex(index) {
    if (index >= 0 && index < _tabs.length) {
      _activeId = _tabs[index].id;
    }
  },

  /**
   * Update data for a tab.
   */
  update(id, data, title) {
    _tabs = _tabs.map((t) =>
      t.id === id ? { ...t, data, ...(title !== undefined ? { title } : {}) } : t,
    );
  },

  closeAll() {
    _tabs = [];
    _activeId = null;
  },
};

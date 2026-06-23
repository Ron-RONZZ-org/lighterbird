/** Reactive tab store — manages multiple open tabs, with pinned home tab. */

let _tabs = $state([]);
let _activeId = $state(null);
let _nextId = 1;

const HOME_TAB = {
  id: "home",
  type: "home",
  title: "Home",
  data: null,
  idKey: "home",
  closable: false,
  pinned: true,
};

function genId() {
  return `tab-${_nextId++}-${Date.now()}`;
}

/** Ensure the home tab exists at index 0. */
function ensureHome() {
  if (_tabs.length === 0 || _tabs[0].id !== HOME_TAB.id) {
    _tabs = [HOME_TAB, ..._tabs.filter((t) => t.id !== HOME_TAB.id)];
  }
  if (!_activeId) {
    _activeId = HOME_TAB.id;
  }
}

export const tabStore = {
  get tabs() {
    ensureHome();
    return _tabs;
  },

  get active() {
    ensureHome();
    return _tabs.find((t) => t.id === _activeId) || HOME_TAB;
  },

  get activeIndex() {
    ensureHome();
    return _tabs.findIndex((t) => t.id === _activeId);
  },

  get count() {
    ensureHome();
    return _tabs.length;
  },

  /**
   * Open a new result tab.
   *
   * @param {"status"|"email"|"events"|"error"|"help"|"loading"|"chat"} type
   * @param {string} title
   * @param {any} data
   * @param {object} [opts]
   * @param {string} [opts.idKey] — dedup key
   * @param {boolean} [opts.closable=true]
   */
  open(type, title, data, opts = {}) {
    ensureHome();
    const { idKey, closable = true } = opts;

    // Dedup by idKey
    if (idKey) {
      const existing = _tabs.find((t) => t.idKey === idKey && t.id !== HOME_TAB.id);
      if (existing) {
        _activeId = existing.id;
        _tabs = _tabs.map((t) => (t.id === existing.id ? { ...t, title, data } : t));
        return existing.id;
      }
    }

    const tab = {
      id: genId(),
      type,
      title,
      data,
      idKey: idKey || null,
      closable,
      pinned: false,
    };

    _tabs = [..._tabs, tab];
    _activeId = tab.id;
    return tab.id;
  },

  close(id) {
    if (id === HOME_TAB.id) return; // home tab never closes
    ensureHome();
    const idx = _tabs.findIndex((t) => t.id === id);
    if (idx === -1) return;

    const newTabs = _tabs.filter((t) => t.id !== id);
    _tabs = newTabs;

    if (id === _activeId) {
      // Activate the nearest tab, preferring home (index 0)
      _activeId = newTabs.length > 0 ? newTabs[Math.min(idx, newTabs.length - 1)].id : HOME_TAB.id;
    }
  },

  setActive(id) {
    ensureHome();
    if (_tabs.find((t) => t.id === id)) _activeId = id;
  },

  setActiveIndex(index) {
    ensureHome();
    if (index >= 0 && index < _tabs.length) {
      _activeId = _tabs[index].id;
    }
  },

  update(id, data, title) {
    _tabs = _tabs.map((t) =>
      t.id === id ? { ...t, data, ...(title !== undefined ? { title } : {}) } : t,
    );
  },

  closeAll() {
    _tabs = [HOME_TAB];
    _activeId = HOME_TAB.id;
  },

  goHome() {
    _activeId = HOME_TAB.id;
  },

  /** @returns {boolean} true if the home tab is currently active */
  get isHome() {
    return _activeId === HOME_TAB.id;
  },
};

/**
 * Reactive store tracking which open form tabs have unsaved changes.
 *
 * Each form component calls setDirty(tabId, bool) when its state changes.
 * TabView checks before closing, App.svelte checks for beforeunload.
 */

let _dirtyForms = $state(new Map());

export const dirtyFormStore = {
  get dirtyForms() {
    return _dirtyForms;
  },

  /** Check if a specific tab has unsaved changes. */
  isDirty(tabId) {
    return _dirtyForms.get(tabId) ?? false;
  },

  /** Update dirty state for a tab. */
  setDirty(tabId, dirty) {
    const next = new Map(_dirtyForms);
    if (dirty) {
      next.set(tabId, true);
    } else {
      next.delete(tabId);
    }
    _dirtyForms = next;
  },

  /** Clear dirty state (on submit/destroy). */
  clear(tabId) {
    const next = new Map(_dirtyForms);
    next.delete(tabId);
    _dirtyForms = next;
  },

  /** Check if ANY form tab has unsaved changes. */
  get hasAnyDirty() {
    for (const v of _dirtyForms.values()) {
      if (v) return true;
    }
    return false;
  },
};

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
    if (dirty) {
      _dirtyForms.set(tabId, true);
    } else {
      _dirtyForms.delete(tabId);
    }
    // Reassign to trigger Svelte 5 reactivity tracking
    _dirtyForms = _dirtyForms;
  },

  /** Clear dirty state (on submit/destroy). */
  clear(tabId) {
    _dirtyForms.delete(tabId);
    _dirtyForms = _dirtyForms;
  },

  /** Check if ANY form tab has unsaved changes. */
  get hasAnyDirty() {
    for (const v of _dirtyForms.values()) {
      if (v) return true;
    }
    return false;
  },
};

/**
 * Create a per-instance form guard that auto-wires dirty state to the global store.
 *
 * Forms can use this instead of manual `onDirtyChange` prop wiring.
 *
 * Usage:
 * ```js
 *   let guard = createFormGuard(tabId);
 *   let dirty = $derived(…);
 *   $effect(() => { guard.setDirty(dirty); });
 * ```
 *
 * @param {string} tabId - Unique tab identifier
 * @returns {{ dirty: boolean, setDirty: (v: boolean) => void, clear: () => void }}
 */
export function createFormGuard(tabId) {
  let dirty = $state(false);

  return {
    get dirty() {
      return dirty;
    },
    setDirty(v) {
      dirty = v;
      if (tabId) dirtyFormStore.setDirty(tabId, v);
    },
    clear() {
      dirty = false;
      if (tabId) dirtyFormStore.clear(tabId);
    },
  };
}

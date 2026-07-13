/**
 * saveCallbackStore — maps tab IDs to optional save-draft callbacks.
 *
 * Used by TabView's UnsavedChangesDialog: when the user picks "Save Draft",
 * TabView looks up the callback registered by the form component (ComposeEmail,
 * LetterForm) and calls it.
 *
 * This is a separate store from dirtyFormStore because the save-callback
 * concept is lighterbird-specific (not in lightercore's shared store).
 */

/** @type {Map<string, () => void>} */
let _callbacks = $state(new Map());

export const saveCallbackStore = {
  /** Register a save callback for tabId (pass null to unregister). */
  setCallback(tabId, cb) {
    const next = new Map(_callbacks);
    if (cb) next.set(tabId, cb);
    else next.delete(tabId);
    _callbacks = next;
  },

  /** Get the callback for tabId, or null. */
  getCallback(tabId) {
    return _callbacks.get(tabId) ?? null;
  },

  /** Clear all callbacks (on destroy). */
  clear(tabId) {
    const next = new Map(_callbacks);
    next.delete(tabId);
    _callbacks = next;
  },
};

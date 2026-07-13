/**
 * saveCallbackStore — maps tab IDs to optional save callbacks.
 *
 * Used by TabView's UnsavedChangesDialog: when the user picks "Save",
 * TabView looks up the callback registered by the form component and calls it.
 *
 * The callback is async and returns a boolean:
 *   true  → close the tab after saving
 *   false → don't close (validation failed, form shows error)
 *
 * Draft forms (ComposeEmail, LetterForm) register a callback that saves
 * the draft and returns true (close after save).
 *
 * Non-draft forms register via FormTab: the callback triggers form submit,
 * and FormTab.handleFormSubmit closes the tab on success. If validation
 * fails, the callback returns false so the tab stays open with the error.
 */

/** @type {Map<string, () => Promise<boolean>>} */
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

/**
 * Popup store — re-exported from @lightercore/ui with app-specific init.
 *
 * The shared ``popup`` provides show/showPersistent/showLoading/close/
 * updateCache.  Cache keys are set dynamically by updateCache; lighterbird
 * uses: accounts, calendars, contacts, todos, journal, events, folders,
 * letters, profiles.
 */
export { popup } from "@lightercore/ui/popupStore.svelte.js";

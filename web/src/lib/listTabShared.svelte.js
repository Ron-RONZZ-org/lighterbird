/**
 * Shared helpers for list tab components (EmailListTab, JournalListTab,
 * ContactsListTab, TodoListTab, CalendarEventsListTab, SieveListTab).
 *
 * Each factory returns reactive state + handlers using Svelte 5 runes.
 * Call from the component's <script> to get local reactive state.
 */

import { registerShortcuts } from "./keyboardShortcuts.svelte.js";

// Standard list tab shortcuts (from AGENTS.md List Tab Standard Feature Set)
registerShortcuts("list-tab-standard", [
  { key: "v", desc: "Toggle selection mode", category: "List" },
  { key: "n", desc: "New item", category: "List" },
  { key: "Delete", desc: "Delete selected items", category: "List" },
  { key: "/", desc: "Toggle search/filter bar", category: "List" },
  { key: "↑/↓", desc: "Navigate rows", category: "List" },
  { key: "PgUp/PgDn", desc: "Page up/down", category: "List" },
  { key: "Home/End", desc: "First/last row", category: "List" },
  { key: "Space", desc: "Toggle focused item", category: "List" },
  { key: "Shift+click", desc: "Range select", category: "List" },
  { key: "Esc", desc: "Exit selection mode", category: "List" },
]);

/**
 * Clipboard copy state for any key (UUID, email address, etc.).
 * Shows `copiedKey` for 1.2s then clears.
 *
 * @returns {{ readonly copiedKey: string, copyToClipboard: (key: string) => void }}
 */
export function createCopyState() {
  let copiedKey = $state("");

  function copyToClipboard(key) {
    navigator.clipboard.writeText(key).then(() => {
      copiedKey = key;
      setTimeout(() => {
        if (copiedKey === key) copiedKey = "";
      }, 1200);
    }).catch(() => {});
  }

  return {
    get copiedKey() { return copiedKey; },
    copyToClipboard,
  };
}

/**
 * Selection + keyboard navigation manager for list tabs.
 *
 * All list tabs share this same interaction model:
 * - `V` key toggles selection mode
 * - `N` key opens the "+ New" form (view mode)
 * - Arrow keys navigate focused row
 * - Shift+click / Shift+arrows range-selects
 * - Space toggles focused item
 * - Delete triggers batch delete
 * - Escape exits selection mode
 *
 * @param {() => Array<{uuid?: string, name?: string}>} getItems
 *   Function returning the current items array (called reactively).
 * @param {(key: string) => void} onOpen
 *   Called when user activates an item in view mode (Enter, click).
 * @param {(keys: string[]) => Promise<void>} onDeleteSelected
 *   Called with selected keys when batch delete is confirmed.
 * @param {() => Promise<void>} onRefresh
 *   Called after batch delete to refresh the list.
 * @param {object} [opts]
 * @param {(e: KeyboardEvent) => boolean} [opts.onBeforeKeydown]
 *   Optional hook to intercept keydown (e.g. when search open).
 *   Return true to prevent default handling.
 * @param {() => void} [opts.onNew]
 *   Called when user presses `N` in view mode to open "+ New" form.
 */
export function createSelectionManager(getItems, onOpen, onDeleteSelected, onRefresh, opts = {}) {
  let selectionMode = $state(false);
  let selectedKeys = $state(new Set());
  let focusedIndex = $state(-1);
  let anchorIndex = $state(-1);
  let confirmDelete = $state(false);

  let numSelected = $derived(selectedKeys.size);

  /** Get the key (uuid or name) for an item at index i. */
  function getKey(i) {
    const item = getItems()[i];
    return item ? (item.uuid ?? item.name) : null;
  }

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedKeys = new Set();
      focusedIndex = -1;
      anchorIndex = -1;
    } else if (getItems().length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleItem(key) {
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    selectedKeys = next;
  }

  function isSelected(key) {
    return selectedKeys.has(key);
  }

  function selectRange(from, to) {
    const items = getItems();
    const start = Math.min(from, to);
    const end = Math.max(from, to);
    const next = new Set(selectedKeys);
    for (let i = start; i <= end; i++) {
      const key = getKey(i);
      if (key) next.add(key);
    }
    selectedKeys = next;
  }

  function handleRowClick(e, key) {
    if (selectionMode) {
      if (e.shiftKey && anchorIndex >= 0) {
        const idx = getItems().findIndex((it) => (it.uuid ?? it.name) === key);
        if (idx >= 0) {
          selectRange(anchorIndex, idx);
          anchorIndex = idx;
        }
      } else {
        toggleItem(key);
        const idx = getItems().findIndex((it) => (it.uuid ?? it.name) === key);
        if (idx >= 0 && anchorIndex < 0) anchorIndex = idx;
      }
    } else if (onOpen) {
      onOpen(key);
    }
  }

  async function deleteSelected() {
    const keys = [...selectedKeys];
    if (keys.length === 0) return;
    try {
      if (onDeleteSelected) await onDeleteSelected(keys);
      selectedKeys = new Set();
      selectionMode = false;
      if (onRefresh) await onRefresh();
    } catch (err) {
      // Error handling deferred to the caller's catch
    }
  }

  function focusRow(index) {
    const items = getItems();
    if (index < 0) index = 0;
    if (index >= items.length) index = items.length - 1;
    focusedIndex = index;
    const key = getKey(index);
    if (key) {
      const el = document.getElementById(`row-${CSS.escape(key)}`);
      if (el) el.scrollIntoView({ block: "nearest" });
    }
  }

  /**
   * Standard keyboard handler for selection-mode navigation.
   * Returns true if the key was handled.
   */
  function handleKeydown(e) {
    // Let the component handle other key combos first if needed
    if (opts.onBeforeKeydown) {
      if (opts.onBeforeKeydown(e)) return;
    }

    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    // When confirm dialog is open, only let it handle Enter/Escape
    if (confirmDelete) {
      if (e.key === "Escape") { confirmDelete = false; e.preventDefault(); }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;

    switch (e.key) {
      case "v":
        if (plain) { toggleSelectionMode(); e.preventDefault(); }
        return;
      case "Escape":
        if (selectionMode) { toggleSelectionMode(); e.preventDefault(); }
        return;
      case "n":
        if (plain && !selectionMode && opts.onNew) {
          opts.onNew();
          e.preventDefault();
        }
        return;
    }

    if (!selectionMode) return;

    const shift = e.shiftKey;

    function navRow(idx) {
      if (shift && anchorIndex >= 0) selectRange(anchorIndex, idx);
      focusRow(idx);
      if (!shift) anchorIndex = idx;
    }

    const items = getItems();
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (focusedIndex < items.length - 1) navRow(focusedIndex + 1);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (focusedIndex > 0) navRow(focusedIndex - 1);
        return;
      case "PageDown":
        e.preventDefault();
        navRow(Math.min(focusedIndex + Math.max(1, Math.floor(items.length / 5)), items.length - 1));
        return;
      case "PageUp":
        e.preventDefault();
        navRow(Math.max(focusedIndex - Math.max(1, Math.floor(items.length / 5)), 0));
        return;
      case "Home":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, 0);
        focusRow(0);
        if (!shift) anchorIndex = 0;
        return;
      case "End":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, items.length - 1);
        focusRow(items.length - 1);
        if (!shift) anchorIndex = items.length - 1;
        return;
      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < items.length) {
          const key = getKey(focusedIndex);
          if (key) toggleItem(key);
          if (anchorIndex < 0) anchorIndex = focusedIndex;
        }
        return;
      case "Delete":
        e.preventDefault();
        if (numSelected > 0) confirmDelete = true;
        return;
    }
  }

  return {
    get selectionMode() { return selectionMode; },
    set selectionMode(v) { selectionMode = v; },
    get selectedKeys() { return selectedKeys; },
    get focusedIndex() { return focusedIndex; },
    get numSelected() { return numSelected; },
    get confirmDelete() { return confirmDelete; },
    set confirmDelete(v) { confirmDelete = v; },

    toggleSelectionMode,
    toggleItem,
    isSelected,
    handleRowClick,
    deleteSelected,
    focusRow,
    handleKeydown,
  };
}

/**
 * Format an ISO date string for display in a list.
 * - Today: shows time only
 * - This year: shows month + day
 * - Older: shows full date
 */
export function formatListItemDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 10);
    const now = new Date();
    const opts = d.toDateString() === now.toDateString()
      ? { hour: "2-digit", minute: "2-digit" }
      : d.getFullYear() === now.getFullYear()
        ? { month: "short", day: "numeric" }
        : { year: "numeric", month: "short", day: "numeric" };
    return d.toLocaleDateString([], opts);
  } catch {
    return iso.slice(0, 10);
  }
}

/**
 * Focus trap for modal dialogs.
 * Wraps Tab/Shift+Tab within the container's focusable elements.
 *
 * @param {() => HTMLElement} getContainer — callback returning the dialog root
 * @param {(e: KeyboardEvent) => void} [onKeydown] — optional extra handler
 * @returns {(e: KeyboardEvent) => void} keydown handler to mount on the overlay
 */
export function createDialogTrap(getContainer, onKeydown) {
  const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  return function trapKeydown(e) {
    if (e.key === "Tab") {
      const container = getContainer();
      if (!container) return;
      const focusable = container.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    if (onKeydown) onKeydown(e);
  };
}

/**
 * Truncate a string with ellipsis if it exceeds max length.
 */
export function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

/**
 * Sanitize a filename to only alphanumeric characters plus - and _.
 * Falls back to "export" if the result would be empty.
 *
 * @param {string} name — base name (without extension)
 * @param {string} [extension] — file extension including dot, e.g. ".md"
 * @param {number} [maxLen=64] — max length of the base part
 * @returns {string} sanitized filename with extension
 */
export function sanitizeFilename(name, extension = "", maxLen = 64) {
  if (!name) return `export${extension}`;
  const base = name.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, maxLen);
  return `${base || "export"}${extension}`;
}

/**
 * Preview text: first line, stripped of markdown, truncated.
 */
export function preview(s, max = 60) {
  if (!s) return "";
  const firstLine = s.split("\n")[0].trim();
  return truncate(firstLine.replace(/[#*_~`>]/g, ""), max);
}

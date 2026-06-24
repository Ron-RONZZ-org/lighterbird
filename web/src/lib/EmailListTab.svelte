<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import EmailListToolbar from "./EmailListToolbar.svelte";
  import MoveDialog from "./MoveDialog.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";

  let { data = {} } = $props();
  let messages = $derived(data?.messages || []);
  let total = $derived(data?.total || 0);

  // ── Selection state ──────────────────────────────────────────────────
  let selectionMode = $state(false);
  let selectedUuids = $state(new Set());
  let focusedIndex = $state(-1);
  let anchorIndex = $state(-1);

  // ── Dialog state ─────────────────────────────────────────────────────
  let showMoveDialog = $state(false);
  let showShortcutHelp = $state(false);
  let confirmDelete = $state(false);

  let numSelected = $derived(selectedUuids.size);

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedUuids = new Set();
      focusedIndex = -1;
      anchorIndex = -1;
    } else if (messages.length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleMessage(uuid) {
    const next = new Set(selectedUuids);
    if (next.has(uuid)) {
      next.delete(uuid);
    } else {
      next.add(uuid);
    }
    selectedUuids = next;
  }

  function isSelected(uuid) {
    return selectedUuids.has(uuid);
  }

  function selectRange(from, to) {
    const start = Math.min(from, to);
    const end = Math.max(from, to);
    const next = new Set(selectedUuids);
    for (let i = start; i <= end; i++) {
      next.add(messages[i].uuid);
    }
    selectedUuids = next;
  }

  // ── Row interaction ─────────────────────────────────────────────────

  function handleRowClick(e, msg) {
    if (selectionMode) {
      toggleMessage(msg.uuid);
    } else {
      openMessage(msg.uuid);
    }
  }

  async function openMessage(uuid) {
    if (!uuid) return;
    try {
      const msg = await emailApi.getMessage(uuid);
      tabStore.open("email", msg.subject || "(no subject)", msg, {
        idKey: `email-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load message" });
    }
  }

  function openMessageInNewTab(e, uuid) {
    if (!uuid) return;
    e.preventDefault();
    window.open(`/api/v1/email/messages/${uuid}/view`, "_blank");
  }

  // ── Batch actions ───────────────────────────────────────────────────

  async function deleteSelected() {
    const uuids = [...selectedUuids];
    if (uuids.length === 0) return;
    try {
      await emailApi.batchDelete(uuids);
      // Re-fetch messages after delete
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", {
        message: err.message || "Failed to delete messages",
      });
    }
  }

  async function handleMoveConfirmed(destinationFolderUuid) {
    const uuids = [...selectedUuids];
    if (uuids.length === 0) return;
    try {
      await emailApi.batchMove(uuids, destinationFolderUuid);
      showMoveDialog = false;
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Move Failed", {
        message: err.message || "Failed to move messages",
      });
    }
  }

  async function refreshList() {
    try {
      const result = await emailApi.listMessages({ limit: 50 });
      tabStore.update(tabStore.active.id, result);
      selectedUuids = new Set();
    } catch {
      // Silent — let user retry
    }
  }

  // ── Keyboard navigation ─────────────────────────────────────────────

  function focusRow(index) {
    if (index < 0) index = 0;
    if (index >= messages.length) index = messages.length - 1;
    focusedIndex = index;
    // Scroll row into view
    const el = document.getElementById(`email-row-${messages[index]?.uuid}`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }

  function handleKeydown(e) {
    // Don't intercept when user is typing in an input
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    // ── Global shortcuts (always available) ──────────────────────────
    switch (e.key) {
      case "v":
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
          toggleSelectionMode();
          e.preventDefault();
        }
        return;
      case "h":
        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
          showShortcutHelp = !showShortcutHelp;
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showMoveDialog) { showMoveDialog = false; e.preventDefault(); return; }
        if (showShortcutHelp) { showShortcutHelp = false; e.preventDefault(); return; }
        if (confirmDelete) { confirmDelete = false; e.preventDefault(); return; }
        if (selectionMode) { toggleSelectionMode(); e.preventDefault(); return; }
        return;
    }

    // ── Selection-mode shortcuts ────────────────────────────────────
    if (!selectionMode) return;

    // Range select with Shift
    const shift = e.shiftKey;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (focusedIndex < messages.length - 1) {
          const next = focusedIndex + 1;
          if (shift && anchorIndex >= 0) {
            // Extend range
            selectRange(anchorIndex, next);
          }
          focusRow(next);
          if (!shift) anchorIndex = next;
        }
        return;

      case "ArrowUp":
        e.preventDefault();
        if (focusedIndex > 0) {
          const prev = focusedIndex - 1;
          if (shift && anchorIndex >= 0) {
            selectRange(anchorIndex, prev);
          }
          focusRow(prev);
          if (!shift) anchorIndex = prev;
        }
        return;

      case "PageDown":
        e.preventDefault();
        {
          const step = Math.max(1, Math.floor(messages.length / 5));
          const next = Math.min(focusedIndex + step, messages.length - 1);
          if (shift && anchorIndex >= 0) selectRange(anchorIndex, next);
          focusRow(next);
          if (!shift) anchorIndex = next;
        }
        return;

      case "PageUp":
        e.preventDefault();
        {
          const step = Math.max(1, Math.floor(messages.length / 5));
          const prev = Math.max(focusedIndex - step, 0);
          if (shift && anchorIndex >= 0) selectRange(anchorIndex, prev);
          focusRow(prev);
          if (!shift) anchorIndex = prev;
        }
        return;

      case "Home":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, 0);
        focusRow(0);
        if (!shift) anchorIndex = 0;
        return;

      case "End":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, messages.length - 1);
        focusRow(messages.length - 1);
        if (!shift) anchorIndex = messages.length - 1;
        return;

      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < messages.length) {
          toggleMessage(messages[focusedIndex].uuid);
          // Also set anchor if first selection
          if (anchorIndex < 0) anchorIndex = focusedIndex;
        }
        return;

      case "Delete":
        e.preventDefault();
        if (numSelected > 0) {
          confirmDelete = true;
        }
        return;
    }

    // Ctrl+M / Cmd+M — open move dialog
    if ((e.ctrlKey || e.metaKey) && e.key === "m") {
      e.preventDefault();
      if (numSelected > 0) {
        showMoveDialog = true;
      }
      return;
    }
  }

  // ── Format helpers ──────────────────────────────────────────────────

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso.slice(0, 10);
      const now = new Date();
      const isToday = d.toDateString() === now.toDateString();
      if (isToday) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const thisYear = d.getFullYear() === now.getFullYear();
      if (thisYear) return d.toLocaleDateString([], { month: "short", day: "numeric" });
      return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
    } catch {
      return iso.slice(0, 10);
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="email-list">
  <!-- Toolbar -->
  <EmailListToolbar
    {selectionMode}
    {numSelected}
    onToggleMode={toggleSelectionMode}
    onDelete={() => { if (numSelected > 0) confirmDelete = true; }}
    onMove={() => { if (numSelected > 0) showMoveDialog = true; }}
  />

  <!-- Message list -->
  <div class="list" role="listbox" aria-label="Email messages" aria-multiselectable="true">
    {#each messages as msg, i (msg.uuid)}
      <div
        id="email-row-{msg.uuid}"
        class="row"
        class:selected={isSelected(msg.uuid)}
        class:focused={i === focusedIndex}
        class:selection-mode={selectionMode}
        role="option"
        aria-selected={isSelected(msg.uuid)}
        tabindex={selectionMode ? (i === focusedIndex ? 0 : -1) : 0}
        onclick={(e) => {
          if (e.ctrlKey || e.metaKey || e.button === 1) {
            openMessageInNewTab(e, msg.uuid);
          } else {
            handleRowClick(e, msg);
          }
        }}
        onmouseenter={() => { if (selectionMode && focusedIndex !== i) {} }}
      >
        <!-- Checkbox (selection mode only, reserved space always) -->
        <span class="checkbox-cell">
          {#if selectionMode}
            <span class="checkbox" class:checked={isSelected(msg.uuid)}>
              {isSelected(msg.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <!-- Message data -->
        <span class="from" class:unread={!msg.is_read}>{truncate(msg.from || "", 24)}</span>
        <span class="subject" class:unread={!msg.is_read}>{truncate(msg.subject || "(no subject)", 40)}</span>
        <span class="date">{formatDate(msg.received_at)}</span>
      </div>
    {:else}
      <p class="empty">No messages.</p>
    {/each}
  </div>

  {#if confirmDelete}
    <ConfirmDialog
      message="Delete {numSelected} message{numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { confirmDelete = false; await deleteSelected(); }}
      onDismiss={() => { confirmDelete = false; }}
    />
  {/if}

  <!-- Move dialog -->
  {#if showMoveDialog}
    <MoveDialog
      onConfirm={(destUuid) => handleMoveConfirmed(destUuid)}
      onDismiss={() => { showMoveDialog = false; }}
    />
  {/if}

  <!-- Keyboard shortcut help overlay -->
  {#if showShortcutHelp}
    <KeyboardShortcutOverlay onDismiss={() => { showShortcutHelp = false; }} />
  {/if}
</div>

<style>
  .email-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    position: relative;
  }

  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    transition: background 0.08s;
    min-height: 2rem;
  }
  .row:hover {
    background: #2a2a44;
  }
  .row.focused {
    background: #2a2a50;
    outline: 1px solid #5a5a8a;
    outline-offset: -1px;
  }
  .row.selected {
    background: #2a2a50;
  }
  .row.selection-mode {
    cursor: pointer;
  }

  /* Checkbox cell — always reserved to avoid layout shift */
  .checkbox-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.8rem;
    flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    height: 1.1rem;
    border: 1.5px solid #7c7c9a;
    border-radius: 3px;
    font-size: 0.7rem;
    color: #e0e0e0;
    background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked {
    background: #4a6fa5;
    border-color: #4a6fa5;
  }

  .from {
    color: #e0e0e0;
    min-width: 10rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .from.unread {
    font-weight: 700;
  }
  .subject {
    color: #ccc;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subject.unread {
    font-weight: 600;
    color: #e0e0e0;
  }
  .date {
    color: #5a5a7a;
    min-width: 6rem;
    text-align: right;
    flex-shrink: 0;
    font-size: 0.78rem;
  }

  .empty {
    color: #5a5a7a;
    text-align: center;
    padding: 2rem;
  }
</style>

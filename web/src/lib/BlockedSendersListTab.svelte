<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";

  let { data = {} } = $props();
  let blocks = $derived(data?.blocks || []);
  let total = $derived(data?.total || 0);
  let highlight = $derived(data?.highlight || "");

  let selectionMode = $state(false);
  let selectedUuids = $state(new Set());
  let focusedIndex = $state(-1);

  let confirmDelete = $state(false);
  let deleteSingleUuid = $state("");  // UUID for single-item delete (not batch)
  let editTarget = $state(null);      // block being edited
  let editNote = $state("");

  let copiedUuid = $state("");
  let highlightActive = $state(false);

  let numSelected = $derived(selectedUuids.size);

  // Highlight animation — auto-clears after 2s
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  function copyUuid(uuid) {
    navigator.clipboard.writeText(uuid).then(() => {
      copiedUuid = uuid;
      setTimeout(() => { if (copiedUuid === uuid) copiedUuid = ""; }, 1200);
    }).catch(() => {});
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }

  function preview(s, max) {
    if (!s) return "";
    return s.split("\n")[0].slice(0, max - 1) + (s.length > max ? "…" : "");
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const sameYear = d.getFullYear() === now.getFullYear();
    if (sameYear) {
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  // ── Global keyboard handler ──────────────────────────────────────────
  function handleGlobalKeydown(e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;
    if (e.key === "Escape") {
      if (selectionMode) { toggleSelectionMode(); e.preventDefault(); return; }
      if (editTarget) { editTarget = null; e.preventDefault(); return; }
      tabStore.close(tabStore.active?.id);
      return;
    }
    if (e.key === "v" || e.key === "V") {
      if (!e.ctrlKey && !e.metaKey) { toggleSelectionMode(); e.preventDefault(); }
    }
    if (e.key === "n" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (!selectionMode && !editTarget) { addNew(); e.preventDefault(); }
    }
    if ((e.key === "Delete" || e.key === "Backspace") && selectionMode && numSelected > 0) {
      e.preventDefault();
      confirmDelete = true;
    }
  }
  $effect(() => {
    emailApi.listBlocks().catch(() => {});
  });

  // ── Selection ────────────────────────────────────────────────────────
  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedUuids = new Set();
      focusedIndex = -1;
    } else if (blocks.length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleBlock(uuid) {
    const next = new Set(selectedUuids);
    if (next.has(uuid)) next.delete(uuid);
    else next.add(uuid);
    selectedUuids = next;
  }

  function isSelected(uuid) {
    return selectedUuids.has(uuid);
  }

  // ── Commands ─────────────────────────────────────────────────────────
  function addNew() {
    // Open the interactive command form via command dispatch
    tabStore.open("status", "Add Block", {
      _trigger: "!email block add",
    });
  }

  function startEdit(block) {
    editTarget = block;
    editNote = block.note || "";
  }

  async function saveEdit() {
    if (!editTarget) return;
    try {
      await emailApi.updateBlock(editTarget.uuid, { note: editNote });
      editTarget = null;
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Update Failed", { message: err.message || "Failed to update block" });
    }
  }

  function cancelEdit() {
    editTarget = null;
  }

  async function deleteBlock(uuid) {
    try {
      await emailApi.deleteBlock(uuid);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete block" });
    }
  }

  function startDelete(uuid) {
    deleteSingleUuid = uuid;
    confirmDelete = true;
  }

  async function deleteSelected() {
    let uuids;
    if (deleteSingleUuid) {
      uuids = [deleteSingleUuid];
    } else {
      uuids = [...selectedUuids];
    }
    if (uuids.length === 0) return;
    try {
      for (const uuid of uuids) {
        await emailApi.deleteBlock(uuid);
      }
      deleteSingleUuid = "";
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete blocks" });
    }
  }

  async function refreshList() {
    const tabId = tabStore.findByKey("persistent-block-list") || tabStore.active?.id;
    if (!tabId) return;
    try {
      const result = await emailApi.listBlocks();
      tabStore.safeUpdate(tabId, result);
      selectedUuids = new Set();
    } catch { /* silent */ }
  }

  function handleRowClick(uuid) {
    if (selectionMode) {
      toggleBlock(uuid);
    }
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<div class="block-list">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="left">
      <button class="btn" onclick={addNew} title="Add new block">+ New Block <kbd>N</kbd></button>
      <button class="btn" onclick={toggleSelectionMode} title="Toggle multi-select mode">
        {selectionMode ? "Exit" : "Select"}
      </button>
      {#if selectionMode && numSelected > 0}
        <button class="btn danger" onclick={deleteSelected}>Unblock ({numSelected})</button>
      {/if}
      <button class="btn" onclick={refreshList} title="Refresh list">⟳</button>
    </div>
    <div class="right">
      <span class="count">{total} block{total !== 1 ? "s" : ""}</span>
    </div>
  </div>

  <!-- Block list -->
  <div class="list" role="listbox" aria-label="Blocked senders">
    {#each blocks as block, i (block.uuid)}
      {#if editTarget && editTarget.uuid === block.uuid}
        <!-- Inline edit row -->
        <div class="row edit-row">
          <span class="badge {block.type}">{block.type}</span>
          <span class="pattern">{block.pattern}</span>
          <!-- svelte-ignore a11y_autofocus -->
          <input
            class="edit-input"
            type="text"
            bind:value={editNote}
            placeholder="Reason for blocking…"
            onkeydown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") cancelEdit(); }}
            autofocus
          />
          <span class="actions">
            <button class="btn small" onclick={saveEdit} title="Save note">Save</button>
            <button class="btn small" onclick={cancelEdit} title="Cancel">Cancel</button>
          </span>
        </div>
      {:else}
        <div
          class="row"
          class:selected={isSelected(block.uuid)}
          class:highlight={block.uuid === highlight && highlightActive}
          class:selection-mode={selectionMode}
          role="option"
          aria-selected={isSelected(block.uuid)}
          tabindex={selectionMode ? (i === focusedIndex ? 0 : -1) : 0}
          onclick={() => handleRowClick(block.uuid)}
          onkeydown={(e) => { if (e.key === "Enter") handleRowClick(block.uuid); }}
        >
          <span class="checkbox-cell">
            {#if selectionMode}
              <span class="checkbox" class:checked={isSelected(block.uuid)}>
                {isSelected(block.uuid) ? "✓" : ""}
              </span>
            {/if}
          </span>
          <span class="badge {block.type}">{block.type}</span>
          <span
            class="uuid"
            role="button"
            tabindex="-1"
            onclick={(e) => { e.stopPropagation(); copyUuid(block.uuid); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); copyUuid(block.uuid); } }}
            title="Click to copy UUID"
          >
            {copiedUuid === block.uuid ? "Copied!" : block.uuid.slice(0, 8)}
          </span>
          <span class="pattern">{block.pattern}</span>
          <span class="note" title={block.note || ""}>
            {block.note ? preview(block.note, 40) : ""}
          </span>
          <span class="date">{formatDate(block.created_at)}</span>
          <span class="actions">
            {#if !selectionMode}
              <button class="btn small" onclick={(e) => { e.stopPropagation(); startEdit(block); }}
                title="Edit note">✎</button>
              <button class="btn small danger" onclick={(e) => { e.stopPropagation(); deleteSingleUuid = block.uuid; confirmDelete = true; }}
                title="Remove block">✕</button>
            {/if}
          </span>
        </div>
      {/if}
    {:else}
      <p class="empty">No blocked senders. Add one with <strong>!email block add</strong>.</p>
    {/each}
  </div>
</div>

<!-- Confirm delete dialog -->
{#if confirmDelete && !editTarget}
  <ConfirmDialog
    message={deleteSingleUuid
      ? "Remove this block permanently?"
      : `Remove selected ${numSelected} blocks permanently?`}
    onConfirm={async () => { confirmDelete = false; await deleteSelected(); }}
    onDismiss={() => { confirmDelete = false; deleteSingleUuid = ""; }}
  />
{/if}

<style>
  .block-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    background: #1a1a2e;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    gap: 0.5rem;
    flex-shrink: 0;
  }
  .left, .right {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .count {
    color: var(--clr-muted);
    font-size: 0.72rem;
  }
  .btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn:hover { background: #3a3a5a; }
  .btn.danger { border-color: #8a3a3a; color: #e07070; }
  .btn.danger:hover { background: #3a2020; }
  .btn.small { padding: 0.1rem 0.3rem; font-size: 0.72rem; }
  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    min-height: 2rem;
    transition: background 0.08s;
  }
  .row:hover { background: #2a2a44; }
  .row.selected { background: #2a2a50; }
  .row.highlight { animation: highlight-fade 2s ease-out; }
  .row.selection-mode { cursor: pointer; }
  .row.edit-row { background: #1e2a3e; }
  @keyframes highlight-fade {
    0% { background: rgba(42, 90, 42, 0.6); }
    100% { background: transparent; }
  }
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
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .badge {
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .badge.sender { background: #3a2a4a; color: #c9a0e0; border: 1px solid #5a3a6a; }
  .badge.domain { background: #2a3a4a; color: #a0c0e0; border: 1px solid #3a5a6a; }
  .uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5.5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .pattern {
    flex: 1;
    color: #e0e0e0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note {
    flex: 0 0 12rem;
    color: var(--clr-muted);
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .date {
    flex-shrink: 0;
    color: var(--clr-dim);
    font-size: 0.72rem;
    min-width: 5rem;
    text-align: right;
  }
  .actions {
    display: flex;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .edit-input {
    flex: 1;
    padding: 0.2rem 0.4rem;
    border: 1px solid #4a6a8a;
    border-radius: 3px;
    background: #1a2a3e;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>

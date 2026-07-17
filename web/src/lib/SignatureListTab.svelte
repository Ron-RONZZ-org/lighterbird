<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";

  let { data = {} } = $props();
  let signatures = $derived(data?.signatures || []);
  let total = $derived(data?.total || 0);
  let highlight = $derived(data?.highlight || "");

  let selectionMode = $state(false);
  let selectedUuids = $state(new Set());
  let focusedIndex = $state(-1);

  let confirmDelete = $state(false);
  let deleteSingleUuid = $state("");
  let editTarget = $state(null);       // signature being edited
  let editName = $state("");
  let editText = $state("");
  let editFormat = $state("plain");

  let copiedUuid = $state("");
  let highlightActive = $state(false);

  let numSelected = $derived(selectedUuids.size);

  // Highlight animation
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
    if (e.key === "d" || e.key === "D") {
      if (!e.ctrlKey && !e.metaKey && !selectionMode && !editTarget) {
        openDefaults(); e.preventDefault();
      }
    }
    if (e.key === "n" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (!selectionMode && !editTarget) { addNew(); e.preventDefault(); }
    }
    if ((e.key === "Delete" || e.key === "Backspace") && selectionMode && numSelected > 0) {
      e.preventDefault();
      confirmDelete = true;
    }
  }

  // ── Selection ────────────────────────────────────────────────────────
  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedUuids = new Set();
      focusedIndex = -1;
    } else if (signatures.length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleSig(uuid) {
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
    tabStore.open("status", "New Signature", {
      _trigger: "!email signature add",
    });
  }

  function openDefaults() {
    // If a single signature is selected (or focused), pass its UUID
    const firstUuid = selectedUuids.size === 1
      ? [...selectedUuids][0]
      : (focusedIndex >= 0 ? signatures[focusedIndex]?.uuid : null);
    if (firstUuid) {
      tabStore.open("status", "Set Default Signature", {
        _trigger: `!email signature default --uuid ${firstUuid}`,
      });
    } else {
      tabStore.open("status", "Set Default Signature", {
        _trigger: "!email signature default",
      });
    }
  }

  function startEdit(sig) {
    editTarget = sig;
    editName = sig.name || "";
    editText = sig.signature_text || "";
    editFormat = sig.signature_format || "plain";
  }

  async function saveEdit() {
    if (!editTarget) return;
    try {
      await emailApi.updateSignature(editTarget.uuid, {
        name: editName || null,
        signature_text: editText || null,
        signature_format: editFormat,
      });
      editTarget = null;
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Update Failed", { message: err.message || "Failed to update signature" });
    }
  }

  function cancelEdit() {
    editTarget = null;
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
        await emailApi.deleteSignature(uuid);
      }
      deleteSingleUuid = "";
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete signatures" });
    }
  }

  async function refreshList() {
    const tabId = tabStore.findByKey("persistent-signature-list") || tabStore.active?.id;
    if (!tabId) return;
    try {
      const result = await emailApi.listSignatures();
      tabStore.safeUpdate(tabId, { signatures: result.signatures, total: result.signatures.length });
      selectedUuids = new Set();
    } catch { /* silent */ }
  }

  function handleRowClick(uuid) {
    if (selectionMode) {
      toggleSig(uuid);
    }
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<div class="sig-list">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="left">
      <button class="btn" onclick={addNew} title="Create new signature">+ New <kbd>N</kbd></button>
      <button class="btn" onclick={toggleSelectionMode} title="Toggle multi-select mode">
        {selectionMode ? "Exit" : "Select"}
      </button>
      {#if selectionMode && numSelected > 0}
        <button class="btn danger" onclick={deleteSelected}>Delete ({numSelected})</button>
      {/if}
      <button class="btn" onclick={openDefaults} title="Set default signature for an account">
        Defaults <kbd>D</kbd>
      </button>
      <button class="btn" onclick={refreshList} title="Refresh list">⟳</button>
    </div>
    <div class="right">
      <span class="count">{total} signature{total !== 1 ? "s" : ""}</span>
    </div>
  </div>

  <!-- Signature list -->
  <div class="list" role="listbox" aria-label="Email signatures">
    {#each signatures as sig, i (sig.uuid)}
      {#if editTarget && editTarget.uuid === sig.uuid}
        <!-- Inline edit row -->
        <div class="row edit-row">
          <div class="edit-fields">
            <label class="edit-label">
              Name
              <input class="edit-input" type="text" bind:value={editName} placeholder="Signature name" />
            </label>
            <label class="edit-label">
              Format
              <select class="edit-select" bind:value={editFormat}>
                <option value="plain">Plain</option>
                <option value="html">HTML</option>
                <option value="markdown">Markdown</option>
              </select>
            </label>
            <label class="edit-label textarea-label">
              Text
              <textarea class="edit-textarea" bind:value={editText} placeholder="Signature text" rows="3"></textarea>
            </label>
          </div>
          <div class="edit-actions">
            <button class="btn small" onclick={saveEdit}>Save</button>
            <button class="btn small" onclick={cancelEdit}>Cancel</button>
          </div>
        </div>
      {:else}
        <div
          class="row"
          class:selected={isSelected(sig.uuid)}
          class:highlight={sig.uuid === highlight && highlightActive}
          class:selection-mode={selectionMode}
          role="option"
          aria-selected={isSelected(sig.uuid)}
          tabindex={selectionMode ? (i === focusedIndex ? 0 : -1) : 0}
          onclick={() => handleRowClick(sig.uuid)}
        >
          <span class="checkbox-cell">
            {#if selectionMode}
              <span class="checkbox" class:checked={isSelected(sig.uuid)}>
                {isSelected(sig.uuid) ? "✓" : ""}
              </span>
            {/if}
          </span>
          <span
            class="uuid"
            role="button"
            tabindex="-1"
            onclick={(e) => { e.stopPropagation(); copyUuid(sig.uuid); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); copyUuid(sig.uuid); } }}
            title="Click to copy UUID"
          >
            {copiedUuid === sig.uuid ? "Copied!" : sig.uuid.slice(0, 8)}
          </span>
          <span class="name">{truncate(sig.name, 30)}</span>
          <span class="preview">{preview(sig.signature_text, 50)}</span>
          <span class="format-badge">{sig.signature_format || "plain"}</span>
          <span class="default-for">
            {#if sig.default_for}
              {#each sig.default_for as acct}
                <span class="badge default" title="Default for {acct}">{truncate(acct, 20)}</span>
              {/each}
            {/if}
          </span>
          <span class="actions">
            {#if !selectionMode}
              <button class="btn small" onclick={(e) => { e.stopPropagation(); startEdit(sig); }}
                title="Edit signature">✎</button>
              <button class="btn small danger" onclick={(e) => { e.stopPropagation(); startDelete(sig.uuid); }}
                title="Delete signature">✕</button>
            {/if}
          </span>
        </div>
      {/if}
    {:else}
      <p class="empty">No signatures. Create one with <strong>!email signature add</strong>.</p>
    {/each}
  </div>
</div>

{#if confirmDelete}
  <ConfirmDialog
    message={deleteSingleUuid
      ? "Delete this signature permanently?"
      : `Delete selected ${numSelected} signatures permanently?`}
    onConfirm={async () => { confirmDelete = false; await deleteSelected(); }}
    onDismiss={() => { confirmDelete = false; deleteSingleUuid = ""; }}
  />
{/if}

<style>
  .sig-list {
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
  .row.edit-row { background: #1e2a3e; padding: 0.5rem; flex-direction: column; align-items: stretch; }
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
  .uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5.5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .name {
    flex: 0 0 12rem;
    color: #e0e0e0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .preview {
    flex: 1;
    color: var(--clr-muted);
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .format-badge {
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
    background: #2a2a3e;
    color: #b0b0c0;
    border: 1px solid #3a3a5a;
    flex-shrink: 0;
  }
  .default-for {
    display: flex;
    gap: 0.2rem;
    flex-shrink: 1;
    min-width: 0;
    overflow: hidden;
  }
  .badge {
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
  }
  .badge.default {
    background: #1e2a3e;
    color: #a0c0e0;
    border: 1px solid #3a5a7a;
  }
  .actions {
    display: flex;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .edit-fields {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .edit-label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.72rem;
    color: var(--clr-muted);
  }
  .edit-input {
    padding: 0.2rem 0.4rem;
    border: 1px solid #4a6a8a;
    border-radius: 3px;
    background: #1a2a3e;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .edit-select {
    padding: 0.15rem 0.3rem;
    border: 1px solid #4a6a8a;
    border-radius: 3px;
    background: #1a2a3e;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .edit-textarea {
    padding: 0.2rem 0.4rem;
    border: 1px solid #4a6a8a;
    border-radius: 3px;
    background: #1a2a3e;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
    resize: vertical;
  }
  .edit-actions {
    display: flex;
    gap: 0.3rem;
    justify-content: flex-end;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>

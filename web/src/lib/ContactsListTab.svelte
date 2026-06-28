<script>
  /** Contacts list tab — selection, batch delete, UUID/email copy, search, add. */

  import { tabStore } from "./tabStore.svelte.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    truncate,
  } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let contacts = $derived(data?.contacts || []);
  let total = $derived(data?.total || 0);

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;



  // Shared selection state
  let sel = createSelectionManager(
    () => contacts,
    (uuid) => openContact(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => contactsApi.delete(u)));
    },
    () => refreshList(),
  );

  let uuidCopy = createCopyState();
  let emailCopy = createCopyState();



  // Sync filters from tab data
  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  function handleNew() {
    tabStore.open("form", "Add Contact", { form: "contacts-add", initialData: {} }, {
      idKey: "contacts-add",
    });
  }

  async function openContact(uuid) {
    if (!uuid) return;
    try {
      const contact = await contactsApi.get(uuid);
      tabStore.open("status", contact.given_name || contact.full_name || "(unnamed)", contact, {
        idKey: `contact-${uuid}`, replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load contact" });
    }
  }

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) params.query = searchQuery;
      const result = await contactsApi.list(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
  }

  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) params.query = query;
    contactsApi.list(params)
      .then((result) => { tabStore.update(tabStore.active.id, result); })
      .catch((err) => { if (err?.name === "AbortError") return; });
  }

  function handleSearchInput(e) {
    const val = e.target.value;
    searchQuery = val;
    clearTimeout(searchTimeout);
    if (val.length === 0 || val.length >= 2) {
      searchTimeout = setTimeout(() => performSearch(val), 300);
    }
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = "";
    if (data?.query) performSearch("");
  }

  function handleWindowKeydown(e) {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    if (sel.confirmDelete) {
      if (e.key === "Escape") { sel.confirmDelete = false; e.preventDefault(); }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
    switch (e.key) {
      case "v":
        if (plain && !sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); }
        return;
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".cl-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        return;
    }
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="contacts-list">
  <!-- Toolbar -->
  <div class="toolbar" class:active={sel.selectionMode || sel.numSelected > 0}>
    {#if showSearch}
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input type="text" class="cl-search-input" placeholder="Search contacts… (min 2 chars)"
          value={searchQuery} oninput={handleSearchInput}
          onkeydown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
            if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
          }} aria-label="Search contacts" />
        {#if searchQuery}
          <button class="search-clear" onclick={() => { searchQuery = ""; performSearch(""); }} aria-label="Clear search">✕</button>
        {/if}
      </div>
    {:else if sel.selectionMode}
      <div class="left">
        <button class="tool-btn" title="Exit selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Exit <kbd>V</kbd></button>
      </div>
      <div class="center">
        {#if sel.numSelected > 0}
          <span class="count">{sel.numSelected} selected</span>
        {:else}
          <span class="count muted">Select with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="right">
        <button class="tool-btn danger" disabled={sel.numSelected === 0} title="Delete selected (Delete key)"
          onclick={() => { sel.confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Select <kbd>V</kbd></button>
      </div>
      <div class="center">
        <span class="hint"><kbd>/</kbd> search</span>
      </div>
      <div class="right">
        <button class="tool-btn primary" onclick={handleNew} title="Add new contact">+ New</button>
      </div>
    {/if}
  </div>

  <!-- Contact list -->
  <div class="list" role="listbox" aria-label="Contacts" aria-multiselectable="true">
    {#each contacts as contact, i (contact.uuid)}
      <div id="row-{contact.uuid}" class="row"
        class:selected={sel.isSelected(contact.uuid)} class:focused={i === sel.focusedIndex}
        class:selection-mode={sel.selectionMode} role="option"
        aria-selected={sel.isSelected(contact.uuid)}
        tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
        onclick={(e) => sel.handleRowClick(e, contact.uuid)}
        onkeydown={(e) => { if (e.key === "Enter") sel.handleRowClick(e, contact.uuid); }}>
        <span class="checkbox-cell">
          {#if sel.selectionMode}
            <span class="checkbox" class:checked={sel.isSelected(contact.uuid)}>
              {sel.isSelected(contact.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>
        <span class="cuuid" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(contact.uuid); }}
              title="Click to copy UUID">
          {uuidCopy.copiedKey === contact.uuid ? "Copied!" : contact.uuid.slice(0, 8)}
        </span>
        <span class="name">{truncate(contact.given_name || contact.full_name || "(unnamed)", 24)}</span>
        <span class="email" onclick={(e) => { e.stopPropagation(); emailCopy.copyToClipboard(contact.email || ""); }}
              title="Click to copy email">
          {emailCopy.copiedKey === contact.email ? "Copied!" : truncate(contact.email || "", 28)}
        </span>
        <span class="org">{truncate(contact.organization || "", 16)}</span>
      </div>
    {:else}
      <p class="empty">No contacts.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog message="Delete {sel.numSelected} contact{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }} />
  {/if}
</div>

<style>
  .contacts-list { display: flex; flex-direction: column; height: 100%; font-family: monospace; font-size: 0.85rem; position: relative; }
  .toolbar { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.5rem; background: #16162a; border-bottom: 1px solid #333; min-height: 2.2rem; flex-shrink: 0; font-family: monospace; font-size: 0.82rem; }
  .toolbar.active { background: #1a1a32; border-bottom-color: #4a4a6a; }
  .left, .right { display: flex; align-items: center; gap: 0.5rem; }
  .center { flex: 1; text-align: center; }
  .tool-btn { padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px; background: #2a2a3e; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.8rem; transition: background 0.1s; }
  .tool-btn kbd { display: inline-block; padding: 0 3px; margin-left: 2px; font-family: monospace; font-size: 0.68rem; background: #222; border: 1px solid #555; border-radius: 3px; color: #999; line-height: 1.3; }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.danger:hover:not(:disabled) { background: #6b2020; border-color: #8b3030; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }
  .hint { color: #5a5a7a; font-size: 0.72rem; }
  .hint kbd { display: inline-block; padding: 0 3px; font-family: monospace; background: #222; border: 1px solid #444; border-radius: 3px; color: #888; font-size: 0.7rem; }
  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }
  .search-bar { display: flex; align-items: center; gap: 0.4rem; flex: 1; }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .cl-search-input { flex: 1; padding: 0.3rem 0.4rem; border: 1px solid #444; border-radius: 4px; background: #12122a; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none; }
  .cl-search-input:focus { border-color: #6a6a9a; }
  .cl-search-input::placeholder { color: #555; }
  .search-clear { background: none; border: none; color: #7c7c9a; cursor: pointer; font-size: 0.8rem; padding: 0.2rem; }
  .search-clear:hover { color: #e0e0e0; }
  .list { flex: 1; overflow-y: auto; padding: 0; }
  .row { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.5rem; border-bottom: 1px solid #2a2a3e; cursor: default; transition: background 0.08s; min-height: 2rem; }
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.selection-mode { cursor: pointer; }
  .checkbox-cell { display: flex; align-items: center; justify-content: center; width: 1.8rem; flex-shrink: 0; }
  .checkbox { display: inline-flex; align-items: center; justify-content: center; width: 1.1rem; height: 1.1rem; border: 1.5px solid #7c7c9a; border-radius: 3px; font-size: 0.7rem; color: #e0e0e0; background: transparent; transition: background 0.1s, border-color 0.1s; }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .cuuid { color: var(--clr-muted); font-size: 0.72rem; min-width: 5rem; flex-shrink: 0; cursor: pointer; }
  .cuuid:hover { color: #7c7c9a; text-decoration: underline; }
  .name { color: #e0e0e0; min-width: 10rem; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .email { color: #999; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
  .email:hover { color: #ccc; text-decoration: underline; }
  .org { color: var(--clr-muted); min-width: 6rem; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.78rem; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
  /* Modal overlay */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 500; display: flex; align-items: center; justify-content: center; }
  .modal { background: #1e1e32; border: 1px solid #444; border-radius: 16px; padding: 1.5rem; width: 380px; max-width: 90vw; }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h3 { font-size: 1rem; color: #e0e0e0; font-weight: 600; }
  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-label { font-size: 0.78rem; color: #7c7c9a; font-family: monospace; }
  .text-input { background: #2a2a3e; border: 1px solid #444; border-radius: 8px; padding: 0.5rem 0.7rem; color: #e0e0e0; font-size: 0.85rem; outline: none; font-family: monospace; }
  .text-input:focus { border-color: #7c7c9a; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary { padding: 0.45rem 1rem; border-radius: 8px; border: 1px solid #444; font-family: monospace; font-size: 0.85rem; cursor: pointer; transition: background 0.1s; }
  .btn-primary { background: #3a6a3a; color: #e0e0e0; border-color: #4a8a4a; flex: 1; }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>

<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { letters as lettersApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    formatListItemDate,
    truncate,
    preview,
  } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let letters = $derived(data?.letters || []);
  let total = $derived(data?.total || 0);

  let uuidCopy = createCopyState();

  let sel = createSelectionManager(
    () => letters,
    (uuid) => openLetter(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => lettersApi.delete(u)));
    },
    () => refreshList(),
    { onNew: handleNew },
  );

  let highlight = $derived(data?.highlight || "");
  let highlightActive = $state(false);
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  async function openLetter(uuid) {
    if (!uuid) return;
    try {
      const letterData = await lettersApi.get(uuid);
      const bodyData = await lettersApi.getBody(uuid);
      tabStore.open("letter-view", letterData.object || "(untitled)", { letter: letterData, body: bodyData.body }, {
        idKey: `letter-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load letter" });
    }
  }

  async function deleteSelected() {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await Promise.all(uuids.map((uuid) => lettersApi.delete(uuid)));
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", {
        message: err.message || "Failed to delete letters",
      });
    }
  }

  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();

    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) {
      params.query = query;
    }

    lettersApi.list(params)
      .then((result) => {
        tabStore.update(tabStore.active.id, result);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
      });
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
    document.querySelector(".letter-list .list")?.focus();
  }

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const result = await lettersApi.list(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
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
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".letter-search-input")?.focus());
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

  function handleNew() {
    tabStore.open("form", "Add Letter", { form: "letter-add", initialData: {
      _returnIdKey: "persistent-letter-list",
      _returnType: "letter-list",
      _returnTitle: "Letters",
    } }, {
      idKey: "letter-add",
    });
  }

  function directionIcon(dir) {
    return dir === "sent" ? "↑" : "↓";
  }

  function senderDisplay(l) {
    if (l.sender_manual) return l.sender_manual;
    if (l.sender_profile) return l.sender_profile.slice(0, 8);
    return "—";
  }

  function recipientDisplay(l) {
    if (l.recipient_manual) return l.recipient_manual;
    if (l.recipient_contact) return l.recipient_contact.slice(0, 8);
    return "—";
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="letter-list">
  <div class="toolbar" class:active={sel.selectionMode || sel.numSelected > 0}>
    {#if showSearch}
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          class="letter-search-input"
          placeholder="Search letters… (min 2 chars)"
          value={searchQuery}
          oninput={handleSearchInput}
          onkeydown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
            if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
          }}
          aria-label="Search letters"
        />
        {#if searchQuery}
          <button class="search-clear" onclick={() => { searchQuery = ""; performSearch(""); }} aria-label="Clear search">✕</button>
        {/if}
      </div>
    {:else if sel.selectionMode}
      <div class="toolbar-left">
        <button class="tool-btn" title="Exit selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Exit <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        {#if sel.numSelected > 0}
          <span class="count">{sel.numSelected} selected</span>
        {:else}
          <span class="count muted">Select entries with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="toolbar-right">
        <button class="tool-btn danger" disabled={sel.numSelected === 0} title="Delete selected (Delete key)"
          onclick={() => { sel.confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="toolbar-left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Select <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        <span class="search-hint"><kbd>/</kbd> search</span>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn primary" onclick={handleNew} title="Add received letter">+ New <kbd>N</kbd></button>
        <button class="tool-btn primary" onclick={() => {
          tabStore.open("form", "Send Letter", { form: "letter-send", initialData: {
            _returnIdKey: "persistent-letter-list",
            _returnType: "letter-list",
            _returnTitle: "Letters",
          } }, { idKey: "letter-send" });
        }} title="Send a letter">Send <kbd>S</kbd></button>
      </div>
    {/if}
  </div>

  <div class="list" role="listbox" aria-label="Letters" aria-multiselectable="true">
    {#each letters as letter, i (letter.uuid)}
      <div
        id="row-{letter.uuid}"
        class="row"
        class:selected={sel.isSelected(letter.uuid)}
        class:focused={i === sel.focusedIndex}
        class:highlight={letter.uuid === highlight && highlightActive}
        class:selection-mode={sel.selectionMode}
        role="option"
        aria-selected={sel.isSelected(letter.uuid)}
        tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
        onclick={(e) => sel.handleRowClick(e, letter.uuid)}
        onkeydown={(e) => {
          if (e.key === "Enter") sel.handleRowClick(e, letter.uuid);
        }}
      >
        <span class="checkbox-cell">
          {#if sel.selectionMode}
            <span class="checkbox" class:checked={sel.isSelected(letter.uuid)}>
              {sel.isSelected(letter.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <span class="dir-icon" title={letter.direction}>{directionIcon(letter.direction)}</span>

        <span class="letter-uuid" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(letter.uuid); }}
              onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); uuidCopy.copyToClipboard(letter.uuid); } }}
              title="Click to copy UUID">
          {uuidCopy.copiedKey === letter.uuid ? "Copied!" : letter.uuid.slice(0, 8)}
        </span>
        <span class="date">{formatListItemDate(letter.created_at)}</span>
        <span class="object">{truncate(letter.object || "(untitled)", 28)}</span>
        <span class="sender">{truncate(senderDisplay(letter), 20)}</span>
        <span class="recipient">{truncate(recipientDisplay(letter), 20)}</span>
        {#if letter.respond_to_uuid}
          <span class="reply-badge" title="Reply to {letter.respond_to_uuid.slice(0, 8)}">↩</span>
        {/if}
      </div>
    {:else}
      <p class="empty">No letters.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} letter{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}
</div>

<style>
  .letter-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    position: relative;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.5rem;
    background: #16162a;
    border-bottom: 1px solid #333;
    min-height: 2.2rem;
    flex-shrink: 0;
    font-family: monospace;
    font-size: 0.82rem;
  }
  .toolbar.active { background: #1a1a32; border-bottom-color: #4a4a6a; }
  .toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
  .toolbar-center { flex: 1; text-align: center; }

  .tool-btn {
    padding: 0.25rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.8rem;
    transition: background 0.1s;
  }
  .tool-btn kbd {
    display: inline-block;
    padding: 0 3px;
    margin-left: 2px;
    font-family: monospace;
    font-size: 0.68rem;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    color: #999;
    line-height: 1.3;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.danger:hover:not(:disabled) { background: #6b2020; border-color: #8b3030; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }

  .search-hint { color: #5a5a7a; font-size: 0.72rem; }
  .search-hint kbd {
    display: inline-block; padding: 0 3px; font-family: monospace;
    background: #222; border: 1px solid #444; border-radius: 3px; color: #888; font-size: 0.7rem;
  }

  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }

  .search-bar {
    display: flex; align-items: center; gap: 0.4rem; flex: 1;
  }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .letter-search-input {
    flex: 1; padding: 0.3rem 0.4rem; border: 1px solid #444; border-radius: 4px;
    background: #12122a; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .letter-search-input:focus { border-color: #6a6a9a; }
  .letter-search-input::placeholder { color: #555; }
  .search-clear {
    background: none; border: none; color: #7c7c9a; cursor: pointer; font-size: 0.8rem; padding: 0.2rem;
  }
  .search-clear:hover { color: #e0e0e0; }

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
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.highlight { animation: letter-highlight-fade 2s ease-out; }
  @keyframes letter-highlight-fade {
    0% { background: rgba(42, 90, 42, 0.6); }
    100% { background: transparent; }
  }
  .row.selection-mode { cursor: pointer; }

  .checkbox-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.8rem; flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem;
    border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }

  .dir-icon {
    min-width: 1.2rem;
    text-align: center;
    font-size: 0.85rem;
    flex-shrink: 0;
    color: var(--clr-sub);
  }

  .letter-uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .letter-uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .date {
    color: var(--clr-muted);
    min-width: 6rem;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
  .object {
    color: #e0e0e0;
    min-width: 10rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sender, .recipient {
    color: #b0b0c0;
    min-width: 8rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8rem;
  }
  .reply-badge {
    color: #6a9a6a;
    font-size: 0.8rem;
    flex-shrink: 0;
  }

  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>

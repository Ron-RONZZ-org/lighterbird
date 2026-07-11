<script>
  import ListSearchBar from "./ListSearchBar.svelte";
  import SortDropdown from "./SortDropdown.svelte";
  import MultiEntryField from "./MultiEntryField.svelte";

  let {
    showSearch = false,
    searchQuery = "",
    selectionMode = false,
    numSelected = 0,
    onToggleSelectionMode = () => {},
    onSearchInput = () => {},
    onSearchEnter = () => {},
    onSearchEscape = () => {},
    onClearSearch = () => {},
    onCloseSearch = () => {},
    onNew = () => {},
    onImport = () => {},
    onSend = () => {},
    onExport = () => {},
    onDelete = () => {},
    // Sort dropdown
    currentFilters = {},
    onSortChange = () => {},
    onGroupChange = () => {},
    // Tag filter
    tagFilterEntries = [],
    onTagFilterChange = () => {},
    onClearTagFilter = () => {},
    // Internal UI state
    showSortDropdown = false,
    showTagFilter = false,
    onToggleSort = () => {},
    onToggleTagFilter = () => {},
    onCloseSort = () => {},
    onCloseTagFilter = () => {},
  } = $props();
</script>

<div class="toolbar" class:active={selectionMode || numSelected > 0}>
  {#if showSearch}
    <ListSearchBar
      {showSearch}
      {searchQuery}
      placeholder="Search letters\u2026 (min 2 chars)"
      ariaLabel="Search letters"
      onSearchInput={onSearchInput}
      {onSearchEnter}
      {onSearchEscape}
      onSearchClear={onClearSearch}
    >
      {#snippet actions()}
        <div class="toolbar-left">
          <button class="tool-btn" title="Toggle selection mode (V)" onclick={onToggleSelectionMode}>Select <kbd>V</kbd></button>
          <button class="tool-btn" title="Toggle sort (S)" onclick={onToggleSort}>Sort <kbd>S</kbd></button>
          <button class="tool-btn" title="Filter by tag (F)" onclick={onToggleTagFilter}>Tags <kbd>F</kbd></button>
        </div>
        <div class="toolbar-right">
          <button class="tool-btn primary" onclick={onNew} title="Add received letter">+ New <kbd>N</kbd></button>
          <button class="tool-btn" onclick={onImport} title="Import letters">Import</button>
          <button class="tool-btn primary" onclick={onSend} title="Send a letter">Send <kbd>S</kbd></button>
        </div>
      {/snippet}
    </ListSearchBar>
  {:else if selectionMode}
    <div class="toolbar-left">
      <button class="tool-btn" title="Exit selection mode (V)" onclick={onToggleSelectionMode}>Exit <kbd>V</kbd></button>
    </div>
    <div class="toolbar-center">
      {#if numSelected > 0}
        <span class="count">{numSelected} selected</span>
      {:else}
        <span class="count muted">Select entries with click or <kbd>Space</kbd></span>
      {/if}
    </div>
    <div class="toolbar-right">
      <button class="tool-btn" disabled={numSelected === 0} title="Export selected (E)"
        onclick={onExport}>Export <kbd>E</kbd></button>
      <button class="tool-btn danger" disabled={numSelected === 0} title="Delete selected (Delete key)"
        onclick={onDelete}>Delete <kbd>Del</kbd></button>
    </div>
  {:else}
    <div class="toolbar-left">
      <button class="tool-btn" title="Toggle selection mode (V)" onclick={onToggleSelectionMode}>Select <kbd>V</kbd></button>
      <button class="tool-btn" title="Toggle sort (S)" onclick={onToggleSort}>Sort <kbd>S</kbd></button>
      <button class="tool-btn" title="Filter by tag (F)" onclick={onToggleTagFilter}>Tags <kbd>F</kbd></button>
    </div>
    <div class="toolbar-center">
      <span class="search-hint"><kbd>/</kbd> search</span>
    </div>
    <div class="toolbar-right">
      <button class="tool-btn primary" onclick={onNew} title="Add received letter">+ New <kbd>N</kbd></button>
      <button class="tool-btn" onclick={onImport} title="Import letters (M)">Import <kbd>M</kbd></button>
      <button class="tool-btn primary" onclick={onSend} title="Send a letter">Send <kbd>S</kbd></button>
    </div>
  {/if}
</div>

<!-- Sort dropdown -->
{#if showSortDropdown}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="dropdown-backdrop" onclick={onCloseSort} role="presentation"></div>
  <div class="dropdown-panel sort-panel">
    <SortDropdown
      sort={currentFilters.sort || "newest"}
      groupByConversation={currentFilters.group === "conversation"}
      sortOptions={[
        { value: "newest", label: "Newest First" },
        { value: "oldest", label: "Oldest First" },
      ]}
      onSortChange={onSortChange}
      onGroupChange={onGroupChange}
    />
  </div>
{/if}

<!-- Tag filter -->
{#if showTagFilter}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="dropdown-backdrop" onclick={onCloseTagFilter} role="presentation"></div>
  <div class="dropdown-panel tag-filter-panel">
    <div class="tag-filter-form">
      <h4 class="section-title">Filter by Tags</h4>
      <MultiEntryField
        label=""
        bind:entries={tagFilterEntries}
        placeholder="Type tag and press Enter"
        hint="AND logic \u2014 letters must have ALL tags"
        onDirtyChange={onTagFilterChange}
      />
      <div class="tag-filter-actions">
        <button class="tool-btn" onclick={onClearTagFilter}>Clear</button>
      </div>
    </div>
  </div>
{/if}

<style>
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

  /* Dropdown panels */
  :global(.dropdown-backdrop) {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    z-index: 99; background: transparent;
  }
  :global(.dropdown-panel) {
    position: absolute; top: 2.4rem; z-index: 100;
    background: #1a1a30; border: 1px solid #444; border-radius: 6px;
    padding: 0.75rem; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    min-width: 200px; max-height: 70vh; overflow-y: auto;
  }
  .sort-panel { right: 5rem; }
  .tag-filter-panel { left: 0.5rem; }

  .section-title {
    margin: 0 0 0.4rem;
    font-size: 0.72rem;
    color: var(--clr-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  .tag-filter-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .tag-filter-actions {
    display: flex;
    gap: 0.4rem;
  }
</style>

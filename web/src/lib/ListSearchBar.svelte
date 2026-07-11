<script>
  /**
   * Shared search bar component for list tabs.
   *
   * Renders a search input with focus-driven UX:
   * - Input focused ? full-width search, action buttons hidden (typing mode)
   * - Input blurred (Enter/blur) ? compact search + action buttons visible (confirmed mode)
   *
   * The parent controls showSearch/searchQuery and provides action buttons
   * via the "actions" slot. The component manages searchFocused internally.
   */
  let {
    showSearch = false,
    searchQuery = "",
    placeholder = "",
    ariaLabel = "Search",
    onSearchInput = () => {},
    onSearchEnter = () => {},
    onSearchEscape = () => {},
    onSearchClear = () => {},
    actions = null,
  } = $props();

  let searchFocused = $state(false);

  // When search opens, mark as focused immediately (before DOM update).
  // The onfocus event fires asynchronously; without this, the toolbar would
  // briefly show compact+buttons mode before onfocus sets searchFocused=true.
  $effect(() => {
    if (showSearch) {
      searchFocused = true;
    }
  });

  function handleSearchFocus() {
    searchFocused = true;
  }

  function handleSearchBlur() {
    searchFocused = false;
  }

  function handleSearchKeydown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      onSearchEnter();
      // Blur the input to show action buttons alongside the search bar
      e.target.blur();
    }
    if (e.key === "Escape") {
      e.stopPropagation();
      onSearchEscape();
    }
  }
</script>

{#if showSearch}
  <div class="search-bar" class:full={searchFocused} class:compact={!searchFocused}>
    <span class="search-icon">🔍</span>
    <input
      type="text"
      class="search-input"
      {placeholder}
      value={searchQuery}
      oninput={onSearchInput}
      onkeydown={handleSearchKeydown}
      onfocus={handleSearchFocus}
      onblur={handleSearchBlur}
      aria-label={ariaLabel || placeholder}
    />
    {#if searchQuery}
      <button class="search-clear" onclick={onSearchClear} aria-label="Clear search">✕</button>
    {/if}
  </div>
  {#if !searchFocused && actions}
    {@render actions()}
  {/if}
{/if}

<style>
  .search-bar {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .search-bar.full {
    flex: 1;
    gap: 0.4rem;
  }
  .search-bar.compact {
    flex: 0 0 auto;
    max-width: 300px;
    min-width: 140px;
  }
  .search-icon { font-size: 0.75rem; opacity: 0.6; flex-shrink: 0; }
  .search-input {
    flex: 1;
    padding: 0.3rem 0.4rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    outline: none;
    min-width: 80px;
  }
  .search-input:focus { border-color: #6a6a9a; }
  .search-input::placeholder { color: #555; }
  .search-clear {
    background: none;
    border: none;
    color: #7c7c9a;
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0.2rem;
    flex-shrink: 0;
  }
  .search-clear:hover { color: #e0e0e0; }
</style>

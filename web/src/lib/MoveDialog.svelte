<script>
  import { email as emailApi } from "./api.js";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let { onConfirm = () => {}, onDismiss = () => {} } = $props();

  let folders = $state([]);
  let query = $state("");
  let selectedFolder = $state(null); // { label, folder_name }
  let loading = $state(true);
  let error = $state("");
  let overlay;

  // Debounce timeout for filtering
  let filterTimeout;

  /** Filtered folder suggestions based on query */
  let suggestions = $derived.by(() => {
    if (!query.trim() || selectedFolder) return [];
    const q = query.toLowerCase();
    return folders.filter((f) => f.label.toLowerCase().includes(q));
  });

  let showSuggestions = $derived(suggestions.length > 0);

  async function loadFolders() {
    loading = true;
    error = "";
    try {
      const result = await emailApi.listFolders();
      folders = result.folders || [];
    } catch (err) {
      error = err.message || "Failed to load folders";
    } finally {
      loading = false;
    }
  }

  function handleInput(e) {
    clearTimeout(filterTimeout);
    query = e.target.value;
    selectedFolder = null;
  }

  function selectSuggestion(folder) {
    selectedFolder = folder;
    query = folder.label;
  }

  function handleConfirm() {
    if (!selectedFolder) return;
    onConfirm(selectedFolder.folder_name);
  }

  const trapKeydown = createDialogTrap(() => overlay, (e) => {
    if (e.key === "Escape") {
      onDismiss();
      e.preventDefault();
      return;
    }
    if (e.key === "Enter" && selectedFolder) {
      handleConfirm();
      e.preventDefault();
      return;
    }
    // Arrow navigation through suggestions
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && showSuggestions) {
      e.preventDefault();
      const focused = document.activeElement;
      const items = overlay?.querySelectorAll(".suggestion-item");
      if (items.length === 0) return;
      let idx = Array.from(items).indexOf(focused);
      if (e.key === "ArrowDown") {
        idx = Math.min(idx + 1, items.length - 1);
      } else {
        idx = Math.max(idx - 1, 0);
      }
      if (idx >= 0) items[idx].focus();
    }
  });

  // Load folders on mount
  $effect(() => {
    loadFolders();
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="overlay" onclick={onDismiss} onkeydown={trapKeydown} role="dialog" aria-modal="true" aria-label="Move messages" bind:this={overlay} tabindex="0">
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="document">
    <h3>Move to folder</h3>
    <p class="desc">Select a destination folder:</p>

    {#if loading}
      <p class="loading-msg">Loading folders…</p>
    {:else if error}
      <p class="error-msg">{error}</p>
    {:else}
      <div class="search-box" role="combobox" aria-expanded={showSuggestions} aria-controls="folder-suggestions">
        <input
          type="text"
          placeholder="Type account/folder…"
          value={query}
          oninput={handleInput}
          onkeydown={trapKeydown}
          aria-autocomplete="list"
        />

        {#if showSuggestions}
          <ul id="folder-suggestions" class="suggestions" role="listbox" aria-label="Folder suggestions">
            {#each suggestions as folder}
              <li
                class="suggestion-item"
                role="option"
                aria-selected={selectedFolder?.folder_name === folder.folder_name}
                tabindex="0"
                onclick={() => selectSuggestion(folder)}
                onkeydown={(e) => {
                  if (e.key === "Enter") selectSuggestion(folder);
                }}
              >
                <span class="folder-label">{folder.label}</span>
                <span class="folder-email">{folder.account_email}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}

    <div class="actions">
      <button class="btn primary" disabled={!selectedFolder} onclick={handleConfirm}>
        Move
      </button>
      <button class="btn" onclick={onDismiss}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
  }

  .dialog {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 10px;
    padding: 1.5rem;
    min-width: 380px;
    max-width: 480px;
    font-family: monospace;
    color: #e0e0e0;
  }

  h3 {
    margin: 0 0 0.3rem;
    font-size: 1rem;
    font-weight: 600;
  }

  .desc {
    color: #7c7c9a;
    font-size: 0.82rem;
    margin-bottom: 0.8rem;
  }

  .loading-msg, .error-msg {
    color: #7c7c9a;
    padding: 0.5rem 0;
  }
  .error-msg {
    color: #c55;
  }

  .search-box {
    position: relative;
    margin-bottom: 1rem;
  }

  input {
    width: 100%;
    padding: 0.5rem 0.6rem;
    border: 1px solid #444;
    border-radius: 5px;
    background: #16162a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    box-sizing: border-box;
    outline: none;
  }
  input:focus {
    border-color: #6a6a9a;
  }
  input::placeholder {
    color: #555;
  }

  .suggestions {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin: 2px 0 0;
    padding: 0;
    list-style: none;
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 5px;
    max-height: 200px;
    overflow-y: auto;
    z-index: 10;
  }

  .suggestion-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    transition: background 0.08s;
  }
  .suggestion-item:hover, .suggestion-item:focus {
    background: #2a2a50;
    outline: none;
  }

  .folder-label {
    color: #e0e0e0;
    font-size: 0.85rem;
  }
  .folder-email {
    color: #5a5a7a;
    font-size: 0.75rem;
  }

  .actions {
    display: flex;
    gap: 0.6rem;
    justify-content: flex-end;
  }

  .btn {
    padding: 0.4rem 1rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.85rem;
    transition: background 0.1s;
  }
  .btn:hover:not(:disabled) {
    background: #3a3a5e;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .btn.primary:not(:disabled) {
    background: #3a5a8a;
    border-color: #4a6a9a;
  }
  .btn.primary:hover:not(:disabled) {
    background: #4a6a9a;
  }
</style>

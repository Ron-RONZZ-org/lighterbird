<script>
  /**
   * FolderDeleteDialog.svelte — 2-level delete confirmation for folders.
   *
   * Level 1: Choose what to do with contained emails.
   *   - Move to Trash (default)
   *   - Move to another folder (shows autocomplete field)
   *
   * Level 2 (conditional): Folder autocomplete with {email}/folder syntax.
   *
   * On confirm: calls onDelete(disposition, targetFolder) where disposition
   * is "trash" or "move".
   */
  import { email as emailApi } from "./api.js";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    folderPaths = [],   // Array of folder paths being deleted
    onDelete = () => {},
    onDismiss = () => {},
  } = $props();

  let numFolders = $derived(folderPaths.length);
  let label = $derived(folderPaths[0] || "");
  let isBatch = $derived(numFolders > 1);

  // Level 1
  let disposition = $state("trash");  // "trash" | "move"

  // Level 2
  let allFolders = $state([]);
  let destQuery = $state("");
  let destFolder = $state(null);
  let loadingFolders = $state(false);

  let suggestions = $derived.by(() => {
    if (!destQuery.trim() || destFolder) return [];
    const q = destQuery.toLowerCase();
    return allFolders.filter(
      (f) => f.label.toLowerCase().includes(q) && !folderPaths.includes(f.label)
    );
  });

  let showSuggestions = $derived(suggestions.length > 0);
  let isValid = $derived(disposition === "trash" || (disposition === "move" && destFolder));
  let overlay;

  async function loadFolders() {
    loadingFolders = true;
    try {
      const result = await emailApi.listFolders();
      allFolders = result.folders || [];
    } catch { /* silent */ }
    finally { loadingFolders = false; }
  }

  function handleDispositionChange(e) {
    disposition = e.target.value;
    if (disposition === "move" && allFolders.length === 0) {
      loadFolders();
    }
  }

  function handleDestInput(e) {
    destQuery = e.target.value;
    destFolder = null;
  }

  function selectSuggestion(folder) {
    destFolder = folder;
    destQuery = folder.label;
  }

  function handleConfirm() {
    if (!isValid) return;
    onDelete(disposition, disposition === "move" ? destFolder?.folder_name : null);
  }

  const trapKeydown = createDialogTrap(() => overlay, (e) => {
    if (e.key === "Escape") { onDismiss(); e.preventDefault(); return; }
    if (e.key === "Enter" && isValid) { handleConfirm(); e.preventDefault(); return; }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && showSuggestions) {
      e.preventDefault();
      const items = overlay?.querySelectorAll(".suggestion-item");
      if (!items?.length) return;
      let idx = Array.from(items).indexOf(document.activeElement);
      idx = e.key === "ArrowDown" ? Math.min(idx + 1, items.length - 1) : Math.max(idx - 1, 0);
      if (idx >= 0) items[idx].focus();
    }
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="overlay" onclick={onDismiss} onkeydown={trapKeydown} role="alertdialog"
     aria-modal="true" aria-label="Delete {isBatch ? 'folders' : 'folder'}"
     bind:this={overlay} tabindex="0">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="document">
    <h3>Delete {isBatch ? `(${numFolders}) folders` : 'folder'}</h3>
    <p class="desc">
      {#if isBatch}
        Deleting {numFolders} folders.
      {:else}
        Deleting folder: <strong>{label}</strong>
      {/if}
    </p>
    <p class="warn">What should happen to the emails inside?</p>

    <!-- Level 1: Disposition -->
    <div class="disposition-group">
      <label class="radio-label">
        <input type="radio" name="disposition" value="trash"
               checked={disposition === "trash"} onchange={handleDispositionChange} />
        <span>Move to Trash</span>
      </label>
      <label class="radio-label">
        <input type="radio" name="disposition" value="move"
               checked={disposition === "move"} onchange={handleDispositionChange} />
        <span>Move to another folder</span>
      </label>
    </div>

    <!-- Level 2: Folder autocomplete (only when "move" selected) -->
    {#if disposition === "move"}
      <div class="dest-box" role="combobox" aria-expanded={showSuggestions} aria-controls="dest-suggestions">
        <input
          type="text"
          class="dest-input"
          placeholder="user@example.com/folder name"
          value={destQuery}
          oninput={handleDestInput}
          onkeydown={trapKeydown}
          aria-autocomplete="list"
        />
        {#if showSuggestions}
          <ul id="dest-suggestions" class="suggestions" role="listbox" aria-label="Destination folder suggestions">
            {#each suggestions as folder}
              <li
                class="suggestion-item"
                role="option"
                aria-selected={destFolder?.folder_name === folder.folder_name}
                tabindex="0"
                onclick={() => selectSuggestion(folder)}
                onkeydown={(e) => { if (e.key === "Enter") selectSuggestion(folder); }}
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
      <button class="btn danger" disabled={!isValid} onclick={handleConfirm}>
        Delete Folder{isBatch ? 's' : ''}
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
    color: #e07070;
  }

  .desc {
    color: #7c7c9a;
    font-size: 0.82rem;
    margin-bottom: 0.3rem;
  }

  .warn {
    color: #c0a040;
    font-size: 0.85rem;
    margin-bottom: 0.8rem;
  }

  .disposition-group {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin-bottom: 0.8rem;
  }

  .radio-label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.85rem;
    color: #e0e0e0;
    cursor: pointer;
  }

  .radio-label input[type="radio"] {
    accent-color: #4a6fa5;
  }

  .dest-box {
    position: relative;
    margin-bottom: 1rem;
  }

  .dest-input {
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
  .dest-input:focus { border-color: #6a6a9a; }
  .dest-input::placeholder { color: #555; }

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

  .folder-label { color: #e0e0e0; font-size: 0.85rem; }
  .folder-email { color: #5a5a7a; font-size: 0.75rem; }

  .actions {
    display: flex;
    gap: 0.6rem;
    justify-content: flex-end;
    margin-top: 0.5rem;
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
  .btn:hover:not(:disabled) { background: #3a3a5e; }
  .btn:disabled { opacity: 0.4; cursor: default; }
  .btn.danger:not(:disabled) {
    background: #6b2020;
    border-color: #8b3030;
  }
  .btn.danger:hover:not(:disabled) { background: #8b3030; }
</style>

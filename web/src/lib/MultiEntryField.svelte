<script>
  /**
   * MultiEntryField.svelte — Reusable chip-based multi-value input.
   *
   * Props:
   *   label           — field label text
   *   entries         — bindable string[] of current entries
   *   placeholder     — input placeholder (default "Type and press Enter")
   *   hint            — optional hint text shown next to label
   *   autocompleteQuery — async (partial: string) => Promise<{label:string,value:string}[]>
   *                       Returns suggestions for drop-down
   *   allowDuplicates — if false, duplicates are silently ignored (default false)
   *   maxEntries      — optional cap (0 = no limit)
   *   maxChipChars    — max characters shown in a chip before truncating (default 40)
   *   onDirtyChange   — (dirty: boolean) => void
   *   disabled        — if true, all interactions disabled (default false)
   */
  let {
    label = "",
    entries = $bindable([]),
    placeholder = "Type and press Enter",
    hint = "",
    autocompleteQuery = null,
    allowDuplicates = false,
    maxEntries = 0,
    maxChipChars = 40,
    onDirtyChange = () => {},
    disabled = false,
  } = $props();

  let inputValue = $state("");
  let suggestions = $state([]);
  let showSuggestions = $state(false);
  let focusedIndex = $state(-1);
  let editingIndex = $state(-1); // -1 = not editing
  let inputEl = $state(null);
  let debounceTimer = $state(null);
  let abortController = $state(null);

  // Dirty tracking — report if we have any entries (versus initial empty)
  let dirty = $derived(entries.length > 0);
  $effect(() => { onDirtyChange(dirty); });

  function addEntry(val) {
    const trimmed = val.trim();
    if (!trimmed) return;
    if (maxEntries > 0 && entries.length >= maxEntries) return;
    if (!allowDuplicates && entries.includes(trimmed)) return;

    if (editingIndex >= 0) {
      entries[editingIndex] = trimmed;
      editingIndex = -1;
    } else {
      entries = [...entries, trimmed];
    }
    inputValue = "";
    suggestions = [];
    showSuggestions = false;
    focusedIndex = -1;
    // Refocus input after state settles
    requestAnimationFrame(() => inputEl?.focus());
  }

  function removeEntry(idx) {
    entries = entries.filter((_, i) => i !== idx);
    if (editingIndex === idx) editingIndex = -1;
    // If we removed before or at the editing index, adjust
    if (editingIndex > idx) editingIndex -= 1;
    inputEl?.focus();
  }

  function startEdit(idx) {
    if (disabled) return;
    editingIndex = idx;
    inputValue = entries[idx];
    showSuggestions = false;
    requestAnimationFrame(() => {
      inputEl?.focus();
      inputEl?.select();
    });
  }

  function cancelEdit() {
    editingIndex = -1;
    inputValue = "";
    suggestions = [];
    showSuggestions = false;
    focusedIndex = -1;
  }

  function selectSuggestion(item) {
    // Replace input value with the suggestion's label
    inputValue = item.label;
    // Immediately add the entry (on Enter, user could also confirm)
    addEntry(item.label);
  }

  async function handleInput(e) {
    const val = e.target.value;
    inputValue = val;

    if (!autocompleteQuery || !val) {
      suggestions = [];
      showSuggestions = false;
      return;
    }

    // Debounce
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      if (abortController) abortController.abort();
      abortController = new AbortController();
      try {
        const results = await autocompleteQuery(val.trim());
        if (results && results.length > 0) {
          // Deduplicate: exclude entries already in the list
          const existing = editingIndex >= 0
            ? entries.filter((_, i) => i !== editingIndex)
            : entries;
          suggestions = results.filter(
            (r) => !existing.includes(r.value) && !existing.includes(r.label)
          );
          showSuggestions = suggestions.length > 0;
          focusedIndex = -1;
        } else {
          suggestions = [];
          showSuggestions = false;
        }
      } catch {
        suggestions = [];
        showSuggestions = false;
      }
    }, 200);
  }

  function handleKeydown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (focusedIndex >= 0 && suggestions[focusedIndex]) {
        selectSuggestion(suggestions[focusedIndex]);
      } else if (inputValue.trim()) {
        addEntry(inputValue);
      }
      return;
    }

    if (e.key === "Backspace" && !inputValue && editingIndex < 0) {
      // Remove last chip
      if (entries.length > 0) {
        removeEntry(entries.length - 1);
      }
      return;
    }

    if (e.key === "Escape") {
      if (showSuggestions) {
        showSuggestions = false;
        suggestions = [];
        e.preventDefault();
      } else if (editingIndex >= 0) {
        cancelEdit();
        e.preventDefault();
      }
      return;
    }

    // Arrow navigation in suggestions
    if (showSuggestions && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      const len = suggestions.length;
      if (e.key === "ArrowDown") {
        focusedIndex = focusedIndex < len - 1 ? focusedIndex + 1 : 0;
      } else {
        focusedIndex = focusedIndex > 0 ? focusedIndex - 1 : len - 1;
      }
      return;
    }

    // Stop propagation for all key events to avoid parent list tab handlers
    e.stopPropagation();
  }

  function handleBlur() {
    // Delay to allow click on suggestion/chip to fire first
    setTimeout(() => {
      showSuggestions = false;
      if (editingIndex >= 0 && inputValue.trim()) {
        addEntry(inputValue);
      } else if (editingIndex >= 0) {
        cancelEdit();
      }
    }, 200);
  }

  function truncated(val) {
    if (val.length <= maxChipChars) return val;
    return val.slice(0, maxChipChars - 3) + "...";
  }

  function chipLabel(val) {
    if (label.toLowerCase() === "tags") {
      // For tag-like fields, show the value directly (often short)
      return val;
    }
    return truncated(val);
  }
</script>

<div class="multi-entry-field" class:disabled>
  {#if label}
    <!-- svelte-ignore a11y_label_has_associated_control -->
    <label>
      <span class="field-label">{label}</span>
      {#if hint}
        <span class="field-hint">{hint}</span>
      {/if}
    </label>
  {/if}

  <div class="chips-wrapper" class:has-focus={false} role="listbox" aria-label={label || "Multi-value input"}>
    {#each entries as entry, i (entry + i)}
      <span class="chip" class:editing={editingIndex === i} role="option" aria-selected={editingIndex === i}>
        {#if editingIndex === i}
          <span class="chip-edit-badge">✎</span>
        {/if}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <span class="chip-label" role="button" tabindex="-1" ondblclick={() => startEdit(i)} title={entry}>{chipLabel(entry)}</span>
        <button
          class="chip-remove"
          onclick={() => removeEntry(i)}
          disabled={disabled}
          aria-label="Remove {entry}"
          tabindex="-1"
        >×</button>
      </span>
    {/each}

    <input
      bind:this={inputEl}
      type="text"
      class="chip-input"
      value={inputValue}
      oninput={handleInput}
      onkeydown={handleKeydown}
      onblur={handleBlur}
      placeholder={entries.length === 0 ? placeholder : ""}
      disabled={disabled}
      aria-label={editingIndex >= 0 ? "Edit entry" : "Add entry"}
    />
  </div>

  {#if showSuggestions && suggestions.length > 0}
    <div class="suggestions-dropdown" role="listbox" aria-label="Suggestions">
      {#each suggestions as item, i}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div
          class="suggestion-item"
          class:focused={focusedIndex === i}
          role="option"
          aria-selected={focusedIndex === i}
          tabindex="-1"
          onmousedown={() => selectSuggestion(item)}
          onmouseenter={() => { focusedIndex = i; }}
        >
          {item.label}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .multi-entry-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .multi-entry-field.disabled {
    opacity: 0.5;
    pointer-events: none;
  }
  label {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
  }
  .field-label {
    font-size: 0.78rem;
    color: var(--clr-sub);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .field-hint {
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
    color: var(--clr-dim);
    font-size: 0.7rem;
  }
  .chips-wrapper {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    align-items: center;
    background: #16213e;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 0.3rem 0.4rem;
    min-height: 2.2rem;
    transition: border-color 0.15s;
  }
  .chips-wrapper:focus-within {
    border-color: #5a5a8a;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.15rem;
    background: #2a3a5a;
    border: 1px solid #4a5a7a;
    border-radius: 3px;
    padding: 0.1rem 0.3rem 0.1rem 0.4rem;
    font-size: 0.78rem;
    color: #d0d8e8;
    transition: background 0.1s;
  }
  .chip:hover {
    background: #3a4a6a;
  }
  .chip.editing {
    background: #3a5a3a;
    border-color: #5a8a5a;
    box-shadow: 0 0 4px rgba(90, 138, 90, 0.4);
  }
  .chip-edit-badge {
    font-size: 0.65rem;
    color: #8aca8a;
    margin-right: 0.1rem;
  }
  .chip-label {
    cursor: default;
    max-width: 12rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chip-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: #8898b8;
    cursor: pointer;
    font-size: 0.9rem;
    line-height: 1;
    padding: 0 0.1rem;
    border-radius: 2px;
    transition: color 0.1s, background 0.1s;
  }
  .chip-remove:hover {
    color: #e08080;
    background: rgba(200, 60, 60, 0.15);
  }
  .chip-input {
    flex: 1;
    min-width: 80px;
    background: transparent;
    border: none;
    outline: none;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 0.85rem;
    padding: 0.25rem 0.3rem;
  }
  .chip-input::placeholder {
    color: #555;
  }
  .suggestions-dropdown {
    position: absolute;
    z-index: 200;
    background: #1e1e36;
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    max-height: 200px;
    overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    min-width: 180px;
  }
  .suggestion-item {
    padding: 0.35rem 0.6rem;
    font-size: 0.82rem;
    color: #d0d0e0;
    cursor: pointer;
    transition: background 0.1s;
  }
  .suggestion-item:hover,
  .suggestion-item.focused {
    background: #2a2a4e;
  }
</style>

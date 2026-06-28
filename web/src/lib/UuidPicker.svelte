<script>
  /**
   * UuidPicker.svelte — Autocomplete UUID picker with data cache integration.
   *
   * Fetches suggestions from the popup data cache for the given uuidSource.
   * Supports type-to-search, keyboard navigation, and clear.
   *
   * Props:
   *   uuidSource — cache source key (e.g. "email.listAccounts", "todo.list")
   *   value      — currently selected UUID (bindable)
   *   placeholder — input placeholder text
   *   required   — if true, input is required
   *   label      — optional field label (uses FormField if provided)
   *   hint       — optional hint text
   *
   * Events:
   *   onchange(newValue) — called when selection changes
   */

  import { popup } from "./popupStore.svelte.js";
  import { getDataCompletionsFromCache } from "./commandEngine.js";
  import FormField from "./FormField.svelte";

  let {
    uuidSource = "",
    value = "",
    placeholder = "Type to search…",
    required = false,
    label = "",
    hint = "",
    onchange = (v) => {},
  } = $props();

  let inputValue = $state(value || "");
  let suggestions = $state([]);
  let showDropdown = $state(false);
  let activeIndex = $state(-1);
  let inputEl = $state(null);

  $effect(() => {
    if (value !== inputValue && !showDropdown) {
      inputValue = value || "";
    }
  });

  let allItems = $derived(getDataCompletionsFromCache(popup.cache, uuidSource));

  function handleInput(e) {
    const q = e.target.value.toLowerCase();
    inputValue = q;

    if (q.length === 0) {
      suggestions = [];
      showDropdown = false;
      onchange("");
      return;
    }

    const matches = allItems.filter(
      (item) => item.label.toLowerCase().includes(q) || item.uuid.toLowerCase().includes(q),
    );
    suggestions = matches.slice(0, 20);
    showDropdown = matches.length > 0;
    activeIndex = -1;

    // Check if exact UUID was typed
    const exact = allItems.find((item) => item.uuid === q);
    if (exact) {
      onchange(exact.uuid);
    } else {
      onchange(q); // allow raw UUID entry
    }
  }

  function selectItem(item) {
    value = item.uuid;
    inputValue = item.label;
    showDropdown = false;
    onchange(item.uuid);
  }

  function handleKeydown(e) {
    if (!showDropdown) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, suggestions.length - 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        break;
      case "Enter":
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < suggestions.length) {
          selectItem(suggestions[activeIndex]);
        }
        break;
      case "Escape":
        showDropdown = false;
        activeIndex = -1;
        break;
    }
  }

  function handleBlur() {
    setTimeout(() => {
      showDropdown = false;
      activeIndex = -1;
    }, 200);
  }

  function handleClear() {
    inputValue = "";
    suggestions = [];
    showDropdown = false;
    value = "";
    onchange("");
    inputEl?.focus();
  }
</script>

{#if label}
  <FormField {label} {hint} {required}>
    {#snippet children()}
      <div class="uuid-picker-wrapper">
        <input
          bind:this={inputEl}
          type="text"
          class="uuid-input"
          class:has-value={!!value}
          bind:value={inputValue}
          oninput={handleInput}
          onkeydown={handleKeydown}
          onblur={handleBlur}
          onfocus={() => { if (suggestions.length > 0) showDropdown = true; }}
          {placeholder}
          {required}
        />
        {#if inputValue}
          <button class="clear-btn" onclick={handleClear} aria-label="Clear" tabindex="-1">✕</button>
        {/if}
        {#if showDropdown && suggestions.length > 0}
          <div class="dropdown" role="listbox">
            {#each suggestions as item, i}
              <div
                class="dropdown-item"
                class:active={i === activeIndex}
                role="option"
                aria-selected={i === activeIndex}
                onmousedown={() => selectItem(item)}
              >
                <span class="item-uuid">{item.uuid.slice(0, 8)}</span>
                <span class="item-label">{item.label}</span>
              </div>
            {:else}
              <div class="dropdown-empty">No matches</div>
            {/each}
          </div>
        {/if}
      </div>
    {/snippet}
  </FormField>
{:else}
  <div class="uuid-picker-wrapper">
    <input
      bind:this={inputEl}
      type="text"
      class="uuid-input"
      class:has-value={!!value}
      bind:value={inputValue}
      oninput={handleInput}
      onkeydown={handleKeydown}
      onblur={handleBlur}
      onfocus={() => { if (suggestions.length > 0) showDropdown = true; }}
      {placeholder}
      {required}
    />
    {#if inputValue}
      <button class="clear-btn" onclick={handleClear} aria-label="Clear" tabindex="-1">✕</button>
    {/if}
    {#if showDropdown && suggestions.length > 0}
      <div class="dropdown" role="listbox">
        {#each suggestions as item, i}
          <div
            class="dropdown-item"
            class:active={i === activeIndex}
            role="option"
            aria-selected={i === activeIndex}
            onmousedown={() => selectItem(item)}
          >
            <span class="item-uuid">{item.uuid.slice(0, 8)}</span>
            <span class="item-label">{item.label}</span>
          </div>
        {:else}
          <div class="dropdown-empty">No matches</div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .uuid-picker-wrapper {
    position: relative;
    display: flex;
    align-items: center;
  }
  .uuid-input {
    flex: 1;
    padding: 0.5rem 0.6rem;
    padding-right: 2rem;
    background: #16213e;
    border: 1px solid #333;
    color: #e0e0e0;
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .uuid-input:focus {
    border-color: #5a5a8a;
  }
  .uuid-input.has-value {
    border-color: #4a6a4a;
  }
  .clear-btn {
    position: absolute;
    right: 0.4rem;
    background: transparent;
    border: none;
    color: #7c7c9a;
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0.2rem;
    line-height: 1;
  }
  .clear-btn:hover {
    color: #e0e0e0;
  }
  .dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 100;
    background: #1e1e36;
    border: 1px solid #4a4a6a;
    border-top: none;
    border-radius: 0 0 4px 4px;
    max-height: 200px;
    overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .dropdown-item:hover,
  .dropdown-item.active {
    background: #2a2a4e;
  }
  .item-uuid {
    color: var(--clr-dim);
    font-size: 0.72rem;
    flex-shrink: 0;
    min-width: 4rem;
    font-family: monospace;
  }
  .item-label {
    color: #e0e0e0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .dropdown-empty {
    padding: 0.5rem;
    color: var(--clr-muted);
    font-size: 0.8rem;
    text-align: center;
  }
</style>

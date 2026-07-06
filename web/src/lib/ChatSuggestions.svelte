<script>
  /**
   * ChatSuggestions.svelte
   *
   * Presentational dropdown that renders autocomplete suggestions, data
   * completions (UUIDs), positional argument trackers, and hints.
   *
   * Props:
   *   suggestions         — array of flag/suggestion strings
   *   dataCompletions     — array of data completion objects [{ uuid, value, label }]
   *   hints               — array of hint strings (parallel to suggestions)
   *   positionals         — array of positional arg trackers [{ name, entered, required }]
   *   selectedSuggestion  — index of highlighted flag suggestion
   *   selectedDataIndex   — index of highlighted data completion
   *   isCommandMode       — whether input starts with !
   *   showSuggestions     — whether the dropdown should be visible
   *   onSelect            — called with the string to insert when an item is clicked
   */
  let {
    suggestions = [],
    dataCompletions = [],
    hints = [],
    positionals = [],
    selectedSuggestion = -1,
    selectedDataIndex = -1,
    isCommandMode = false,
    showSuggestions = false,
    onSelect = (value) => {},
  } = $props();

  /** Get the text to insert when a data completion is selected. */
  function getDataValue(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
  }

  /** Get the display text for a data completion item. */
  function getDataLabel(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
  }
</script>

{#if showSuggestions}
  <div class="suggestions">
    <!-- Positional argument tracker (non-interactive) -->
    {#if positionals.length > 0}
      <div class="positional-tracker" aria-hidden="true">
        {#each positionals as p, i}
          <span class="pos-arg" class:entered={p.entered} class:pending={!p.entered}>
            {p.entered ? p.name : `<${p.name}>`}
          </span>
          {#if !p.entered && p.required}
            <span class="pos-required" aria-hidden="true">*</span>
          {/if}
          {#if i < positionals.length - 1}
            <span class="pos-sep"> </span>
          {/if}
        {/each}
      </div>
    {/if}

    <!-- Flag suggestions -->
    {#each suggestions as suggestion, i}
      <button
        class="suggestion"
        class:selected={i === selectedSuggestion}
        onmousedown={(e) => {
          e.preventDefault();
          onSelect(suggestion);
        }}
      >
        <span class="suggestion-text">{suggestion}</span>
        {#if hints[i]}
          <span class="hint-text">{hints[i]}</span>
        {/if}
      </button>
    {/each}

    <!-- Data completions (UUIDs) -->
    {#each dataCompletions as dc, i}
      <button
        class="suggestion"
        class:selected={i === selectedDataIndex}
        onmousedown={(e) => {
          e.preventDefault();
          onSelect(getDataValue(dc));
        }}
      >
        <span class="suggestion-text">{getDataLabel(dc)}</span>
        <span class="hint-text">{dc.value ? "" : dc.label}</span>
      </button>
    {/each}
  </div>
{/if}

<style>
  /* Suggestions dropdown */
  .suggestions {
    width: 100%;
    max-height: 200px;
    overflow-y: auto;
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 8px;
    margin-top: 4px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 100;
  }
  /* Positional tracker row (non-interactive, info-only) */
  .positional-tracker {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.35rem 0.75rem;
    background: #16162a;
    border-bottom: 1px solid #333;
    font-family: monospace;
    font-size: 0.8rem;
    user-select: none;
    pointer-events: none;
  }
  .pos-arg {
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
  }
  .pos-arg.entered {
    color: #c0c0e0;
    font-weight: 500;
  }
  .pos-arg.pending {
    color: #5a5a7a;
  }
  .pos-required {
    color: #c44;
    font-size: 0.7rem;
    margin-left: 0;
  }
  .pos-sep {
    color: #444;
  }

  .suggestion {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.4rem 0.75rem;
    background: transparent;
    border: none;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
  }
  .suggestion:hover,
  .suggestion.selected {
    background: #2a2a44;
  }
  .hint-text {
    color: #7c7c9a;
    font-size: 0.75rem;
    margin-left: 1rem;
    flex-shrink: 0;
  }
</style>

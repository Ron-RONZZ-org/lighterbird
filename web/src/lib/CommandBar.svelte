<script>
  import { commandTree } from "./commandTree.js";
  import { getCompletions, getDataCompletionsFromCache } from "./commandEngine.js";
  import { parseCommand, hasTrailingSpace } from "./parser.js";
  import { email as emailApi, calendar as calendarApi } from "./api.js";
  import { history } from "./commandHistory.svelte.js";
  import { popup } from "./popupStore.svelte.js";

  let { isLoading = false, oncommand } = $props();

  let inputValue = $state("");
  let suggestions = $state([]);
  let hints = $state([]);
  let dataCompletions = $state([]);
  let selectedSuggestion = $state(-1);
  let selectedDataIndex = $state(-1);

  // Derived — show suggestions when either type has items
  let showSuggestions = $derived(
    displaySuggestions.length > 0 || dataCompletions.length > 0,
  );

  // Filter out placeholder hints when real data completions exist.
  let displaySuggestions = $derived(
    dataCompletions.length > 0
      ? suggestions.filter((s) => !s.startsWith("<") && !s.startsWith("["))
      : suggestions,
  );
  let displayHints = $derived(
    dataCompletions.length > 0
      ? hints.filter((_, i) => !suggestions[i].startsWith("<") && !suggestions[i].startsWith("["))
      : hints,
  );

  /** Count how many leading tokens are command path (not params). */
  function countCommandTokens(tokens) {
    let current = commandTree;
    for (let i = 0; i < tokens.length; i++) {
      const found = current.find(
        (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
      );
      if (!found) return i;
      if (found.apiMethod) return i + 1;
      current = found.children || [];
    }
    return tokens.length;
  }

  function updateSuggestions() {
    if (!inputValue.startsWith("!")) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    const result = getCompletions(inputValue);
    suggestions = result.completions;
    hints = result.hints;
    selectedSuggestion = -1;
    selectedDataIndex = -1;

    // Only show data completions (UUIDs) when cursor is at a param position
    // that expects a UUID (has uuidSource). This prevents UUIDs from appearing
    // at root or child navigation levels.
    dataCompletions = [];
    if (result.node && result.node.params && result.level === "params") {
      const { tokens, partial } = parseCommand(inputValue);
      const trailing = hasTrailingSpace(inputValue);
      const effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
      const cmdTokens = countCommandTokens(effectiveTokens);
      const consumed = effectiveTokens.length - cmdTokens;

      for (let i = consumed; i < result.node.params.length; i++) {
        const p = result.node.params[i];
        if (p.uuidSource) {
          dataCompletions = getDataCompletionsFromCache(popup.cache, p.uuidSource);
          break;
        }
      }
    }
  }

  function handleInput(e) {
    inputValue = e.target.value;
    updateSuggestions();
  }

  function applyCompletion(completion) {
    if (!completion) return;
    if (inputValue.endsWith(" ")) {
      inputValue = inputValue + completion + " ";
    } else if (completion.startsWith("!") && inputValue.startsWith("!")) {
      inputValue = completion + " ";
    } else {
      const parts = inputValue.split(/\s+/);
      parts[parts.length - 1] = completion;
      inputValue = parts.join(" ") + " ";
    }
    suggestions = [];
    hints = [];
    dataCompletions = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
    requestAnimationFrame(() => updateSuggestions());
  }

  function hideSuggestions() {
    suggestions = [];
    hints = [];
    dataCompletions = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
  }

  /** Refresh the data cache with current accounts/calendars from the backend. */
  async function refreshDataCache() {
    try {
      const [accts, cals] = await Promise.all([
        emailApi.listAccounts().catch(() => null),
        calendarApi.listCalendars().catch(() => null),
      ]);
      popup.updateCache({
        accounts: accts?.accounts ?? [],
        calendars: cals?.calendars ?? [],
      });
      // Re-read from cache to update dataCompletions if the popup is still
      // showing UUID completions
      updateSuggestions();
    } catch { /* background fetch failed silently */ }
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (suggestions.length > 0 || dataCompletions.length > 0) {
        hideSuggestions();
        return;
      }
      popup.close();
      return;
    }

    if (e.key === "Tab") {
      e.preventDefault();
      if (displaySuggestions.length > 0) {
        const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
        applyCompletion(displaySuggestions[idx]);
      } else if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        // Insert only the UUID prefix (first 8 chars) — backend resolves via LIKE
        applyCompletion(dataCompletions[idx].uuid.slice(0, 8));
      }
      return;
    }

    if (e.key === "ArrowUp") {
      if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
        e.preventDefault();
        selectedDataIndex = Math.max(0, selectedDataIndex - 1);
        return;
      }
      if (displaySuggestions.length > 0) {
        e.preventDefault();
        selectedSuggestion = Math.max(0, selectedSuggestion - 1);
        return;
      }
      e.preventDefault();
      const cmd = history.back();
      if (cmd) inputValue = cmd;
      requestAnimationFrame(() => updateSuggestions());
      return;
    }

    if (e.key === "ArrowDown") {
      if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
        e.preventDefault();
        selectedDataIndex = Math.min(dataCompletions.length - 1, selectedDataIndex + 1);
        return;
      }
      if (displaySuggestions.length > 0) {
        e.preventDefault();
        selectedSuggestion = Math.min(displaySuggestions.length - 1, selectedSuggestion + 1);
        return;
      }
      e.preventDefault();
      const cmd = history.forward();
      inputValue = cmd;
      requestAnimationFrame(() => updateSuggestions());
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      const cmd = inputValue.trim();
      if (!cmd) return;

      // If suggestions exist and input is partial, complete instead of execute
      if (displaySuggestions.length > 0) {
        const lastToken = cmd.split(/\s+/).pop() || "";
        const isPartial = displaySuggestions.some((s) => s !== lastToken && !s.startsWith("<") && !s.startsWith("["));
        if (isPartial) {
          const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
          applyCompletion(displaySuggestions[idx]);
          return;
        }
      }

      // If UUID suggestions are shown and one is selected (or first), apply it
      if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        applyCompletion(dataCompletions[idx].uuid.slice(0, 8));
        return;
      }

      // Execute the command, then refresh cache with current backend state
      history.push(cmd);
      inputValue = "";
      hideSuggestions();
      // Refresh cache AFTER command completes so UUID suggestions reflect reality
      Promise.resolve(oncommand(cmd)).finally(() => refreshDataCache());
    }
  }
</script>

<div class="command-bar">
  <div class="input-wrapper">
    <span class="prefix">❯</span>
    <input
      type="text"
      value={inputValue}
      oninput={handleInput}
      onkeydown={handleKeydown}
      placeholder="Type !command or ask the LLM anything..."
      disabled={isLoading}
      aria-label="Command input"
      autocomplete="off"
      autofocus
    />
    {#if isLoading}
      <span class="spinner" aria-label="Loading">...</span>
    {/if}
  </div>
  {#if showSuggestions}
    <ul class="suggestions" role="listbox">
      {#each displaySuggestions as suggestion, i}
        <li
          role="option"
          class="suggestion"
          class:selected={i === selectedSuggestion}
          aria-selected={i === selectedSuggestion}
          onmousedown={(e) => { e.preventDefault(); applyCompletion(suggestion); }}
        >
          <span class="suggestion-text">{suggestion}</span>
          {#if displayHints[i]}
            <span class="hint-text">{displayHints[i]}</span>
          {/if}
        </li>
      {/each}
      {#each dataCompletions as dc, i}
        <li
          role="option"
          class="suggestion"
          class:selected={i === selectedDataIndex}
          onmousedown={(e) => { e.preventDefault(); applyCompletion(dc.uuid.slice(0, 8)); }}
        >
          <span class="suggestion-text">{dc.uuid.slice(0, 8)}</span>
          <span class="hint-text">{dc.label}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .command-bar { border-bottom: 1px solid #333; position: relative; }
  .input-wrapper { display: flex; align-items: center; padding: 0.5rem 1rem; gap: 0.5rem; }
  .prefix { color: #7c7c9a; font-family: monospace; font-size: 1rem; }
  input { flex: 1; background: transparent; border: none; color: #e0e0e0; font-family: monospace; font-size: 1rem; outline: none; }
  input::placeholder { color: #555; }
  input:disabled { opacity: 0.5; }
  .spinner { color: #7c7c9a; animation: pulse 1s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
  .suggestions { list-style: none; padding: 0; margin: 0; border-top: 1px solid #333; max-height: 240px; overflow-y: auto; }
  .suggestion { display: flex; justify-content: space-between; align-items: center; padding: 0.35rem 1rem; font-family: monospace; font-size: 0.9rem; cursor: pointer; }
  .suggestion:hover, .suggestion.selected { background: #16213e; color: #fff; }
  .hint-text { color: #7c7c9a; font-size: 0.8rem; margin-left: 1rem; }
  .suggestion.selected .hint-text { color: #9a9ac0; }
</style>

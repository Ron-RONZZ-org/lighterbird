<script>
  import { commandTree } from "./commandTree.js";
  import { getCompletions, getDataCompletionsFromCache } from "./commandEngine.js";
  import { parseCommand, hasTrailingSpace } from "./parser.js";
  import { email as emailApi, calendar as calendarApi, contacts as contactsApi, todo as todoApi, journal as journalApi } from "./api.js";
  import { history } from "./commandHistory.svelte.js";
  import { popup } from "./popupStore.svelte.js";

  let { isLoading = false, oncommand } = $props();

  let inputValue = $state("");
  let suggestions = $state([]);
  let hints = $state([]);
  let dataCompletions = $state([]);
  let positionals = $state([]);
  let selectedSuggestion = $state(-1);
  let selectedDataIndex = $state(-1);

  // Track if we have any interactive content in the dropdown
  let hasInteractiveItems = $derived(
    suggestions.length > 0 || dataCompletions.length > 0,
  );

  let showSuggestions = $derived(
    hasInteractiveItems || positionals.length > 0,
  );

  // When data completions exist, hide flag suggestions to reduce clutter
  let displaySuggestions = $derived(
    dataCompletions.length > 0 ? [] : suggestions,
  );
  let displayHints = $derived(
    dataCompletions.length > 0 ? [] : hints,
  );

  /** Count how many leading tokens are command path (not params). */
  function countCommandTokens(tokens) {
    let current = commandTree;
    for (let i = 0; i < tokens.length; i++) {
      const found = current.find(
        (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
      );
      if (!found) return i;
      if (!found.children || found.children.length === 0) return i + 1;
      current = found.children || [];
    }
    return tokens.length;
  }

  function updateSuggestions() {
    if (!inputValue.startsWith("!")) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    const result = getCompletions(inputValue);
    suggestions = result.completions;
    hints = result.hints;
    positionals = result.positionals;
    selectedSuggestion = -1;
    selectedDataIndex = -1;

    // Only show data completions (UUIDs) when cursor is at a param position
    // that expects a UUID (has uuidSource).
    dataCompletions = [];
    if (result.node && result.level === "params") {
      const { tokens, partial } = parseCommand(inputValue);
      const trailing = hasTrailingSpace(inputValue);
      const effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
      const cmdTokens = countCommandTokens(effectiveTokens);
      const consumed = effectiveTokens.length - cmdTokens;

      // 1. Check positional params for uuidSource
      if (result.node.params) {
        for (let i = consumed; i < result.node.params.length; i++) {
          const p = result.node.params[i];
          if (p.uuidSource) {
            dataCompletions = getDataCompletionsFromCache(popup.cache, p.uuidSource);
            break;
          }
        }

        // Repeatable params: keep showing completions after all consumed
        if (dataCompletions.length === 0 && result.node.params.length > 0) {
          const lastParam = result.node.params[result.node.params.length - 1];
          if (lastParam.repeatable && lastParam.uuidSource && consumed >= result.node.params.length) {
            dataCompletions = getDataCompletionsFromCache(popup.cache, lastParam.uuidSource);
          }
        }
      }

      // 2. Check flags for uuidSource — user just typed a --flag and needs a value
      if (dataCompletions.length === 0 && result.node.flags) {
        for (const f of result.node.flags) {
          if (f.uuidSource && f.name in flags && flags[f.name] === "") {
            // User completed --folder and now needs a value suggestion
            dataCompletions = getDataCompletionsFromCache(popup.cache, f.uuidSource);
            break;
          }
        }
      }

      // Filter out already-inputted UUIDs
      if (dataCompletions.length > 0) {
        const paramTokens = effectiveTokens.slice(cmdTokens);
        const usedUuids = new Set(paramTokens.map(t => t.toLowerCase()));
        dataCompletions = dataCompletions.filter(dc => !usedUuids.has(dc.uuid.slice(0, 8).toLowerCase()));
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
    positionals = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
    requestAnimationFrame(() => updateSuggestions());
  }

  function hideSuggestions() {
    suggestions = [];
    hints = [];
    dataCompletions = [];
    positionals = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
  }

  /** Refresh the data cache with current data from the backend. */
  async function refreshDataCache() {
    try {
      const [accts, cals, conts, tds, jrnl] = await Promise.all([
        emailApi.listAccounts().catch(() => null),
        calendarApi.listCalendars().catch(() => null),
        contactsApi.list({limit: 50}).catch(() => null),
        todoApi.list({limit: 50}).catch(() => null),
        journalApi.list({limit: 50}).catch(() => null),
      ]);
      popup.updateCache({
        accounts: accts?.accounts ?? [],
        calendars: cals?.calendars ?? [],
        contacts: conts?.contacts ?? [],
        todos: tds?.todos ?? [],
        journal: jrnl?.entries ?? [],
      });
      updateSuggestions();
    } catch { /* background fetch failed silently */ }
  }

  function handleKeydown(e) {
    // Escape
    if (e.key === "Escape") {
      if (hasInteractiveItems) {
        hideSuggestions();
        return;
      }
      popup.close();
      return;
    }

    // Tab: autocomplete (skip positional tracker — it has no items to select)
    if (e.key === "Tab") {
      e.preventDefault();
      if (displaySuggestions.length > 0) {
        const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
        applyCompletion(displaySuggestions[idx]);
      } else if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        const dc = dataCompletions[idx];
        applyCompletion(dc.value || dc.uuid.slice(0, 8));
      }
      return;
    }

    // ArrowUp (skip positional tracker)
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

    // ArrowDown (skip positional tracker)
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

    // Enter
    if (e.key === "Enter") {
      e.preventDefault();
      const cmd = inputValue.trim();
      if (!cmd) return;

      // If suggestions exist and input is partial, complete instead of execute
      if (displaySuggestions.length > 0) {
        const lastToken = cmd.split(/\s+/).pop() || "";
        const isPartial = displaySuggestions.some((s) =>
          s.toLowerCase().startsWith(lastToken.toLowerCase())
          && s !== lastToken
          && !s.startsWith("<")
          && !s.startsWith("[")
        );
        if (isPartial) {
          const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
          applyCompletion(displaySuggestions[idx]);
          return;
        }
      }

      // UUID completions
      if (dataCompletions.length > 0) {
        const lastToken = cmd.split(/\s+/).pop() || "";
        if (selectedDataIndex >= 0) {
          const dc = dataCompletions[selectedDataIndex];
          applyCompletion(dc.value || dc.uuid.slice(0, 8));
          return;
        }
        if (!/^[0-9a-f]{8,}$/i.test(lastToken)) {
          const dc = dataCompletions[0];
          applyCompletion(dc.value || dc.uuid.slice(0, 8));
          return;
        }
      }

      // Execute
      history.push(cmd);
      inputValue = "";
      hideSuggestions();
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
      <span class="spinner" aria-label="Loading">
        <span class="spinner-dot"></span>
        <span class="spinner-dot"></span>
        <span class="spinner-dot"></span>
      </span>
    {/if}
  </div>
  {#if showSuggestions}
    <ul class="suggestions" role="listbox">
      <!-- Positional argument tracker (non-interactive) -->
      {#if positionals.length > 0}
        <li role="presentation" class="positional-tracker" aria-hidden="true">
          {#each positionals as p}
            <span class="pos-arg" class:entered={p.entered} class:pending={!p.entered}>
              {p.entered ? p.name : `<${p.name}>`}
            </span>
            {#if !p.entered && p.required}
              <span class="pos-required" aria-hidden="true">*</span>
            {/if}
          {/each}
        </li>
      {/if}

      <!-- Flag suggestions -->
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

      <!-- Data completions (UUIDs or value-based like folders) -->
      {#each dataCompletions as dc, i}
        <li
          role="option"
          class="suggestion"
          class:selected={i === selectedDataIndex}
          onmousedown={(e) => { e.preventDefault(); applyCompletion(dc.value || dc.uuid.slice(0, 8)); }}
        >
          <span class="suggestion-text">{dc.value || dc.uuid.slice(0, 8)}</span>
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
  .spinner { display: flex; gap: 3px; align-items: center; padding: 0 4px; }
  .spinner-dot { width: 6px; height: 6px; background: #7c7c9a; border-radius: 50%; animation: dot-bounce 1s ease-in-out infinite; }
  .spinner-dot:nth-child(2) { animation-delay: 0.16s; }
  .spinner-dot:nth-child(3) { animation-delay: 0.32s; }
  @keyframes dot-bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
  .suggestions { list-style: none; padding: 0; margin: 0; border-top: 1px solid #333; max-height: 240px; overflow-y: auto; }

  /* Positional tracker row (non-interactive) */
  .positional-tracker {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.35rem 1rem;
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
  }

  .suggestion {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.35rem 1rem;
    font-family: monospace;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .suggestion:hover, .suggestion.selected { background: #16213e; color: #fff; }
  .hint-text { color: #7c7c9a; font-size: 0.8rem; margin-left: 1rem; }
  .suggestion.selected .hint-text { color: #9a9ac0; }
</style>

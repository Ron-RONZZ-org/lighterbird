<script>
  import { commandTree } from "./commandTree.js";
  import { getCompletions, getDataCompletionsFromCache } from "./commandEngine.js";
  import { parseCommand, hasTrailingSpace } from "./parser.js";
  import { popup } from "./popupStore.svelte.js";

  let {
    onSubmit,
    placeholder = "Ask anything or type ! for commands…",
    centered = true,
  } = $props();

  let value = $state("");
  let suggestions = $state([]);
  let hints = $state([]);
  let dataCompletions = $state([]);
  let selectedSuggestion = $state(-1);
  let selectedDataIndex = $state(-1);
  let isCommandMode = $state(false);
  let textareaEl = $state(null);

  let showSuggestions = $derived(
    (isCommandMode && suggestions.length > 0) || dataCompletions.length > 0,
  );

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

  // Check if input starts with ! → command mode
  function checkCommandMode() {
    isCommandMode = value.startsWith("!");
    if (!isCommandMode) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
    }
  }

  function updateSuggestions() {
    if (!isCommandMode) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    const result = getCompletions(value);
    suggestions = result.completions;
    hints = result.hints;
    selectedSuggestion = -1;
    selectedDataIndex = -1;

    // UUID completions (positional params + flag values)
    dataCompletions = [];
    if (result.node && result.level === "params") {
      const { tokens, flags, partial } = parseCommand(value);
      const trailing = hasTrailingSpace(value);
      const effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
      const cmdTokens = countCommandTokens(effectiveTokens);

      // 1. Check positional params
      if (result.node.params) {
        const consumed = effectiveTokens.length - cmdTokens;
        for (let i = consumed; i < result.node.params.length; i++) {
          const p = result.node.params[i];
          if (p.uuidSource) {
            dataCompletions = getDataCompletionsFromCache(popup.cache, p.uuidSource);
            break;
          }
        }

        if (dataCompletions.length === 0 && result.node.params.length > 0) {
          const lastParam = result.node.params[result.node.params.length - 1];
          if (lastParam.repeatable && lastParam.uuidSource && consumed >= result.node.params.length) {
            dataCompletions = getDataCompletionsFromCache(popup.cache, lastParam.uuidSource);
          }
        }
      }

      // 2. Check flags that have uuidSource (e.g. --folder)
      if (dataCompletions.length === 0 && result.node.flags) {
        for (const f of result.node.flags) {
          if (f.uuidSource) {
            // Show auto-completion when the flag name is present in parsed flags.
            // This includes both when the value is being typed (flags[f.name] is the partial)
            // and when the value is complete (flag name exists, user may be refining).
            if (f.name in flags) {
              dataCompletions = getDataCompletionsFromCache(popup.cache, f.uuidSource);
              break;
            }
          }
        }
      }

      if (dataCompletions.length > 0) {
        const paramTokens = effectiveTokens.slice(cmdTokens);
        const usedValues = new Set(paramTokens.map(t => t.toLowerCase()));
        dataCompletions = dataCompletions.filter((dc) => {
          const insertVal = getDataValue(dc).toLowerCase();
          return !usedValues.has(insertVal);
        });
      }
    }
  }

  function countCommandTokens(tokens) {
    let current = commandTree;
    for (let i = 0; i < tokens.length; i++) {
      const found = current.find((n) => n.name.toLowerCase() === tokens[i].toLowerCase());
      if (!found) return i;
      if (!found.children || found.children.length === 0) return i + 1;
      current = found.children || [];
    }
    return tokens.length;
  }

  function handleInput() {
    checkCommandMode();
    if (isCommandMode) updateSuggestions();
  }

  /** Get the text to insert when a data completion is selected. */
  function getDataValue(dc) {
    // Folders have a "value" field with the full folder path
    return dc.value || dc.uuid.slice(0, 8);
  }

  /** Get the display text for a data completion item. */
  function getDataLabel(dc) {
    // For value-based completions (folders), show the value, not the UUID
    return dc.value || dc.uuid.slice(0, 8);
  }

  function applyCompletion(completion) {
    if (!completion) return;
    if (value.endsWith(" ")) {
      value = value + completion + " ";
    } else if (completion.startsWith("!") && value.startsWith("!")) {
      value = completion + " ";
    } else {
      const parts = value.split(/\s+/);
      parts[parts.length - 1] = completion;
      value = parts.join(" ") + " ";
    }
    suggestions = [];
    hints = [];
    dataCompletions = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
    requestAnimationFrame(() => updateSuggestions());
  }

  function handleKeydown(e) {
    // Escape: close suggestions
    if (e.key === "Escape") {
      if (showSuggestions) {
        suggestions = [];
        hints = [];
        dataCompletions = [];
        return;
      }
      return;
    }

    // Tab: autocomplete
    if (e.key === "Tab" && showSuggestions) {
      e.preventDefault();
      if (displaySuggestions.length > 0) {
        const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
        applyCompletion(displaySuggestions[idx]);
      } else if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        applyCompletion(getDataValue(dataCompletions[idx]));
      }
      return;
    }

    // Arrow keys for suggestion navigation
    if (e.key === "ArrowUp" && showSuggestions) {
      e.preventDefault();
      if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
        selectedDataIndex = Math.max(0, selectedDataIndex - 1);
      } else if (displaySuggestions.length > 0) {
        selectedSuggestion = Math.max(0, selectedSuggestion - 1);
      }
      return;
    }

    if (e.key === "ArrowDown" && showSuggestions) {
      e.preventDefault();
      if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
        selectedDataIndex = Math.min(dataCompletions.length - 1, selectedDataIndex + 1);
      } else if (displaySuggestions.length > 0) {
        selectedSuggestion = Math.min(displaySuggestions.length - 1, selectedSuggestion + 1);
      }
      return;
    }

    // Enter: submit (Shift+Enter = newline)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const cmd = value.trim();
      if (!cmd) return;

      // If in command mode and suggestions exist, complete instead
      if (isCommandMode && displaySuggestions.length > 0) {
        const lastToken = cmd.split(/\s+/).pop() || "";
        const isPartial = displaySuggestions.some(
          (s) =>
            s.toLowerCase().startsWith(lastToken.toLowerCase()) &&
            s !== lastToken &&
            !s.startsWith("<") &&
            !s.startsWith("["),
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
          applyCompletion(getDataValue(dataCompletions[selectedDataIndex]));
          return;
        }
        if (!/^[0-9a-f]{8,}$/i.test(lastToken)) {
          applyCompletion(getDataValue(dataCompletions[0]));
          return;
        }
      }

      // Submit
      value = "";
      suggestions = [];
      hints = [];
      dataCompletions = [];
      if (onSubmit) onSubmit(cmd);
    }
  }

  function handlePaste(e) {
    // If pasting something starting with !, switch to command mode (handled by input event)
  }

  function handleTextareaClick() {
    // Clicking on the textarea refocuses it (already focused)
  }

</script>

<div class="chat-input" class:centered>
  <div class="input-area">
    <textarea
      bind:this={textareaEl}
      class="input-field"
      class:command-mode={isCommandMode}
      {placeholder}
      bind:value
      oninput={handleInput}
      onkeydown={handleKeydown}
      onpaste={handlePaste}
      onpointerdown={handleTextareaClick}
      rows="1"
      aria-label="Message input"
      autofocus
    ></textarea>
    <span class="mode-badge" class:active={isCommandMode}>
      {isCommandMode ? "CMD" : "CHAT"}
    </span>
  </div>

  <!-- Autocomplete dropdown -->
  {#if showSuggestions}
    <div class="suggestions" class:above={!centered}>
      {#each displaySuggestions as suggestion, i}
        <button
          class="suggestion"
          class:selected={i === selectedSuggestion}
          onmousedown={(e) => {
            e.preventDefault();
            applyCompletion(suggestion);
          }}
        >
          <span class="suggestion-text">{suggestion}</span>
          {#if displayHints[i]}
            <span class="hint-text">{displayHints[i]}</span>
          {/if}
        </button>
      {/each}
      {#each dataCompletions as dc, i}
        <button
          class="suggestion"
          class:selected={i === selectedDataIndex}
          onmousedown={(e) => {
            e.preventDefault();
            applyCompletion(getDataValue(dc));
          }}
        >
          <span class="suggestion-text">{getDataLabel(dc)}</span>
          <span class="hint-text">{dc.value ? "" : dc.label}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .chat-input {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
    transition: all 0.3s ease;
  }
  .chat-input.centered {
    justify-content: center;
    flex: 1;
  }
  .input-area {
    position: relative;
    width: 100%;
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
  }
  .input-field {
    flex: 1;
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 12px;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.95rem;
    padding: 0.75rem 1rem;
    outline: none;
    resize: none;
    line-height: 1.5;
    max-height: 200px;
    overflow-y: auto;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input-field:focus {
    border-color: #7c7c9a;
    box-shadow: 0 0 0 2px rgba(124, 124, 154, 0.2);
  }
  .input-field.command-mode {
    border-color: #5a8a5a;
    box-shadow: 0 0 0 2px rgba(90, 138, 90, 0.15);
  }
  .input-field::placeholder {
    color: #555;
  }
  .mode-badge {
    position: absolute;
    top: -8px;
    right: 8px;
    font-family: monospace;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 1px 6px;
    border-radius: 4px;
    background: #2a2a3e;
    color: #5a5a7a;
    border: 1px solid #333;
    transition: all 0.15s;
  }
  .mode-badge.active {
    background: #1a3a1a;
    color: #6aaa6a;
    border-color: #3a6a3a;
  }

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
  .suggestions.above {
    margin-top: 0;
    margin-bottom: 4px;
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

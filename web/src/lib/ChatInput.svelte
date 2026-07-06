<script>
  import { commandTree } from "./commandTree.js";
  import { getCompletions, getDataCompletionsFromCache } from "./commandEngine.js";
  import { parseCommand, hasTrailingSpace } from "./parser.js";
  import { popup } from "./popupStore.svelte.js";
  import { history } from "./commandHistory.svelte.js";
  import ChatSuggestions from "./ChatSuggestions.svelte";

  let {
    onSubmit,
    placeholder = "Ask anything in natural language or type ! for commands",
    centered = true,
  } = $props();

  let value = $state("");
  let suggestions = $state([]);
  let hints = $state([]);
  let dataCompletions = $state([]);
  let positionals = $state([]);
  let selectedSuggestion = $state(-1);
  let selectedDataIndex = $state(-1);
  let isCommandMode = $state(false);
  let textareaEl = $state(null);

  // Track if we have any interactive content in the dropdown
  let hasInteractiveItems = $derived(
    suggestions.length > 0 || dataCompletions.length > 0,
  );

  let showSuggestions = $derived(
    (isCommandMode && hasInteractiveItems) || positionals.length > 0,
  );

  // When data completions exist, hide flag suggestions to reduce clutter.
  // Only the tracker (positionals) + data completions are shown.
  let displaySuggestions = $derived(
    dataCompletions.length > 0 ? [] : suggestions,
  );
  let displayHints = $derived(
    dataCompletions.length > 0 ? [] : hints,
  );

  // Check if input starts with ! → command mode
  function checkCommandMode() {
    isCommandMode = value.startsWith("!");
    if (!isCommandMode) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
    }
  }

  function updateSuggestions() {
    if (!isCommandMode) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    const result = getCompletions(value);
    suggestions = result.completions;
    hints = result.hints;
    positionals = result.positionals;
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

      // 2. Check flags for uuidSource — user is typing or has completed a flag
      //    that expects a value from the cache (e.g. --folder).
      if (dataCompletions.length === 0 && result.node.flags) {
        // 2a. Partial flag name: user typed "--fol" — match via partial
        if (partial.startsWith("--")) {
          const partialFlagName = partial.slice(2);
          for (const f of result.node.flags) {
            if (f.uuidSource && f.name.startsWith(partialFlagName)) {
              dataCompletions = getDataCompletionsFromCache(popup.cache, f.uuidSource);
              break;
            }
          }
        }
        // 2b. Completed flag with empty value: "--folder " → needs a value
        if (dataCompletions.length === 0) {
          for (const f of result.node.flags) {
            if (f.uuidSource && f.name in flags && flags[f.name] === "") {
              dataCompletions = getDataCompletionsFromCache(popup.cache, f.uuidSource);
              break;
            }
          }
        }
        // 2c. Comma continuation: "--folder INBOX," → add another
        if (dataCompletions.length === 0) {
          for (const f of result.node.flags) {
            if (f.uuidSource && f.name in flags && flags[f.name].endsWith(",")) {
              const allItems = getDataCompletionsFromCache(popup.cache, f.uuidSource);
              if (allItems.length > 0) {
                const enteredValues = flags[f.name]
                  .split(",")
                  .map((v) => v.trim().toLowerCase())
                  .filter((v) => v.length > 0);
                dataCompletions = allItems.filter(
                  (dc) => !enteredValues.includes((dc.value || "").toLowerCase()),
                );
              }
              break;
            }
          }
        }
      }

      if (dataCompletions.length > 0) {
        const paramTokens = effectiveTokens.slice(cmdTokens);
        const usedValues = new Set(paramTokens.map(t => t.toLowerCase()));
        dataCompletions = dataCompletions.filter((dc) => {
          const insertVal = (dc.value || dc.uuid?.slice(0, 8) || "").toLowerCase();
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

  function autoResize() {
    if (!textareaEl) return;
    textareaEl.style.height = "auto";
    textareaEl.style.height = Math.min(textareaEl.scrollHeight, 200) + "px";
  }

  function handleInput() {
    autoResize();
    checkCommandMode();
    if (isCommandMode) updateSuggestions();
  }

  /** Get the text to insert when a data completion is selected. */
  function getDataValue(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
  }

  /** Get the display text for a data completion item. */
  function getDataLabel(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
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
    positionals = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
    requestAnimationFrame(() => updateSuggestions());
  }

  function handleKeydown(e) {
    // Escape: close suggestions, or blur input
    if (e.key === "Escape") {
      if (showSuggestions) {
        suggestions = [];
        hints = [];
        dataCompletions = [];
        positionals = [];
        return;
      }
      // Blur the textarea to exit input editing, and stop propagation
      // to prevent TabView's Escape handler from also closing a tab.
      textareaEl?.blur();
      e.stopPropagation();
      return;
    }

    // Tab: autocomplete
    if (e.key === "Tab" && hasInteractiveItems) {
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

    // Arrow keys: navigate suggestions OR command history
    if (e.key === "ArrowUp") {
      if (hasInteractiveItems) {
        e.preventDefault();
        if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
          selectedDataIndex = Math.max(0, selectedDataIndex - 1);
        } else if (displaySuggestions.length > 0) {
          selectedSuggestion = Math.max(0, selectedSuggestion - 1);
        }
        return;
      }
      // No suggestions → navigate command history
      e.preventDefault();
      const cmd = history.back();
      if (cmd) {
        value = cmd;
        checkCommandMode();
        requestAnimationFrame(() => updateSuggestions());
      }
      return;
    }

    if (e.key === "ArrowDown") {
      if (hasInteractiveItems) {
        e.preventDefault();
        if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
          selectedDataIndex = Math.min(dataCompletions.length - 1, selectedDataIndex + 1);
        } else if (displaySuggestions.length > 0) {
          selectedSuggestion = Math.min(displaySuggestions.length - 1, selectedSuggestion + 1);
        }
        return;
      }
      // No suggestions → navigate command history
      e.preventDefault();
      const cmd = history.forward();
      value = cmd;
      checkCommandMode();
      requestAnimationFrame(() => updateSuggestions());
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
      history.push(cmd);
      value = "";
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
      if (onSubmit) onSubmit(cmd);
    }
  }

  function handleFocus() {
    window.dispatchEvent(new CustomEvent("input-focus-changed", { detail: { focused: true } }));
  }

  function handleBlur() {
    window.dispatchEvent(new CustomEvent("input-focus-changed", { detail: { focused: false } }));
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
    <!-- svelte-ignore a11y_autofocus -->
    <textarea
      bind:this={textareaEl}
      class="input-field"
      class:command-mode={isCommandMode}
      {placeholder}
      bind:value
      oninput={handleInput}
      onkeydown={handleKeydown}
      onfocus={handleFocus}
      onblur={handleBlur}
      onpaste={handlePaste}
      onpointerdown={handleTextareaClick}
      aria-label="Message input"
      autofocus
    ></textarea>
  </div>

  <!-- Autocomplete dropdown -->
  <ChatSuggestions
    suggestions={displaySuggestions}
    {dataCompletions}
    hints={displayHints}
    {positionals}
    {selectedSuggestion}
    {selectedDataIndex}
    {isCommandMode}
    {showSuggestions}
    onSelect={applyCompletion}
  />
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
    border: 1px solid #555;
    border-radius: 14px;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 0.95rem;
    padding: 0.85rem 1rem;
    outline: none;
    resize: none;
    line-height: 1.6;
    min-height: 52px;
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
</style>

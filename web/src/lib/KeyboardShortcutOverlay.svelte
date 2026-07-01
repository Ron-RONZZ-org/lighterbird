<script>
  import { getAllShortcuts } from "./keyboardShortcuts.svelte.js";

  let { scope = "global", onDismiss = () => {} } = $props();

  /** Flatten all registered shortcuts into the expected display format. */
  let shortcuts = $derived(getAllShortcuts());

  function handleKeydown(e) {
    if (e.key === "Escape") {
      onDismiss();
      e.preventDefault();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="overlay" onclick={onDismiss} role="dialog" aria-label="Keyboard shortcuts" tabindex="0">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="document">
    <h3>Keyboard Shortcuts</h3>
    <p class="hint">Press <kbd>h</kbd> or <kbd>Esc</kbd> to close</p>

    {#each shortcuts as group}
      <div class="group">
        <h4>{group.category}</h4>
        {#each group.keys as shortcut}
          <div class="row">
            <span class="key">
              {#each shortcut.key.split(" / ") as part, i}
                {#if i > 0}<span class="sep"> / </span>{/if}
                <kbd>{part}</kbd>
              {/each}
            </span>
            <span class="desc">{shortcut.desc}</span>
          </div>
        {/each}
      </div>
    {/each}
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
    min-width: 420px;
    max-width: 520px;
    max-height: 80vh;
    overflow-y: auto;
    font-family: monospace;
    color: #e0e0e0;
  }

  h3 {
    margin: 0 0 0.2rem;
    font-size: 1rem;
    font-weight: 600;
  }

  .hint {
    color: var(--clr-muted);
    font-size: 0.75rem;
    margin-bottom: 1rem;
  }
  .hint kbd {
    display: inline-block;
    padding: 1px 4px;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: var(--clr-kbd);
    font-size: 0.7rem;
  }

  .group {
    margin-bottom: 1rem;
  }
  .group:last-child {
    margin-bottom: 0;
  }

  h4 {
    margin: 0 0 0.4rem;
    font-size: 0.78rem;
    color: var(--clr-sub);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .row {
    display: flex;
    gap: 1rem;
    padding: 0.2rem 0;
    font-size: 0.82rem;
  }

  .key {
    min-width: 12rem;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .key kbd {
    display: inline-block;
    padding: 1px 5px;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: #ddd;
    font-size: 0.75rem;
  }
  .key .sep {
    color: var(--clr-dim);
    font-size: 0.7rem;
  }

  .desc {
    color: #aaa;
  }
</style>

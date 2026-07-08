<script>
  /**
   * ConfirmToolDialog — Human-in-the-loop approval for LLM tool calls.
   *
   * Shows a list of pending write/destructive operations the LLM wants to
   * perform.  The user can approve or reject each one individually, or
   * use the "Approve All" / "Reject All" buttons.
   */
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    batch = [],
    message = "",
    onConfirm = () => {},
    onDismiss = () => {},
  } = $props();

  let decisions = $state({});
  let overlay;
  let focusBtn;

  $effect(() => {
    import("svelte").then(({ tick }) => tick().then(() => focusBtn?.focus()));
  });

  const trapKeydown = createDialogTrap(() => overlay, (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitDecisions();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onDismiss();
    }
  });

  function toggle(index, value) {
    decisions = { ...decisions, [index]: value };
  }

  function approveAll() {
    const all = {};
    for (let i = 0; i < batch.length; i++) {
      all[i] = true;
    }
    decisions = all;
    submitDecisions();
  }

  function rejectAll() {
    const all = {};
    for (let i = 0; i < batch.length; i++) {
      all[i] = false;
    }
    decisions = all;
    submitDecisions();
  }

  function submitDecisions() {
    // Build decisions map — only include tools the user explicitly decided on
    const decs = {};
    for (const [idx, val] of Object.entries(decisions)) {
      decs[idx] = val;
    }
    onConfirm(decs);
  }

  function decidedCount() {
    return Object.keys(decisions).length;
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Tool confirmation"
     onclick={onDismiss} onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="confirm-box wide" onclick={(e) => e.stopPropagation()}>
    <h3 class="confirm-title">LLM Tool Confirmation</h3>

    {#if message}
      <div class="confirm-message">{@html message}</div>
    {/if}

    <div class="tool-list">
      {#each batch as tool, i}
        <div class="tool-item" class:decided={i in decisions}>
          <div class="tool-info">
            <code class="tool-path">!{tool.tokens.join(" ")}</code>
            {#if tool.description}
              <span class="tool-desc">{tool.description}</span>
            {/if}
            {#if tool.flags && Object.keys(tool.flags).length > 0}
              <span class="tool-flags">
                {#each Object.entries(tool.flags) as [key, val]}
                  <span class="flag-badge">--{key}={val}</span>
                {/each}
              </span>
            {/if}
          </div>
          <div class="tool-actions">
            {#if i in decisions}
              <span class="decision-badge" class:approved={decisions[i]} class:rejected={!decisions[i]}>
                {decisions[i] ? "Approved" : "Rejected"}
              </span>
            {:else}
              <button class="btn btn-sm btn-primary" onclick={() => toggle(i, true)}>Approve</button>
              <button class="btn btn-sm btn-danger" onclick={() => toggle(i, false)}>Reject</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    <div class="bulk-actions">
      <button class="btn btn-primary" onclick={approveAll}>Approve All</button>
      <button class="btn btn-danger" onclick={rejectAll}>Reject All</button>
    </div>

    <div class="dialog-actions">
      <button class="btn btn-primary" onclick={submitDecisions}
              disabled={decidedCount() === 0} bind:this={focusBtn}>
        Submit Decisions ({decidedCount()}/{batch.length})
      </button>
      <button class="btn" onclick={onDismiss}>Cancel All</button>
    </div>
  </div>
</div>

<style>
  .confirm-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5); display: flex; align-items: center;
    justify-content: center; z-index: 1000;
  }
  .confirm-box {
    background: var(--bg-primary, #fff); border-radius: 8px;
    padding: 1.5rem; max-width: 640px; width: 90%;
    box-shadow: 0 4px 24px rgba(0,0,0,0.2);
  }
  .confirm-box.wide {
    max-width: 800px;
  }
  .confirm-title {
    margin: 0 0 0.75rem; font-size: 1.1rem;
  }
  .confirm-message {
    margin-bottom: 1rem; font-size: 0.9rem;
    line-height: 1.5; color: var(--text-secondary, #555);
  }
  .tool-list {
    max-height: 400px; overflow-y: auto;
    margin-bottom: 1rem; border: 1px solid var(--border, #ddd);
    border-radius: 6px;
  }
  .tool-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--border, #eee);
    gap: 0.5rem;
  }
  .tool-item:last-child { border-bottom: none; }
  .tool-item.decided { background: var(--bg-highlight, #f8f9fa); }
  .tool-info {
    flex: 1; display: flex; flex-direction: column; gap: 0.2rem;
    min-width: 0;
  }
  .tool-path { font-size: 0.85rem; font-weight: 600; }
  .tool-desc { font-size: 0.8rem; color: var(--text-secondary, #666); }
  .tool-flags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .flag-badge {
    font-size: 0.7rem; background: var(--bg-tertiary, #eee);
    padding: 0.1rem 0.4rem; border-radius: 3px;
    color: var(--text-secondary, #666);
  }
  .tool-actions {
    display: flex; gap: 0.3rem; align-items: center;
    flex-shrink: 0;
  }
  .decision-badge {
    font-size: 0.75rem; padding: 0.15rem 0.5rem;
    border-radius: 3px; font-weight: 600;
  }
  .decision-badge.approved { background: #d4edda; color: #155724; }
  .decision-badge.rejected { background: #f8d7da; color: #721c24; }
  .bulk-actions {
    display: flex; gap: 0.5rem; margin-bottom: 0.75rem;
  }
  .dialog-actions {
    display: flex; gap: 0.5rem; justify-content: flex-end;
    border-top: 1px solid var(--border, #eee); padding-top: 0.75rem;
  }
  .btn { padding: 0.4rem 1rem; border-radius: 4px; border: 1px solid transparent;
         cursor: pointer; font-size: 0.85rem; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: var(--accent, #0066cc); color: #fff; }
  .btn-danger { background: #dc3545; color: #fff; }
  .btn-sm { padding: 0.25rem 0.6rem; font-size: 0.8rem; }
</style>

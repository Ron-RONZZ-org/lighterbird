<script>
  import { tick } from "svelte";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    title = "Confirm",
    message = "Are you sure?",
    confirmText = "Confirm",
    variant = "danger",
    onConfirm = () => {},
    onDismiss = () => {},
  } = $props();
  let confirmBtn;
  let overlay;

  // Steal focus from whatever was focused (e.g. the Delete button that triggered this dialog)
  $effect(() => {
    tick().then(() => confirmBtn?.focus());
  });

  const trapKeydown = createDialogTrap(() => overlay, (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      onConfirm();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onDismiss();
    }
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label={title}
     onclick={onDismiss} onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
    {#if title}
      <h3 class="confirm-title">{title}</h3>
    {/if}
    <p>{message}</p>
    <div class="actions">
      <button class="btn {variant}" onclick={onConfirm} bind:this={confirmBtn}>{confirmText}</button>
      <button class="btn" onclick={onDismiss}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .confirm-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .confirm-box {
    background: #22223a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    text-align: center;
    font-family: system-ui, monospace;
    max-width: 420px;
  }
  .confirm-title {
    color: #e0a0a0;
    font-size: 1rem;
    margin-bottom: 0.6rem;
    font-weight: 600;
  }
  .confirm-box p {
    margin-bottom: 1rem;
    color: #e0e0e0;
    font-size: 0.89rem;
    line-height: 1.5;
  }
  .actions {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
  }
  .btn {
    padding: 0.4rem 1rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 0.85rem;
    font-family: monospace;
    transition: background 0.1s;
  }
  .btn:hover { background: #3a3a5e; }
  .btn.danger { background: #6b2020; border-color: #8b3030; }
  .btn.danger:hover { background: #8b3030; }
  .btn.warning { background: #6b5a20; border-color: #8b7a30; }
  .btn.warning:hover { background: #8b7a30; }
</style>

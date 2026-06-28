<script>
  import { tick } from "svelte";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let { message = "Confirm?", onConfirm = () => {}, onDismiss = () => {} } = $props();
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
<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Confirm"
     onclick={onDismiss} onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
    <p>{message}</p>
    <div class="actions">
      <button class="btn danger" onclick={onConfirm} bind:this={confirmBtn}>Confirm</button>
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
  }
  .confirm-box p {
    margin-bottom: 1rem;
    color: #e0e0e0;
    font-size: 0.95rem;
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
</style>

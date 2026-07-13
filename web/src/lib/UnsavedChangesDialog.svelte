<script>
  /**
   * UnsavedChangesDialog — three-way "Save / Discard / Cancel" dialog
   * shown when the user tries to close a dirty form tab.
   *
   * If ``onSave`` is provided (form supports draft-saving), three buttons
   * are shown.  Otherwise only Discard and Cancel are shown.
   */

  import { tick } from "svelte";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    title = "Unsaved Changes",
    message = "You have unsaved changes. What would you like to do?",
    saveText = "Save Draft",
    discardText = "Discard",
    cancelText = "Cancel",
    onSave = null,    // () => void — if null, hide the Save button
    onDiscard = () => {},
    onCancel = () => {},
  } = $props();

  let focusBtn;
  let overlay;

  $effect(() => {
    tick().then(() => focusBtn?.focus());
  });

  const trapKeydown = createDialogTrap(() => overlay, (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      if (onSave) onSave();
      else onDiscard();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onCancel();
    }
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="unsaved-overlay" role="alertdialog" aria-modal="true" aria-label={title}
     onclick={onCancel} onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="unsaved-box" onclick={(e) => e.stopPropagation()}>
    {#if title}
      <h3 class="unsaved-title">{title}</h3>
    {/if}
    <p class="unsaved-message">{message}</p>
    <div class="actions">
      {#if onSave}
        <button class="btn btn-save" onclick={onSave} bind:this={focusBtn}>{saveText}</button>
      {/if}
      <button class="btn btn-discard" class:btn-only-two={!onSave}
        onclick={onDiscard} bind:this={onSave ? undefined : focusBtn}>{discardText}</button>
      <button class="btn btn-cancel" onclick={onCancel}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .unsaved-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 110;
  }
  .unsaved-box {
    background: #22223a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    text-align: center;
    font-family: system-ui, monospace;
    max-width: 420px;
  }
  .unsaved-title {
    color: #e0a0a0;
    font-size: 1rem;
    margin-bottom: 0.6rem;
    font-weight: 600;
  }
  .unsaved-message {
    margin-bottom: 1rem;
    color: #e0e0e0;
    font-size: 0.89rem;
    line-height: 1.5;
  }
  .actions {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
    flex-wrap: wrap;
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
  .btn-save { background: #1a3a2a; border-color: #3a6a4a; color: #6abc6a; }
  .btn-save:hover { background: #2a4a3a; }
  .btn-discard { background: #4a1a1a; border-color: #6a3a3a; color: #d08080; }
  .btn-discard:hover { background: #5a2a2a; }
  .btn-discard.btn-only-two { background: #6b2020; border-color: #8b3030; color: #f0a0a0; }
  .btn-discard.btn-only-two:hover { background: #8b3030; }
  .btn-cancel { background: #2a2a3e; border-color: #444; color: #b0b0c0; }
  .btn-cancel:hover { background: #3a3a5e; color: #e0e0e0; }
</style>

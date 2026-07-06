<script>
  /**
   * DropdownPanel.svelte — Reusable backdrop + panel overlay for command dropdowns.
   *
   * Props:
   *   show     — whether the overlay is visible
   *   onClose  — callback when backdrop is clicked
   */
  let { show = false, onClose = () => {} } = $props();
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="dropdown-backdrop" onclick={onClose} role="presentation"></div>
  <div class="dropdown-panel">
    <slot />
  </div>
{/if}

<style>
  .dropdown-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: transparent;
  }
  .dropdown-panel {
    position: absolute;
    top: 2.4rem;
    left: 0.3rem;
    z-index: 300;
    background: #1e1e32;
    border: 1px solid #4a4a6a;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    max-height: 70vh;
    overflow-y: auto;
  }
</style>

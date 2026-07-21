<script>
  /**
   * ActionBanner — dismissable/undoable banner for email operations.
   *
   * Displays a message with an optional action button (e.g. "Undo").
   * Auto-dismisses after the configured duration.
   *
   * Uses the module-level actionBannerStore (singleton state).
   */
  import { actionBanner } from "./actionBannerStore.svelte.js";

  let visible = $derived(actionBanner.visible);
  let message = $derived(actionBanner.message);
  let actionLabel = $derived(actionBanner.actionLabel);
  let hasAction = $derived(actionBanner.onAction !== null);
</script>

{#if visible}
  <div class="action-banner" role="alert" class:has-action={hasAction}>
    <span class="banner-message">{message}</span>
    <span class="banner-actions">
      {#if hasAction}
        <button class="banner-btn" onclick={() => actionBanner.triggerAction()}>
          {actionLabel}
        </button>
      {/if}
      <button class="banner-close" onclick={() => actionBanner.hide()} aria-label="Dismiss">✕</button>
    </span>
  </div>
{/if}

<style>
  .action-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.5rem 1rem;
    background: #1e3a2e;
    border-bottom: 1px solid #3a6a4a;
    color: #b0e0c0;
    font-family: monospace;
    font-size: 0.82rem;
    animation: bannerSlideIn 0.2s ease;
    flex-shrink: 0;
  }
  .action-banner.has-action {
    background: #2a3a2e;
  }
  .banner-message {
    flex: 1;
    min-width: 0;
  }
  .banner-actions {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
  }
  .banner-btn {
    padding: 0.2rem 0.6rem;
    border: 1px solid #4a8a5a;
    border-radius: 4px;
    background: transparent;
    color: #7fdb7f;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    transition: background 0.1s;
    white-space: nowrap;
  }
  .banner-btn:hover {
    background: #1e4a2e;
  }
  .banner-close {
    background: none;
    border: none;
    color: #6a8a7a;
    font-size: 0.85rem;
    cursor: pointer;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
  }
  .banner-close:hover {
    color: #b0e0c0;
    background: #2a4a3a;
  }
  @keyframes bannerSlideIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>

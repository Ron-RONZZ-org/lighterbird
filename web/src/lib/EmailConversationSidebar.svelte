<script>
  import { tabStore } from "./tabStore.svelte.js";

  let {
    show = false,
    conversation = [],
    loading = false,
    currentUuid = "",
    onClose = () => {},
  } = $props();

  function openConversationMsg(convMsg) {
    tabStore.open("email", convMsg.subject || "(no subject)", convMsg, {
      idKey: `email-${convMsg.uuid}`,
      replaceable: false,
    });
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
  <div class="conv-overlay" role="presentation" onclick={onClose}>
    <!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
    <div class="conv-panel" role="presentation" onclick={(e) => e.stopPropagation()}>
      <div class="conv-header">
        <span>Thread</span>
        <button class="close-btn" onclick={onClose}>✕</button>
      </div>
      <div class="conv-list">
        {#if loading}
          <p class="conv-loading">Loading…</p>
        {:else if conversation.length === 0}
          <p class="conv-empty">No other messages in this thread.</p>
        {:else}
          {#each conversation as cm}
            <div
              class="conv-item"
              class:active={cm.uuid === currentUuid}
              role="button"
              tabindex="0"
              onclick={() => openConversationMsg(cm)}
              onkeydown={(e) => { if (e.key === "Enter") openConversationMsg(cm); }}
            >
              <span class="conv-from">{(cm.from || "").slice(0, 24)}</span>
              <span class="conv-subject">{(cm.subject || "").slice(0, 32)}</span>
              <span class="conv-date">{cm.received_at || ""}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .conv-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 100;
    display: flex;
    justify-content: flex-end;
  }
  .conv-panel {
    width: 340px;
    max-width: 90vw;
    background: #1e1e32;
    border-left: 1px solid #444;
    display: flex;
    flex-direction: column;
    animation: slideIn 0.15s ease;
  }
  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }
  .conv-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid #333;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--clr-sub);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--clr-sub);
    font-size: 1rem;
    cursor: pointer;
    padding: 2px 4px;
  }
  .close-btn:hover { color: #fff; }
  .conv-list {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
  }
  .conv-item {
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid #2a2a3e;
    transition: background 0.1s;
    font-family: monospace;
    font-size: 0.8rem;
  }
  .conv-item:hover { background: #2a2a44; }
  .conv-item.active {
    background: #252540;
    border-left: 3px solid #7c7c9a;
  }
  .conv-from { color: #e0e0e0; display: block; font-weight: 600; }
  .conv-subject { color: #b0b0c0; display: block; }
  .conv-date { color: var(--clr-muted); display: block; font-size: 0.7rem; margin-top: 2px; }
  .conv-loading, .conv-empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
    font-family: monospace;
    font-size: 0.8rem;
  }
</style>

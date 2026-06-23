<script>
  import { tabStore } from "./tabStore.svelte.js";
  import LoadingPopup from "./LoadingPopup.svelte";
  import StatusPopup from "./StatusPopup.svelte";
  import EmailPopup from "./EmailPopup.svelte";
  import EmailViewTab from "./EmailViewTab.svelte";
  import EventsPopup from "./EventsPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";

  /** Map tab types to content components. */
  const CONTENT = {
    status: StatusPopup,
    email: EmailViewTab,
    events: EventsPopup,
    error: ErrorPopup,
    help: HelpPopup,
    loading: LoadingPopup,
  };

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (tabStore.active && tabStore.active.closable) {
        tabStore.close(tabStore.active.id);
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if tabStore.tabs.length === 0}
  <div class="empty-state">
    <p class="empty-hint">Type a command to get started</p>
  </div>
{:else}
  <div class="tab-view">
    {#if tabStore.active}
      <div class="tab-content" role="region" aria-label="Tab content">
        {#if tabStore.active.type === "loading"}
          <LoadingPopup message={tabStore.active.title} />
        {:else if tabStore.active.type === "status"}
          <StatusPopup data={tabStore.active.data} />
        {:else if tabStore.active.type === "email"}
          <EmailViewTab data={tabStore.active.data} tabId={tabStore.active.id} />
        {:else if tabStore.active.type === "events"}
          <EventsPopup data={tabStore.active.data} />
        {:else if tabStore.active.type === "error"}
          <ErrorPopup data={tabStore.active.data} />
        {:else if tabStore.active.type === "help"}
          <HelpPopup data={tabStore.active.data} />
        {:else}
          <StatusPopup data={tabStore.active.data} />
        {/if}
      </div>
    {/if}

    <!-- Tab bar at bottom -->
    {#if tabStore.count > 0}
      <div class="tab-bar" role="tablist" aria-label="Open tabs">
        {#each tabStore.tabs as tab, i}
          <button
            role="tab"
            class="tab"
            class:active={tab.id === tabStore.active?.id}
            onclick={() => tabStore.setActive(tab.id)}
            aria-selected={tab.id === tabStore.active?.id}
            title={tab.title}
          >
            <span class="tab-icon">{tabIcon(tab.type)}</span>
            <span class="tab-label">{truncate(tab.title, 20)}</span>
            {#if tab.closable}
              <span
                class="tab-close"
                role="button"
                tabindex="-1"
                onclick={(e) => { e.stopPropagation(); tabStore.close(tab.id); }}
                onkeydown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); tabStore.close(tab.id); }}}
              >✕</span>
            {/if}
          </button>
        {/each}
        <span class="tab-bar-spacer"></span>
      </div>
    {/if}
  </div>
{/if}

<script context="module">
  function tabIcon(type) {
    const icons = {
      status: "📋",
      email: "✉",
      events: "📅",
      error: "⚠",
      help: "?",
      loading: "⏳",
    };
    return icons[type] || "•";
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }
</script>

<style>
  .tab-view {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    animation: slideDown 0.12s ease;
  }
  @keyframes slideDown {
    from { max-height: 0; opacity: 0; }
    to { max-height: 60vh; opacity: 1; }
  }
  .tab-content {
    flex: 1;
    overflow-y: auto;
    background: #1e1e32;
    border: 1px solid #444;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    max-height: 55vh;
  }
  .tab-bar {
    display: flex;
    align-items: stretch;
    background: #16162a;
    border: 1px solid #444;
    border-top: none;
    border-radius: 0 0 8px 8px;
    overflow-x: auto;
    gap: 1px;
    min-height: 32px;
  }
  .tab {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    background: #1a1a2e;
    border: none;
    border-right: 1px solid #333;
    color: #7c7c9a;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
    flex-shrink: 0;
  }
  .tab:hover {
    background: #22223a;
    color: #e0e0e0;
  }
  .tab.active {
    background: #1e1e32;
    color: #e0e0e0;
    border-bottom: 2px solid #7c7c9a;
  }
  .tab-icon {
    font-size: 0.7rem;
    opacity: 0.7;
  }
  .tab-label {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tab-close {
    font-size: 0.65rem;
    padding: 1px 3px;
    border-radius: 3px;
    opacity: 0.5;
    transition: opacity 0.1s;
    line-height: 1;
  }
  .tab-close:hover {
    opacity: 1;
    background: #333;
  }
  .tab-bar-spacer {
    flex: 1;
    background: #1a1a2e;
  }
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 3rem;
  }
  .empty-hint {
    color: #5a5a7a;
    font-family: monospace;
    font-size: 0.9rem;
    font-style: italic;
  }
</style>

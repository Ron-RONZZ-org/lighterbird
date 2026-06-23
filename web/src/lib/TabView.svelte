<script>
  import { tabStore } from "./tabStore.svelte.js";
  import HomeTab from "./HomeTab.svelte";
  import LoadingPopup from "./LoadingPopup.svelte";
  import StatusPopup from "./StatusPopup.svelte";
  import EmailPopup from "./EmailPopup.svelte";
  import EmailViewTab from "./EmailViewTab.svelte";
  import EventsPopup from "./EventsPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (tabStore.active && tabStore.active.closable && !tabStore.isHome) {
        tabStore.close(tabStore.active.id);
      } else if (tabStore.isHome) {
        // On home tab, close the last result tab
        const resultTabs = tabStore.tabs.filter((t) => t.closable);
        if (resultTabs.length > 0) {
          tabStore.close(resultTabs[resultTabs.length - 1].id);
        }
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="tab-view">
  <!-- Tab content -->
  {#if tabStore.active}
    <div class="tab-content" role="region" aria-label="Tab content">
      {#if tabStore.isHome}
        <HomeTab />
      {:else if tabStore.active.type === "loading"}
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

  <!-- Tab bar (hidden when only home tab exists) -->
  {#if tabStore.count > 1}
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
          <span class="tab-label">{truncate(tab.title, 22)}</span>
          {#if tab.closable}
            <span
              class="tab-close"
              role="button"
              tabindex="-1"
              onclick={(e) => {
                e.stopPropagation();
                tabStore.close(tab.id);
              }}
              onkeydown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  tabStore.close(tab.id);
                }
              }}
            >✕</span>
          {/if}
        </button>
      {/each}
      <span class="tab-bar-spacer"></span>
    </div>
  {/if}
</div>

<script context="module">
  function tabIcon(type) {
    const icons = {
      home: "⌂",
      status: "📋",
      email: "✉",
      events: "📅",
      error: "⚠",
      help: "?",
      loading: "⏳",
      chat: "💬",
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
    height: 100%;
  }
  .tab-content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: #1a1a2e;
  }
  .tab-bar {
    display: flex;
    align-items: stretch;
    background: #16162a;
    border-top: 1px solid #333;
    overflow-x: auto;
    gap: 1px;
    min-height: 32px;
    flex-shrink: 0;
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
    max-width: 140px;
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
</style>

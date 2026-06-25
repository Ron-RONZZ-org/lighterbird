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
  import EmailListTab from "./EmailListTab.svelte";
  import JournalListTab from "./JournalListTab.svelte";
  import FormTab from "./FormTab.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";

  let showGlobalHelp = $state(false);
  let inputFocused = $state(false);

  // Track command input focus state for context-sensitive hints
  $effect(() => {
    function handler(e) {
      inputFocused = e.detail.focused;
    }
    window.addEventListener("input-focus-changed", handler);
    return () => window.removeEventListener("input-focus-changed", handler);
  });

  // Auto-focus command input when switching to home tab
  $effect(() => {
    if (tabStore.isHome) {
      // Small delay to let the DOM settle
      requestAnimationFrame(() => {
        window.dispatchEvent(new CustomEvent("focus-command-input"));
      });
    }
  });

  function handleKeydown(e) {
    // Escape — close current tab
    // Tabs with complex overlays (email-list) manage their own Escape;
    // they use 'q' or the close button to close.
    if (e.key === "Escape") {
      // Dismiss global help overlay first if open
      if (showGlobalHelp) {
        showGlobalHelp = false;
        return;
      }
      // When command input is focused on home tab, let ChatInput handle Escape (blur)
      if (tabStore.isHome && inputFocused) return;
      const type = tabStore.active?.type;
      if (type === "email-list") return; // self-managed Escape (dialogs, search, selection)
      if (tabStore.active && tabStore.active.closable && !tabStore.isHome) {
        tabStore.close(tabStore.active.id);
      } else if (tabStore.isHome) {
        const resultTabs = tabStore.tabs.filter((t) => t.closable);
        if (resultTabs.length > 0) {
          tabStore.close(resultTabs[resultTabs.length - 1].id);
        }
      }
      return;
    }

    // H / h — toggle help (global, or delegate to email-list)
    if (e.key === "h" || e.key === "H") {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      if (tabStore.active?.type === "email-list") {
        window.dispatchEvent(new CustomEvent("help-toggle"));
      } else {
        showGlobalHelp = !showGlobalHelp;
      }
      return;
    }

    // I / i — focus command input on home tab
    if ((e.key === "i" || e.key === "I") && tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      window.dispatchEvent(new CustomEvent("focus-command-input"));
      return;
    }

    // Q / q — close current tab (inert when typing in an input to avoid
    // accidental closes from someone inserting "q" in a text field)
    if ((e.key === "q" || e.key === "Q") && !tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      if (tabStore.active && tabStore.active.closable) {
        tabStore.close(tabStore.active.id);
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="tab-view">
  <!-- Tab content: HomeTab is always mounted (keeps conversation state) -->
  <div class="tab-content" class:active={tabStore.isHome} role="region" aria-label="Home tab">
    <HomeTab />
  </div>
  {#if tabStore.active && !tabStore.isHome}
    <div class="tab-content" class:active={true} role="region" aria-label="Tab content">
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
      {:else if tabStore.active.type === "email-list"}
        <EmailListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "journal-list"}
        <JournalListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "help"}
        <HelpPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "form"}
        <FormTab data={tabStore.active.data} />
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
      <span class="tab-hint" title="Keyboard shortcuts">
        {#if tabStore.isHome && !inputFocused}
          <kbd>i</kbd> focus
          <span class="hint-sep">·</span>
        {:else if tabStore.isHome && inputFocused}
          <kbd>Esc</kbd> blur
          <span class="hint-sep">·</span>
        {/if}
        <kbd>h</kbd> help
        {#if !tabStore.isHome}
          <span class="hint-sep">·</span>
          <kbd>q</kbd> <kbd>Esc</kbd> close
        {/if}
      </span>
    </div>
  {/if}

  {#if showGlobalHelp}
    <KeyboardShortcutOverlay scope="global" onDismiss={() => { showGlobalHelp = false; }} />
  {/if}
</div>

<script module>
  function tabIcon(type) {
    const icons = {
      home: "⌂",
      status: "📋",
      email: "✉",
      "email-list": "✉",
      "journal-list": "📓",
      events: "📅",
      error: "⚠",
      help: "?",
      loading: "⏳",
      chat: "💬",
      form: "✏",
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
    display: none;
    flex-direction: column;
    background: #1a1a2e;
  }
  .tab-content.active {
    display: flex;
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
    color: var(--clr-sub);
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
  .tab-hint {
    display: flex;
    align-items: center;
    gap: 3px;
    padding: 0 8px;
    font-size: 0.68rem;
    color: var(--clr-dim);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .tab-hint kbd {
    display: inline-block;
    padding: 1px 4px;
    font-size: 0.62rem;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: var(--clr-kbd);
  }
  .hint-sep {
    color: #444;
    margin: 0 2px;
  }
</style>

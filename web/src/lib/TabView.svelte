<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { dirtyFormStore } from "./dirtyFormStore.svelte.js";
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
  import JournalViewTab from "./JournalViewTab.svelte";
  import SieveListTab from "./SieveListTab.svelte";
  import ContactsListTab from "./ContactsListTab.svelte";
  import ContactViewTab from "./ContactViewTab.svelte";
  import TodoListTab from "./TodoListTab.svelte";
  import TodoViewTab from "./TodoViewTab.svelte";
  import CalendarEventsListTab from "./CalendarEventsListTab.svelte";
  import SieveEditorForm from "./SieveEditorForm.svelte";
  import ConfirmToolDialog from "./ConfirmToolDialog.svelte";

  /** Handle tool confirmation from a /* prompt command tab. */
  async function handleToolConfirm(tab, decisions) {
    try {
      const resp = await fetch("/api/v1/prompt-commands/execute/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: tab.data?.session_id,
          decisions,
        }),
      });
      if (!resp.ok) {
        tabStore.update(tab.id, {
          type: "error",
          data: { message: `Resume failed: HTTP ${resp.status}` },
        });
        return;
      }
      const result = await resp.json();
      if (result.type === "confirm_tool") {
        // Another round of approvals
        tabStore.update(tab.id, { type: "confirm_tool", data: result });
        return;
      }
      // Final result: show as chat or status
      if (result.type === "chat" && result.data?.html) {
        tabStore.update(tab.id, { type: "chat", data: result.data });
      } else {
        // Re-fetch the command to render properly
        tabStore.update(tab.id, { type: result.type || "status", title: result.title || "", data: result.data || result });
      }
    } catch (err) {
      tabStore.update(tab.id, {
        type: "error",
        data: { message: err.message || "Failed to resume" },
      });
    }
  }

  function handleToolDismiss(tab) {
    tabStore.close(tab.id);
  }
  import FormTab from "./FormTab.svelte";
  import LetterListTab from "./LetterListTab.svelte";
  import LetterViewTab from "./LetterViewTab.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";
  import SavedCommandsTab from "./SavedCommandsTab.svelte";

  /** Map of tab type → component constructor. */
  const TAB_COMPONENTS = {
    loading: LoadingPopup,
    status: StatusPopup,
    email: EmailViewTab,
    events: EventsPopup,
    error: ErrorPopup,
    "email-list": EmailListTab,
    "email-trash-list": EmailListTab,
    "email-draft-list": EmailListTab,
    "journal-list": JournalListTab,
    "journal-view": JournalViewTab,
    "contacts-list": ContactsListTab,
    "contact-view": ContactViewTab,
    "todo-list": TodoListTab,
    "todo-view": TodoViewTab,
    "calendar-events": CalendarEventsListTab,
    "sieve-list": SieveListTab,
    "sieve-editor": SieveEditorForm,
    "letter-list": LetterListTab,
    "letter-view": LetterViewTab,
    "saved-commands": SavedCommandsTab,
    templates: StatusPopup,
    help: HelpPopup,
    form: FormTab,
  };

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

  // Auto-focus command input when switching to home tab.
  // Directly query the DOM — avoids race conditions with event listeners.
  $effect(() => {
    if (tabStore.isHome) {
      requestAnimationFrame(() => {
        document.querySelector(".input-field")?.focus();
      });
    }
  });

  /** Close a tab, checking for unsaved changes first. */
  function handleCloseTab(tabId) {
    if (dirtyFormStore.isDirty(tabId)) {
      if (!confirm("You have unsaved changes. Discard them?")) return;
      dirtyFormStore.clear(tabId);
    }
    tabStore.close(tabId);
  }

  // Tab types that manage their own Escape (selection mode, search, dialogs)
  const LIST_TAB_TYPES = new Set([
    "email-list", "journal-list", "contacts-list", "todo-list",
    "calendar-events", "sieve-list", "letter-list",
  ]);

  function handleKeydown(e) {
    // Escape — context-sensitive: blur field → allow component → close tab
    if (e.key === "Escape") {
      // Level 1: If an input/textarea is focused, blur it
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable) {
        e.target.blur();
        e.preventDefault();
        return;
      }

      // Level 2: Dismiss global help overlay if open
      if (showGlobalHelp) {
        showGlobalHelp = false;
        e.preventDefault();
        return;
      }

      // Level 3: When command input is focused on home tab, let ChatInput handle Escape
      if (tabStore.isHome && inputFocused) return;

      // Level 4: List tabs manage their own Escape (selection mode exit, search close,
      // dialog dismiss). TabView's handler fires before the list tab's window handler,
      // so we return here and let the list tab process Escape first. The list tab's
      // handler will close the tab itself if Escape is not needed by any active UI state.
      const type = tabStore.active?.type;
      if (type && LIST_TAB_TYPES.has(type)) return;

      // Level 5: Close current tab
      if (tabStore.active && tabStore.active.closable && !tabStore.isHome) {
        handleCloseTab(tabStore.active.id);
        e.preventDefault();
      } else if (tabStore.isHome) {
        const resultTabs = tabStore.tabs.filter((t) => t.closable);
        if (resultTabs.length > 0) {
          const tab = resultTabs[resultTabs.length - 1];
          handleCloseTab(tab.id);
          e.preventDefault();
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
    // Direct DOM query avoids race conditions with event listeners.
    if ((e.key === "i" || e.key === "I") && tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      document.querySelector(".input-field")?.focus();
      return;
    }

    // Q / q — close current tab (inert when typing in an input to avoid
    // accidental closes from someone inserting "q" in a text field)
    if ((e.key === "q" || e.key === "Q") && !tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      if (tabStore.active && tabStore.active.closable) {
        handleCloseTab(tabStore.active.id);
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
      {:else if tabStore.active.type === "email-list" || tabStore.active.type === "email-trash-list" || tabStore.active.type === "email-draft-list"}
        <EmailListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "journal-list"}
        <JournalListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "journal-view"}
        <JournalViewTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "contacts-list"}
        <ContactsListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "contact-view"}
        <ContactViewTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "todo-list"}
        <TodoListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "todo-view"}
        <TodoViewTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "calendar-events"}
        <CalendarEventsListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "sieve-list"}
        <SieveListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "sieve-editor"}
        <SieveEditorForm data={tabStore.active.data} />
      {:else if tabStore.active.type === "letter-list"}
        <LetterListTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "letter-view"}
        <LetterViewTab data={tabStore.active.data} tabId={tabStore.active.id} />
      {:else if tabStore.active.type === "saved-commands"}
        <SavedCommandsTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "help"}
        <HelpPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "templates"}
        <StatusPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "confirm_tool"}
        <ConfirmToolDialog
          batch={tabStore.active.data?.batch || []}
          message={tabStore.active.data?.message || ""}
          onConfirm={(decisions) => handleToolConfirm(tabStore.active, decisions)}
          onDismiss={() => handleToolDismiss(tabStore.active)}
        />
      {:else if tabStore.active.type === "chat"}
        <StatusPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "form"}
        <FormTab data={tabStore.active.data} tabId={tabStore.active.id} />
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
                handleCloseTab(tab.id);
              }}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  handleCloseTab(tab.id);
                }
              }}
            >✕</span>
          {/if}
        </button>
      {/each}
      <span class="tab-bar-spacer"></span>
      <span class="tab-hint" title="Keyboard shortcuts">
        {#if tabStore.isHome}
          {#if inputFocused}
            <kbd>Esc</kbd> blur
          {:else}
            <kbd>i</kbd> input mode
          {/if}
          <span class="hint-sep">·</span>
        {/if}
        <kbd>h</kbd> help
        {#if !tabStore.isHome}
          <span class="hint-sep">·</span>
          {#if tabStore.active && LIST_TAB_TYPES.has(tabStore.active.type)}
            <kbd>q</kbd> close
          {:else}
            <kbd>q</kbd> <kbd>Esc</kbd> close
          {/if}
        {/if}
      </span>
    </div>
  {:else}
    <!-- Home-only hint strip — always visible when no result tabs -->
    <div class="home-hints">
      <span class="tab-hint" title="Keyboard shortcuts">
        {#if inputFocused}
          <kbd>Esc</kbd> blur
        {:else}
          <kbd>i</kbd> input mode
        {/if}
        <span class="hint-sep">·</span>
        <kbd>h</kbd> help
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
      "email-trash-list": "🗑",
      "email-draft-list": "✎",
      "journal-list": "📓",
      "journal-view": "📓",
      "contacts-list": "👤",
      "contact-view": "👤",
      "todo-list": "☐",
      "calendar-events": "📅",
      "sieve-list": "🔍",
      "sieve-editor": "✏",
      "saved-commands": "⚡",
      "templates": "📋",
      "letter-list": "✉",
      "letter-view": "✉",
      events: "📅",
      error: "⚠",
      help: "?",
      loading: "⏳",
      chat: "💬",
      "confirm_tool": "🔐",
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
  }
  .tab-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
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

  .home-hints {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px 0;
    background: #16162a;
    border-top: 1px solid #2a2a3e;
    flex-shrink: 0;
    min-height: 24px;
  }
</style>

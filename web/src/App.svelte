<script>
  import CommandBar from "./lib/CommandBar.svelte";
  import PopupOverlay from "./lib/PopupOverlay.svelte";
  import { popup } from "./lib/popupStore.svelte.js";
  import { tabStore } from "./lib/tabStore.svelte.js";
  import { execute } from "./lib/commandExecutor.js";
  import { findNode } from "./lib/commandTree.js";
  import { parseCommand } from "./lib/parser.js";
  import { email, calendar, contacts, todo, journal } from "./lib/api.js";
  import ComposeEmail from "./lib/ComposeEmail.svelte";
  import EventForm from "./lib/EventForm.svelte";

  let isLoading = $state(false);
  let activeForm = $state(null);
  let formOnSubmit = $state(null);

  /** Global keyboard shortcuts. */
  function handleGlobalKeydown(e) {
    // Alt+1/2/3/4 — switch tabs
    if (e.altKey && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        tabStore.setActiveIndex(num - 1);
        return;
      }
    }

    // Ctrl+R — Reply (only when email tab is active)
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 'r') {
      const active = tabStore.active;
      if (active && active.type === 'email') {
        e.preventDefault();
        // Dispatch a custom event that EmailViewTab can listen for
        window.dispatchEvent(new CustomEvent('email-action', { detail: { action: 'reply' } }));
        return;
      }
    }

    // Ctrl+Shift+R — Reply All
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'R') {
      const active = tabStore.active;
      if (active && active.type === 'email') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('email-action', { detail: { action: 'reply-all' } }));
        return;
      }
    }

    // Ctrl+L — Forward
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === 'l') {
      const active = tabStore.active;
      if (active && active.type === 'email') {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('email-action', { detail: { action: 'forward' } }));
        return;
      }
    }
  }

  /** Detect whether a command string opens a persistent live view. */
  function detectPersistentType(input) {
    const t = input.trim();
    if (/^!(email\s+)?account\s+list\s*$/i.test(t)) return "accounts";
    if (/^!(calendar\s+)?account\s+list\s*$/i.test(t)) return "calendars";
    if (/^!contacts\s+list\s*$/i.test(t)) return "contacts";
    if (/^!todo\s+list\s*$/i.test(t)) return "todos";
    if (/^!journal\s+list\s*$/i.test(t)) return "journal";
    return null;
  }

  /** Check whether a command string mutates the given persistent data type. */
  function isRelevantMutation(input, dataType) {
    if (!dataType) return false;
    const t = input.trim();
    if (dataType === "accounts" && /^!(email\s+)?account\s+(add|remove|modify)\b/i.test(t)) return true;
    if (dataType === "calendars" && /^!(calendar\s+)?account\s+(add|remove|modify|sync)\b/i.test(t)) return true;
    if (dataType === "contacts" && /^!contacts\s+(add|remove|modify)\b/i.test(t)) return true;
    if (dataType === "todos" && /^!todo\s+(add|remove|modify|done)\b/i.test(t)) return true;
    if (dataType === "journal" && /^!journal\s+write\b/i.test(t)) return true;
    return false;
  }

  /** Re-fetch data for the current persistent popup and update it. */
  async function refreshPersistentPopup() {
    try {
      let data;
      const dt = popup.persistentDataType;
      if (dt === "accounts") {
        data = await email.listAccounts();
      } else if (dt === "calendars") {
        data = await calendar.listCalendars();
      } else if (dt === "contacts") {
        data = await contacts.list();
      } else if (dt === "todos") {
        data = await todo.list();
      } else if (dt === "journal") {
        data = await journal.list();
      } else {
        return;
      }
      popup.updatePersistent(data);
    } catch { /* refresh failed silently */ }
  }

  /** Check if the input resolves to an interactive command (form popup). */
  function detectInteractive(input) {
    const trimmed = input.trim();
    if (!trimmed.startsWith("!")) return null;
    const { tokens, partial } = parseCommand(trimmed);
    const effective = partial ? [...tokens, partial] : tokens;
    const node = findNode(effective);
    if (node && node.interactive) {
      return node;
    }
    return null;
  }

  /** Handle form submission from interactive popups. */
  async function handleFormSubmit(formData) {
    const { tokens, flags, remaining } = formData;
    const allTokens = [...tokens, ...(remaining || [])];
    isLoading = true;
    try {
      const result = await execute(`!${allTokens.join(" ")}` +
        Object.entries(flags || {}).map(([k, v]) => ` --${k} "${v}"`).join(""));
      popup.show(result.type, result.title, result.data);
    } catch (err) {
      popup.show("error", "Error", { message: err.message || String(err) });
    } finally {
      isLoading = false;
      activeForm = null;
    }
  }

  /** Derive a human-readable loading label from the input. */
  function loadingLabel(input) {
    const t = input.trim();
    if (!t.startsWith("!")) return "Thinking…";
    // Show the command name (first two tokens, e.g. "email sync")
    const parts = t.slice(1).split(/\s+/);
    const cmd = parts.slice(0, 2).join(" ");
    if (!cmd) return "Working…";
    return `${cmd}…`;
  }

  async function handleCommand(input) {
    // Check for interactive command (form popup)
    const interactiveNode = detectInteractive(input);
    if (interactiveNode) {
      const cmdName = interactiveNode.name;
      if (cmdName === "send") {
        activeForm = ComposeEmail;
      } else if (cmdName === "add" && input.includes("event")) {
        activeForm = EventForm;
      } else if (cmdName === "addevent") {
        activeForm = EventForm;
      }
      if (activeForm) {
        popup.show("form", "Compose", { component: activeForm });
        return;
      }
    }

    isLoading = true;
    // Show loading popup so user sees immediate feedback
    popup.showLoading(loadingLabel(input));

    try {
      const result = await execute(input);

      // If there is a persistent popup and this command mutates its data,
      // execute the mutation then refresh the live view.
      if (popup.persistentDataType && isRelevantMutation(input, popup.persistentDataType)) {
        if (result.type === "error") {
          popup.show(result.type, result.title, result.data);
        } else {
          await refreshPersistentPopup();
        }
        return;
      }

      // Check if this command opens a new persistent live view.
      const dataType = detectPersistentType(input);
      if (dataType) {
        popup.showPersistent(result.type, result.title, result.data, dataType);
      } else {
        if (result.type === "error" && popup.persistentDataType) {
          return;
        }
        popup.show(result.type, result.title, result.data);
      }
    } catch (err) {
      if (!popup.persistentDataType) {
        popup.show("error", "Error", {
          message: err.message || String(err),
          suggestion: err.suggestion || "",
        });
      }
    } finally {
      isLoading = false;
    }
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<main>
  {#if isLoading}
    <div class="loading-bar" aria-label="Loading"></div>
  {/if}
  <header>
    <h1>lighterbird</h1>
    {#if tabStore.count > 0}
      <span class="tab-hint">
        Alt+1..{Math.min(tabStore.count, 9)} switch tabs
      </span>
    {/if}
  </header>
  <CommandBar {isLoading} oncommand={handleCommand} />
  <PopupOverlay />
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    max-width: 960px;
    margin: 0 auto;
    width: 100%;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid #333;
  }
  header h1 {
    font-size: 1rem;
    font-weight: 600;
    color: #7c7c9a;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .tab-hint {
    font-size: 0.7rem;
    color: #5a5a7a;
    font-family: monospace;
  }
  .loading-bar {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, #7c7c9a 0%, #a4a4d0 50%, #7c7c9a 100%);
    background-size: 200% 100%;
    animation: bar-slide 1.5s ease-in-out infinite;
    z-index: 1000;
  }
  @keyframes bar-slide {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
</style>

<script>
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

    // Ctrl+R / Ctrl+Shift+R / Ctrl+L — email actions (dispatched to EmailViewTab)
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "r") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "reply" } }));
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "R") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "reply-all" } }));
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "l") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "forward" } }));
        return;
      }
    }
  }

  function loadingLabel(input) {
    const t = input.trim();
    if (!t.startsWith("!")) return "Thinking…";
    const parts = t.slice(1).split(/\s+/);
    const cmd = parts.slice(0, 2).join(" ");
    if (!cmd) return "Working…";
    return `${cmd}…`;
  }

  async function handleCommand(input) {
    isLoading = true;
    popup.showLoading(loadingLabel(input));

    try {
      const result = await execute(input);
      const dataType = detectPersistentType(input);
      if (dataType) {
        popup.showPersistent(result.type, result.title, result.data, dataType);
      } else {
        popup.show(result.type, result.title, result.data);
      }
    } catch (err) {
      popup.show("error", "Error", {
        message: err.message || String(err),
        suggestion: err.suggestion || "",
      });
    } finally {
      isLoading = false;
    }
  }

  function detectPersistentType(input) {
    const t = input.trim();
    if (/^!(email\s+)?account\s+list\s*$/i.test(t)) return "accounts";
    if (/^!(calendar\s+)?account\s+list\s*$/i.test(t)) return "calendars";
    if (/^!contacts\s+list\s*$/i.test(t)) return "contacts";
    if (/^!todo\s+list\s*$/i.test(t)) return "todos";
    if (/^!journal\s+list\s*$/i.test(t)) return "journal";
    return null;
  }

  // Expose handleCommand globally so HomeTab can use it for ! commands
  // (HomeTab calls execute() directly via the import)
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<main>
  {#if isLoading}
    <div class="loading-bar" aria-label="Loading"></div>
  {/if}
  <PopupOverlay />
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
    width: 100%;
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

<script>
  import CommandBar from "./lib/CommandBar.svelte";
  import PopupOverlay from "./lib/PopupOverlay.svelte";
  import { popup } from "./lib/popupStore.svelte.js";
  import { execute } from "./lib/commandDispatcher.js";
  import { email, calendar } from "./lib/api.js";

  let isLoading = $state(false);

  /** Detect whether a command string opens a persistent live view. */
  function detectPersistentType(input) {
    const t = input.trim();
    if (/^!account\s+list\s*$/i.test(t)) return "accounts";
    if (/^!calendar\s+list\s*$/i.test(t)) return "calendars";
    return null;
  }

  /** Check whether a command string mutates the given persistent data type. */
  function isRelevantMutation(input, dataType) {
    if (!dataType) return false;
    const t = input.trim();
    if (dataType === "accounts" && /^!account\s+(add|remove)\b/i.test(t)) return true;
    if (dataType === "calendars" && /^!calendar\s+(add|sync)\b/i.test(t)) return true;
    return false;
  }

  /** Re-fetch data for the current persistent popup and update it. */
  async function refreshPersistentPopup() {
    try {
      let data;
      let title;
      const dt = popup.persistentDataType;
      if (dt === "accounts") {
        data = await email.listAccounts();
        title = "Email Accounts";
      } else if (dt === "calendars") {
        data = await calendar.listCalendars();
        title = "Calendars";
      } else {
        return;
      }
      popup.updatePersistent(data);
    } catch { /* refresh failed silently */ }
  }

  async function handleCommand(input) {
    isLoading = true;

    try {
      const result = await execute(input);

      // If there is a persistent popup and this command mutates its data,
      // execute the mutation then refresh the live view.
      if (popup.persistentDataType && isRelevantMutation(input, popup.persistentDataType)) {
        if (result.type === "error") {
          // Show error, which replaces the persistent view temporarily
          popup.show(result.type, result.title, result.data);
        } else {
          // Mutation succeeded — refresh the live view
          await refreshPersistentPopup();
        }
        return;
      }

      // Check if this command opens a new persistent live view.
      const dataType = detectPersistentType(input);
      if (dataType) {
        popup.showPersistent(result.type, result.title, result.data, dataType);
      } else {
        // For errors and transient results, show and keep popup open.
        // Only close if the existing popup was a persistent view of a
        // *different* type — otherwise just overwrite.
        if (result.type === "error" && popup.persistentDataType) {
          // Don't overwrite persistent popup with error; the user sees the
          // error in the command input area instead.
          return;
        }
        popup.show(result.type, result.title, result.data);
      }
    } catch (err) {
      // Only show error popup if no persistent view is active
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

<main>
  <header>
    <h1>lighterbird</h1>
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
</style>

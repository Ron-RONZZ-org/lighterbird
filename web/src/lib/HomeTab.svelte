<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";
  import { renderMarkdown } from "./markdown.js";
  import ChatInput from "./ChatInput.svelte";
  import LlmSetupModal from "./LlmSetupModal.svelte";
  import ChatMessage from "./ChatMessage.svelte";
  import ResetConfirmDialog from "./ResetConfirmDialog.svelte";
  import ConfirmToolDialog from "./ConfirmToolDialog.svelte";
  import { email as emailApi, calendar, contacts, todo, journal, letters, profiles } from "./api.js";
  import { parseCommand } from "./parser.js";
  import { commandTree, findNode } from "./commandTree.js";
  import { shouldIntercept } from "./commandRouter.js";
  import { detectPersistentType } from "./persistentTypes.js";
  import { splitCommands, isMultiCommand } from "@lightercore/ui/multiCommand.js";
  import { formatConversationText, copyToClipboard } from "@lightercore/ui/conversationUtils.js";

  let hasSentLlmMessage = $state(false);
  let showLlmSetup = $state(false);
  let llmAvailable = $state(null); // null = unknown, true/false = checked
  /** @type {{role:"user"|"assistant", html?:string, text?:string, actions?:[]}[]} */
  let messages = $state([]);
  let convoEl = $state(null);
  let isLoadingLlm = $state(false);
  let resetConfirm = $state(null); // {tokens, flags, message} or null
  /** @type {{type:"chat"|"confirm_tool", session_id?:string, batch?:[], message?:string}|null} */
  let pendingToolConfirm = $state(null);
  let copiedConversation = $state(false);
  let clearConfirm = $state(false);

  /** Build conversation context from message history (last 20 messages). */
  function buildContext() {
    const ctx = [];
    for (const msg of messages.slice(-20)) {
      if (msg.role === "user" && msg.text) {
        ctx.push({ role: "user", content: msg.text });
      } else if (msg.role === "assistant" && (msg.text || msg.html)) {
        const plain = msg.text || (msg.html ? stripHtml(msg.html) : "");
        if (plain) {
          ctx.push({ role: "assistant", content: plain });
        }
      }
    }
    return ctx;
  }

  function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html;
    return div.textContent || div.innerText || "";
  }

  /** Handle submission from ChatInput. */
  async function handleSubmit(input) {
    const trimmed = input.trim();
    if (!trimmed || isLoadingLlm) return;

    // Add user message to conversation
    messages = [...messages, { role: "user", text: trimmed }];
    hasSentLlmMessage = true;

    if (trimmed.startsWith("!")) {
      // ── Multi-command batch execution ─────────────────────────────
      // If the input contains multiple !-commands (e.g. "!email list !todo list"),
      // execute them sequentially, continue on error, and skip interactive
      // commands (those that require form input).
      if (isMultiCommand(trimmed)) {
        const commands = splitCommands(trimmed);
        for (const cmd of commands) {
          try {
            const routing = shouldIntercept(cmd);
            if (routing.intercept) {
              tabStore.open("error", "Skipped", {
                message: `Command "${cmd}" requires an interactive form. Run it separately.`,
              });
              continue;
            }
            const result = await execute(cmd);
            if (result.type === "form-required") {
              tabStore.open("error", "Skipped", {
                message: `Command "${cmd}" requires interactive input. Run it separately.`,
              });
              continue;
            }
            const dataType = detectPersistentType(cmd);
            if (dataType) {
              popup.showPersistent(result.type, result.title, result.data, dataType);
            } else {
              popup.show(result.type, result.title, result.data);
            }
          } catch (err) {
            tabStore.open("error", "Command Failed", {
              message: err.message || String(err),
              suggestion: err.suggestion || "",
            });
          }
        }
        scrollToBottom();
        return;
      }

      // ── Smart add-command routing (single command) ────────────────
      const routing = shouldIntercept(trimmed);
      if (routing.intercept) {
        try {
          const listInput = "!" + routing.listTokens.join(" ");
          const listResult = await execute(listInput);
          if (listResult.type === "error") {
            popup.show("error", "Error", listResult.data);
          } else {
            popup.showPersistent(
              listResult.type,
              listResult.title,
              listResult.data || {},
              routing.listIdKey,
            );
            popup.updateCache(listResult.data || {});
            tabStore.open("form", routing.addTitle || "Add", {
              form: routing.addFormType,
              initialData: routing.initialData || {},
            }, { idKey: `form-${routing.addFormType}` });
          }
        } catch (err) {
          popup.show("error", "Routing Error", {
            message: err.message || "Failed to open add form",
          });
        }
        scrollToBottom();
        return;
      }

      // ── Normal command execution → result opens in new tab ─────────
      try {
        const result = await execute(trimmed);

        // Handle form-required response (interactive commands with missing args)
        if (result.type === "form-required") {
          const { form, initialData, message } = result.data || {};
          if (form) {
            // Special case: reset-no-backup shows a ConfirmDialog overlay
            if (form === "reset-no-backup") {
              resetConfirm = {
                tokens: parseCommand(trimmed).tokens,
                flags: { "no-backup": "", "confirmed": "true" },
                message: message || "This will permanently delete ALL your data.",
              };
              scrollToBottom();
              return;
            }
            tabStore.open("form", result.title || "Complete Form", {
              form,
              initialData: initialData || {},
              error: result.data?.error || "",
            }, { idKey: `form-${form}` });
            scrollToBottom();
            return;
          }
        }

        const dataType = detectPersistentType(trimmed);
        if (dataType) {
          popup.showPersistent(result.type, result.title, result.data, dataType);
        } else {
          popup.show(result.type, result.title, result.data);
        }
      } catch (err) {
        tabStore.open("error", "Error", {
          message: err.message || String(err),
          suggestion: err.suggestion || "",
        });
      }
      scrollToBottom();
      return;
    }

    // ── LLM chat mode (multi-round tool-calling) ─────────────────────
    if (llmAvailable === null) {
      await checkLlmAvailable();
    }
    if (llmAvailable === false) {
      showLlmSetup = true;
      isLoadingLlm = false;
      return;
    }

    isLoadingLlm = true;
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
    scrollToBottom();

    const context = buildContext();

    try {
      await _runChatRound(trimmed, context, msgIdx);
    } catch (err) {
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html: `<p>Network error: ${err.message}</p>`, _streaming: false }
          : m,
      );
    }

    isLoadingLlm = false;
    scrollToBottom();
  }

  /** Handle action accept (draft approval). */
  function handleActionAccept(action) {
    if (action.action === "send_email") {
      const tokens = ["email", "send", action.params.to[0], action.params.subject, action.params.body];
      tabStore.open("loading", "Sending…", null, { closable: false });
      fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens, flags: {} }),
      })
        .then((r) => r.json())
        .then((result) => {
          tabStore.open(result.type || "status", result.title || "Sent", result.data || {});
        })
        .catch((err) => {
          tabStore.open("error", "Error", { message: err.message || "Failed to send" });
        });
    }
  }

  /** Handle action reject. */
  function handleActionReject(action) {
    messages = [
      ...messages,
      {
        role: "assistant",
        html: `<p><em>You rejected the ${action.action} draft.</em></p>`,
        actions: [],
      },
    ];
  }

  /** Handle successful command save from ChatMessage. */
  function handleCommandSaved(alias, cmdTemplate) {
    messages = [...messages, {
      role: "assistant",
      html: `<p><em>Saved command <strong>!${alias}</strong> → <code>${cmdTemplate}</code></em></p>`,
    }];
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (convoEl) convoEl.scrollTop = convoEl.scrollHeight;
    });
  }

  /** Run one round of the multi-round chat (or resume). */
  async function _runChatRound(message, context, msgIdx) {
    const resp = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, context }),
    });

    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html: `<p>Error: ${errMsg}</p>`, _streaming: false } : m,
      );
      return;
    }

    const result = await resp.json();

    if (result.type === "confirm_tool") {
      // Pause for user approval
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html: `<p><em>Waiting for your approval...</em></p>`, _streaming: false } : m,
      );
      pendingToolConfirm = result;
      return;
    }

    if (result.type === "chat" && result.data?.html) {
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html: result.data.html, text: result.data.html.replace(/<[^>]+>/g, ""), _streaming: false, actions: result.data.actions || [] }
          : m,
      );
      return;
    }

    // Fallback: status or unknown type
    const fallbackHtml = result.data?.message || result.data?.html || JSON.stringify(result);
    messages = messages.map((m, i) =>
      i === msgIdx ? { ...m, html: `<p>${fallbackHtml}</p>`, _streaming: false } : m,
    );
  }

  /** Handle tool confirmation from ConfirmToolDialog (now shared ConfirmDialog). */
  async function _handleToolConfirm(decisions, feedback) {
    const session = pendingToolConfirm;
    pendingToolConfirm = null;
    if (!session?.session_id) return;

    // Re-add the "thinking" message
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];

    try {
      const body = { session_id: session.session_id, decisions };
      if (feedback != null) {
        body.feedback = feedback;
      }
      const resp = await fetch("/api/v1/chat/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p>Error: ${errMsg}</p>`, _streaming: false } : m,
        );
        return;
      }

      const result = await resp.json();

      if (result.type === "confirm_tool") {
        // Another round of approvals needed
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p><em>Waiting for your approval...</em></p>`, _streaming: false } : m,
        );
        pendingToolConfirm = result;
        return;
      }

      if (result.type === "chat" && result.data?.html) {
        messages = messages.map((m, i) =>
          i === msgIdx
            ? { ...m, html: result.data.html, text: result.data.html.replace(/<[^>]+>/g, ""), _streaming: false, actions: result.data.actions || [] }
            : m,
        );
        return;
      }

      const fallbackHtml = result.data?.message || JSON.stringify(result);
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html: `<p>${fallbackHtml}</p>`, _streaming: false } : m,
      );
    } catch (err) {
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html: `<p>Network error: ${err.message}</p>`, _streaming: false } : m,
      );
    }
  }

  /** Dismiss tool confirmation (user cancelled). */
  function _handleToolDismiss() {
    pendingToolConfirm = null;
    messages = [...messages, {
      role: "assistant",
      html: "<p><em>Tool execution cancelled.</em></p>",
      _streaming: false,
    }];
  }

  // ── Conversation toolbar ───────────────────────────────────────
  async function handleCopyConversation() {
    const text = formatConversationText(messages, { userLabel: "You", assistantLabel: "Assistant" });
    await copyToClipboard(text);
    copiedConversation = true;
    setTimeout(() => { copiedConversation = false; }, 1500);
  }

  function handleClearConversation() {
    messages = [];
    clearConfirm = false;
  }

  // Refresh data cache on mount (and when messages change — triggers re-cache
  // so autocomplete data stays fresh).
  $effect(() => {
    refreshDataCache();
  });

  async function refreshDataCache() {
    try {
      // Use a 3-month window for events (30 days ago → 60 days ahead)
      const eventStart = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
      const eventEnd = new Date(Date.now() + 60 * 86400000).toISOString().slice(0, 10);
      const [accts, cals, conts, tds, jrnl, fldrs, evts, ltrs, profs] = await Promise.all([
        emailApi.listAccounts().catch(() => null),
        calendar.listCalendars().catch(() => null),
        contacts.list({ limit: 50 }).catch(() => null),
        todo.list({ limit: 50 }).catch(() => null),
        journal.list({ limit: 50 }).catch(() => null),
        emailApi.listFolders().catch(() => null),
        calendar.listEvents({ start: eventStart, end: eventEnd }).catch(() => null),
        letters.list({ limit: 50 }).catch(() => null),
        profiles.list({ limit: 50 }).catch(() => null),
      ]);
      popup.updateCache({
        accounts: accts?.accounts ?? [],
        calendars: cals?.calendars ?? [],
        contacts: conts?.contacts ?? [],
        todos: tds?.todos ?? [],
        journal: jrnl?.entries ?? [],
        folders: fldrs?.folders ?? [],
        events: evts?.events ?? [],
        letters: ltrs?.letters ?? [],
        profiles: profs?.profiles ?? [],
      });
    } catch { /* ignore */ }
  }

  async function checkLlmAvailable() {
    try {
      const resp = await fetch("/api/v1/llm/config");
      if (resp.ok) {
        const cfg = await resp.json();
        llmAvailable = !!cfg.available;
      } else {
        llmAvailable = false;
      }
    } catch {
      llmAvailable = false;
    }
  }

  function handleLlmConfigured() {
    showLlmSetup = false;
    llmAvailable = true;
  }
</script>

<div class="home-tab">
  <!-- Logo / branding -->
  <div class="brand" class:compact={hasSentLlmMessage}>
    <h1 class="logo">lighterbird</h1>
    {#if !hasSentLlmMessage}
      <p class="tagline">Command-driven personal information manager</p>
    {/if}
  </div>

  <!-- Conversation area (visible after first message) -->
  {#if messages.length > 0}
    <div class="conversation" bind:this={convoEl}>
      {#each messages as msg}
        <ChatMessage
          {msg}
          onActionAccept={handleActionAccept}
          onActionReject={handleActionReject}
          onCommandSaved={handleCommandSaved}
        />
      {/each}
    </div>
  {/if}

  {#if messages.length > 0}
    <div class="conversation-toolbar">
      <button class="toolbar-btn" onclick={handleCopyConversation} title="Copy conversation to clipboard">
        {#if copiedConversation}
          &#10003; Copied
        {:else}
          &#128203; Copy conversation
        {/if}
      </button>
      <button class="toolbar-btn toolbar-btn-danger" onclick={() => { clearConfirm = true; }} title="Clear all messages">
        &#128465; Clear chat
      </button>
    </div>
  {/if}

  {#if clearConfirm}
    <div class="clear-overlay" role="alertdialog" aria-label="Clear conversation"
         onclick={() => { clearConfirm = false; }}>
      <div class="clear-box" role="presentation" onclick={(e) => e.stopPropagation()}>
        <p class="clear-message">Clear all conversation messages? This cannot be undone.</p>
        <div class="actions">
          <button class="btn btn-danger-btn" onclick={handleClearConversation}>Clear</button>
          <button class="btn btn-cancel-btn" onclick={() => { clearConfirm = false; }}>Cancel</button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Input area -->
  <div class="input-container" class:at-bottom={hasSentLlmMessage || messages.length > 0}>
    <ChatInput centered={!hasSentLlmMessage && messages.length === 0} onSubmit={handleSubmit} />
  </div>
</div>

{#if showLlmSetup}
  <LlmSetupModal
    onConfigured={handleLlmConfigured}
    onDismiss={() => { showLlmSetup = false; }}
  />
{/if}

{#if resetConfirm}
  <ResetConfirmDialog
    message={resetConfirm.message}
    onConfirm={async () => {
      const cmd = resetConfirm;
      resetConfirm = null;
      try {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: cmd.tokens, flags: cmd.flags }),
        });
        const result = await resp.json();
        if (result.type === "form-required") {
          popup.show("error", "Reset Cancelled", { message: "Reset requires confirmation." });
        } else {
          const dataType = detectPersistentType("!reset");
          if (dataType) {
            popup.showPersistent(result.type, result.title, result.data, dataType);
          } else {
            popup.show(result.type, result.title, result.data);
          }
        }
      } catch (err) {
        popup.show("error", "Reset Failed", { message: err.message || String(err) });
      }
    }}
    onDismiss={() => { resetConfirm = null; }}
  />
{/if}

{#if pendingToolConfirm}
  <ConfirmToolDialog
    batch={pendingToolConfirm.batch || []}
    message={pendingToolConfirm.message || ""}
    onSubmit={_handleToolConfirm}
    onDismiss={_handleToolDismiss}
  />
{/if}

<style>
  .home-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
  }
  .brand {
    text-align: center;
    padding: 3rem 1rem 1rem;
    transition: all 0.4s ease;
    flex-shrink: 0;
  }
  .brand.compact {
    padding: 0.75rem 1rem 0.25rem;
  }
  .logo {
    font-size: 1.6rem;
    font-weight: 300;
    color: #7c7c9a;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: monospace;
  }
  .brand.compact .logo {
    font-size: 0.9rem;
    opacity: 0.6;
  }
  .tagline {
    font-size: 0.8rem;
    color: #5a5a7a;
    font-family: monospace;
    margin-top: 0.4rem;
  }
  .conversation {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-height: 0;
  }
  /* ── Conversation toolbar ───────────────────── */
  .conversation-toolbar {
    display: flex;
    gap: 0.5rem;
    justify-content: center;
    padding: 0.25rem 1rem 0.5rem;
    flex-shrink: 0;
  }
  .toolbar-btn {
    background: transparent;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-family: monospace;
    font-size: 0.75rem;
    color: #7c7c9a;
    cursor: pointer;
    transition: all 0.15s;
  }
  .toolbar-btn:hover { background: #2a2a44; color: #b0b0c0; border-color: #6a6a8a; }
  .toolbar-btn-danger:hover { background: #3a1a1a; color: #ba6a6a; border-color: #8a3a3a; }

  /* ── Clear chat confirm dialog ──────────────── */
  .clear-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .clear-box {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    max-width: 400px;
    width: 90%;
  }
  .clear-message {
    margin: 0 0 0.75rem 0;
    color: #e0e0e0;
    font-size: 0.9rem;
    line-height: 1.4;
    text-align: center;
  }
  .btn-danger-btn { background: #4a2a2a; border-color: #7a3a3a; color: #e0e0e0; padding: 0.35rem 0.85rem; border-radius: 4px; cursor: pointer; font-size: 0.82rem; }
  .btn-danger-btn:hover { background: #6a3a3a; }
  .btn-cancel-btn { background: #3a3a3a; border-color: #555; color: #e0e0e0; padding: 0.35rem 0.85rem; border-radius: 4px; cursor: pointer; font-size: 0.82rem; }
  .btn-cancel-btn:hover { background: #4a4a4a; }

  .input-container {
    padding: 0.75rem 1rem;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    transition: all 0.4s ease;
  }
  .input-container.at-bottom {
    border-top: 1px solid #333;
    background: #1a1a2e;
  }
</style>

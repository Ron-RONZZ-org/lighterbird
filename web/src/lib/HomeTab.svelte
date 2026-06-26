<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";
  import { renderMarkdown } from "./markdown.js";
  import ChatInput from "./ChatInput.svelte";
  import LlmSetupModal from "./LlmSetupModal.svelte";
  import { email as emailApi, calendar, contacts, todo, journal } from "./api.js";
  import { parseCommand } from "./parser.js";
  import { commandTree, findNode } from "./commandTree.js";

  let hasSentLlmMessage = $state(false);
  let showLlmSetup = $state(false);
  let llmAvailable = $state(null); // null = unknown, true/false = checked
  /** @type {{role:"user"|"assistant", html?:string, text?:string, actions?:[]}[]} */
  let messages = $state([]);
  let convoEl = $state(null);
  let isLoadingLlm = $state(false);
  let saveDialogIndex = $state(-1); // index of message with open save dialog, -1 = closed
  let saveAlias = $state("");
  let saveCommand = $state("");
  let saveHint = $state("");
  let copiedIndex = $state(-1); // index of message just copied, -1 = none

  /** Build conversation context from message history (last 20 messages). */
  function buildContext() {
    const ctx = [];
    for (const msg of messages.slice(-20)) {
      if (msg.role === "user" && msg.text) {
        ctx.push({ role: "user", content: msg.text });
      } else if (msg.role === "assistant" && (msg.text || msg.html)) {
        // Strip HTML tags for the context (keep plain text)
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

  /** Count command-path tokens (excluding params). */
  function countCmdTokens(tokens) {
    let current = commandTree;
    for (let i = 0; i < tokens.length; i++) {
      const found = current.find((n) => n.name.toLowerCase() === tokens[i].toLowerCase());
      if (!found) return i;
      if (!found.children || found.children.length === 0) return i + 1;
      current = found.children;
    }
    return tokens.length;
  }

  /** Open an interactive form tab for a command node with missing params. */
  function openFormTab(node, input) {
    const cmdPath = node.name; // leaf node name
    // Detect parent domain from input
    const parts = input.replace(/^!/, "").trim().split(/\s+/);
    const parents = parts.slice(0, -1); // everything before the leaf command
    const domain = parents[0] || "";
    const parentStr = parents.join(".");

    let formType = "";
    let formTitle = "";
    let FormComponent = null;

    if (cmdPath === "write" && domain === "journal") {
      formType = "journal-write";
      formTitle = "Write Journal Entry";
    } else if (cmdPath === "add" && parentStr === "todo") {
      formType = "todo-add";
      formTitle = "Add Todo";
    } else if (cmdPath === "send" && domain === "email") {
      formType = "email-send";
      formTitle = "Compose Email";
    } else if (cmdPath === "add" && parentStr === "calendar event") {
      formType = "calendar-event-add";
      formTitle = "Add Calendar Event";
    } else {
      // Unknown interactive command — let it fall through to backend error
      return;
    }

    tabStore.open("form", formTitle, { form: formType, initialData: {} });
  }

  /** Handle submission from ChatInput. */
  async function handleSubmit(input) {
    const trimmed = input.trim();
    if (!trimmed || isLoadingLlm) return;

    // Add user message to conversation
    messages = [...messages, { role: "user", text: trimmed }];
    hasSentLlmMessage = true;

    if (trimmed.startsWith("!")) {
      // ── Interactive form detection ─────────────────────────────────
      // Check if the command tree says this is interactive AND the user
      // hasn't provided all required positional params.
      const { tokens, partial } = parseCommand(trimmed);
      const trailing = trimmed.endsWith(" ");
      // Build effective tokens: when there's no trailing space, the partial
      // might be a complete command token (not a partial). Try resolving it.
      let effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
      if (!trailing && partial) {
        // The partial might be the leaf command name — check if tokens +
        // partial resolves to a deeper node.
        const nodeWithPartial = findNode([...tokens, partial]);
        if (nodeWithPartial) {
          effectiveTokens = [...tokens, partial];
        }
      }
      const node = findNode(effectiveTokens);

      if (node?.interactive && effectiveTokens.length > 0) {
        const consumed = effectiveTokens.length - countCmdTokens(effectiveTokens) - 1;
        const missingRequired = node.params?.some((p, i) => p.required && i >= consumed);
        if (missingRequired) {
          openFormTab(node, trimmed);
          scrollToBottom();
          return;
        }
      }

      // ── Normal command execution → result opens in new tab ─────────
      try {
        const result = await execute(trimmed);
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

    // ── LLM chat mode ────────────────────────────────────────────────
    // Check if LLM is available; if not, show setup modal
    if (llmAvailable === null) {
      await checkLlmAvailable();
    }
    if (llmAvailable === false) {
      showLlmSetup = true;
      isLoadingLlm = false;
      return;
    }

    // ── Streaming ────────────────────────────────────────────────────
    isLoadingLlm = true;
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
    scrollToBottom();

    const context = buildContext();

    try {
      const resp = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, context }),
      });

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p>Error: ${errMsg}</p>`, _streaming: false } : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      // Read SSE stream
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") continue;
            try {
              const parsed = JSON.parse(payload);
              if (parsed.token) {
                accumulated += parsed.token;
                const html = renderMarkdown(accumulated);
                messages = messages.map((m, i) =>
                  i === msgIdx ? { ...m, html, text: accumulated, _streaming: true } : m,
                );
                scrollToBottom();
              }
            } catch { /* skip malformed SSE */ }
          }
        }
      }

      // Final render with completed text
      const finalHtml = renderMarkdown(accumulated);
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html: finalHtml, text: accumulated, _streaming: false, actions: [] }
          : m,
      );
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

  /** Copy message text to clipboard and show brief feedback. */
  function copyMessage(index) {
    const msg = messages[index];
    if (!msg) return;
    const text = msg.text || (msg.html ? stripHtml(msg.html) : "");
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      copiedIndex = index;
      setTimeout(() => { if (copiedIndex === index) copiedIndex = -1; }, 1500);
    }).catch(() => {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      copiedIndex = index;
      setTimeout(() => { if (copiedIndex === index) copiedIndex = -1; }, 1500);
    });
  }

  /** Open save command dialog for a user !command message. */
  function openSaveDialog(index, text) {
    // Strip leading ! for the template
    const cmdText = text.replace(/^!/, "").trim();
    saveCommand = cmdText;
    saveAlias = "";
    saveHint = "";
    saveDialogIndex = index;
  }

  /** Save the command via backend. */
  async function handleSaveCommand() {
    if (!saveAlias.trim() || !saveCommand.trim()) return;
    const alias = saveAlias.trim();
    const cmdTemplate = saveCommand.trim();
    const hint = saveHint.trim();
    try {
      const result = await execute(
        `!user saved-commands add --alias ${alias} --command "${cmdTemplate}"${hint ? ` --hint "${hint}"` : ""}`
      );
      if (result.type === "status") {
        saveDialogIndex = -1;
        // Add a confirmation message
        messages = [...messages, {
          role: "assistant",
          html: `<p><em>Saved command <strong>!${alias}</strong> → <code>${cmdTemplate}</code></em></p>`,
        }];
      } else {
        const errMsg = result.data?.message || "Failed to save command";
        tabStore.open("error", "Error", { message: errMsg });
      }
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to save" });
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (convoEl) convoEl.scrollTop = convoEl.scrollHeight;
    });
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

  function detectPersistentType(input) {
    const t = input.trim();
    if (/^!(email\s+)?account\s+list\s*$/i.test(t)) return "accounts";
    if (/^!(calendar\s+)?account\s+list\s*$/i.test(t)) return "calendars";
    if (/^!contacts\s+list\s*$/i.test(t)) return "contacts";
    if (/^!todo\s+list\s*$/i.test(t)) return "todos";
    if (/^!journal\s+(list|search)\b/i.test(t)) return "journal-list";
    if (/^!email\s+(list|search)\b/i.test(t)) return "email-list";
    if (/^!user\s+saved-commands\s+list\s*$/i.test(t)) return "saved-commands";
    return null;
  }

  // Refresh data cache on mount (and when messages change — triggers re-cache
  // so autocomplete data stays fresh).
  $effect(() => {
    refreshDataCache();
  });

  async function refreshDataCache() {
    try {
      const [accts, cals, conts, tds, jrnl, fldrs] = await Promise.all([
        emailApi.listAccounts().catch(() => null),
        calendar.listCalendars().catch(() => null),
        contacts.list({ limit: 50 }).catch(() => null),
        todo.list({ limit: 50 }).catch(() => null),
        journal.list({ limit: 50 }).catch(() => null),
        emailApi.listFolders().catch(() => null),
      ]);
      popup.updateCache({
        accounts: accts?.accounts ?? [],
        calendars: cals?.calendars ?? [],
        contacts: conts?.contacts ?? [],
        todos: tds?.todos ?? [],
        journal: jrnl?.entries ?? [],
        folders: fldrs?.folders ?? [],
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
      {#each messages as msg, i}
        <div class="message" class:user={msg.role === "user"} class:assistant={msg.role === "assistant"}>
          <div class="msg-header">
            <span class="msg-role">{msg.role === "user" ? "You" : "lighterbird"}</span>
            <button
              class="btn-copy"
              title="Copy message"
              onclick={() => copyMessage(i)}
            >
              {#if copiedIndex === i}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              {:else}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              {/if}
            </button>
          </div>
          {#if msg.html}
            <div class="msg-body">{@html msg.html}</div>
          {:else if msg.text}
            <div class="msg-body">{msg.text}</div>
          {:else if msg._streaming}
            <div class="msg-body"><em>Thinking…</em></div>
          {/if}
          {#if msg.actions && msg.actions.length > 0}
            <div class="actions">
              {#each msg.actions as action}
                <div class="action-card">
                  <p class="action-label">{action.label || action.action}</p>
                  <div class="action-buttons">
                    <button class="btn-accept" onclick={() => handleActionAccept(action)}>Accept</button>
                    <button class="btn-reject" onclick={() => handleActionReject(action)}>Reject</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
          {#if msg.role === "user" && msg.text && msg.text.trim().startsWith("!") && !msg.text.trim().startsWith("!user")}
            <div class="msg-actions">
              <button class="btn-save-cmd" onclick={() => openSaveDialog(i, msg.text)}>Save Command</button>
            </div>
          {/if}
          {#if i === saveDialogIndex}
            <div class="save-dialog">
              <div class="save-dialog-inner">
                <div class="save-row">
                  <label>
                    <span class="save-label">Alias</span>
                    <input type="text" bind:value={saveAlias} placeholder="e.g. ronzz" />
                  </label>
                </div>
                <div class="save-row">
                  <label>
                    <span class="save-label">Command <em>(without !)</em></span>
                    <input type="text" bind:value={saveCommand} placeholder="email list --folder X" />
                  </label>
                </div>
                <div class="save-row">
                  <label>
                    <span class="save-label">Hint</span>
                    <input type="text" bind:value={saveHint} placeholder="Short description" />
                  </label>
                </div>
                <div class="save-actions">
                  <button class="btn-save" onclick={handleSaveCommand}>Save</button>
                  <button class="btn-cancel-save" onclick={() => { saveDialogIndex = -1; }}>Cancel</button>
                </div>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <!-- Input area -->
  <div class="input-container" class:at-bottom={hasSentLlmMessage}>
    <ChatInput centered={!hasSentLlmMessage} onSubmit={handleSubmit} />
  </div>
</div>

{#if showLlmSetup}
  <LlmSetupModal
    onConfigured={handleLlmConfigured}
    onDismiss={() => { showLlmSetup = false; }}
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
  .message {
    max-width: 85%;
    padding: 0.6rem 0.9rem;
    border-radius: 10px;
    font-family: monospace;
    font-size: 0.88rem;
    line-height: 1.5;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .message.user {
    align-self: flex-end;
    background: #2a2a44;
    border: 1px solid #3a3a5a;
    color: #e0e0e0;
  }
  .message.assistant {
    align-self: flex-start;
    background: #1a1a30;
    border: 1px solid #333;
    color: #d0d0e0;
  }
  .msg-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.3rem;
  }
  .btn-copy {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: #5a5a7a;
    cursor: pointer;
    padding: 2px;
    border-radius: 4px;
    opacity: 0;
    transition: opacity 0.15s, color 0.15s, background 0.15s;
  }
  .message:hover .btn-copy {
    opacity: 1;
  }
  .btn-copy:hover {
    color: #b0b0c0;
    background: #3a3a5a;
  }
  .msg-role {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #7c7c9a;
  }
  .msg-body { white-space: pre-wrap; word-break: break-word; }
  .msg-body :global(p) { margin: 0.3rem 0; }
  .msg-body :global(pre) {
    background: #111; padding: 0.5rem; border-radius: 6px;
    overflow-x: auto; font-size: 0.8rem; margin: 0.4rem 0;
  }
  .msg-body :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.82rem;
  }
  .msg-body :global(pre code) { background: none; padding: 0; }
  .msg-body :global(a) { color: #8a8acc; text-decoration: underline; }
  .msg-body :global(blockquote) {
    border-left: 2px solid #5a5a7a; padding-left: 0.6rem;
    margin: 0.4rem 0; color: #9a9ab0;
  }
  .msg-body :global(ul), .msg-body :global(ol) { padding-left: 1.2rem; margin: 0.3rem 0; }
  .msg-body :global(li) { margin: 0.1rem 0; }
  .msg-body :global(h1), .msg-body :global(h2), .msg-body :global(h3) {
    margin: 0.5rem 0 0.2rem; color: #e0e0e0;
  }
  .msg-body :global(hr) { border: none; border-top: 1px solid #333; margin: 0.5rem 0; }
  .actions { margin-top: 0.5rem; }
  .action-card {
    background: #1e1e32; border: 1px solid #4a4a6a;
    border-radius: 8px; padding: 0.6rem; margin-top: 0.4rem;
  }
  .action-label { font-size: 0.8rem; color: #b0b0c0; margin-bottom: 0.4rem; }
  .action-buttons { display: flex; gap: 0.4rem; }
  .btn-accept, .btn-reject {
    padding: 0.25rem 0.8rem; border-radius: 6px; border: 1px solid #444;
    font-family: monospace; font-size: 0.78rem; cursor: pointer; transition: background 0.1s;
  }
  .btn-accept { background: #1a3a1a; color: #6aaa6a; border-color: #3a6a3a; }
  .btn-accept:hover { background: #2a4a2a; }
  .btn-reject { background: #3a1a1a; color: #aa6a6a; border-color: #6a3a3a; }
  .btn-reject:hover { background: #4a2a2a; }
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
  .msg-actions { margin-top: 0.35rem; display: flex; gap: 0.3rem; }
  .btn-save-cmd {
    background: transparent; border: 1px solid #4a4a6a; border-radius: 4px;
    padding: 0.15rem 0.5rem; font-family: monospace; font-size: 0.72rem;
    color: #7c7c9a; cursor: pointer; transition: all 0.1s;
  }
  .btn-save-cmd:hover { background: #2a2a44; color: #b0b0c0; border-color: #6a6a8a; }
  .save-dialog {
    margin-top: 0.4rem; padding: 0.5rem; background: #1e1e32;
    border: 1px solid #4a4a6a; border-radius: 8px;
  }
  .save-dialog-inner { display: flex; flex-direction: column; gap: 0.3rem; }
  .save-row label {
    display: flex; flex-direction: column; gap: 0.15rem;
  }
  .save-label { font-size: 0.72rem; color: #7c7c9a; }
  .save-label em { font-style: normal; color: #5a5a7a; }
  .save-row input {
    background: #16162a; border: 1px solid #333; border-radius: 4px;
    padding: 0.25rem 0.4rem; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .save-row input:focus { border-color: #5a5a8a; }
  .save-actions { display: flex; gap: 0.3rem; margin-top: 0.3rem; }
  .btn-save {
    background: #2a4a2a; color: #6aaa6a; border: 1px solid #3a6a3a;
    border-radius: 4px; padding: 0.2rem 0.6rem; font-family: monospace; font-size: 0.78rem; cursor: pointer;
  }
  .btn-save:hover { background: #3a5a3a; }
  .btn-cancel-save {
    background: transparent; color: #7c7c9a; border: 1px solid #444;
    border-radius: 4px; padding: 0.2rem 0.6rem; font-family: monospace; font-size: 0.78rem; cursor: pointer;
  }
  .btn-cancel-save:hover { background: #2a2a3e; }
</style>

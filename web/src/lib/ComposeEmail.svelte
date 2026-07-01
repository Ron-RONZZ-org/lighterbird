<script>
  /** Email compose form — used when !email send is typed interactively. */

  import { email as emailApi, drafts as draftsApi } from "./api.js";
  import FormField from "./FormField.svelte";
  import { createCowrite, CowriteButton, CowritePanel } from "./cowrite/index.js";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let accountUuid = $state(_initial.account || "");
  let to = $state(_initial.to || "");
  let subject = $state(_initial.subject || "");
  let body = $state(_initial.body || "");
  let cc = $state(_initial.cc || "");
  let bcc = $state(_initial.bcc || "");
  let priority = $state(_initial.priority || "3");
  let bodyFormat = $state("markdown"); // "markdown" | "html" | "plain"
  let attachmentFiles = $state([]); // Array of {name, data} (base64)
  let sending = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);
  let accounts = $state([]);

  // ── LLM co-writing ─────────────────────────────────────────────────
  let cowrite = $state(createCowrite({
    formType: "email-send",
    getCurrentContent: () => ({
      to,
      subject,
      body,
      cc,
      bcc,
    }),
    applyEdit: (field, text) => {
      if (field === "to") to = text;
      else if (field === "subject") subject = text;
      else if (field === "body") body = text;
      else if (field === "cc") cc = text;
      else if (field === "bcc") bcc = text;
    },
  }));

  /** Save draft on Ctrl+S */
  async function saveDraft() {
    if (savingDraft) return;
    savingDraft = true;
    draftSaved = false;
    try {
      const result = await draftsApi.save(
        "email",
        subject || "(no subject)",
        { account: accountUuid, to, subject, body, cc, bcc, priority, bodyFormat },
        draftUuid,
      );
      draftUuid = result.uuid;
      draftSaved = true;
      setTimeout(() => { draftSaved = false; }, 2000);
    } catch { /* silent */ }
    finally { savingDraft = false; }
  }

  function handleFormKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveDraft();
    }
    // Ctrl+Enter — submit form from any field including textarea
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  // Dirty state — compare current against initial
  let dirty = $derived(
    to !== (_initial.to || "")
    || subject !== (_initial.subject || "")
    || body !== (_initial.body || "")
    || cc !== (_initial.cc || "")
    || bcc !== (_initial.bcc || "")
    || priority !== (_initial.priority || "3")
    || bodyFormat !== "markdown"
    || attachmentFiles.length > 0
  );
  $effect(() => { onDirtyChange(dirty); });

  $effect(() => {
    emailApi.listAccounts().then((data) => {
      accounts = data.accounts || [];
      if (accounts.length > 0 && !accountUuid) {
        accountUuid = accounts[0].uuid;
      }
    }).catch(() => {});
  });

  async function handleAttachmentUpload(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const newAttachments = [];
    for (const file of files) {
      const data = await fileToBase64(file);
      newAttachments.push({ name: file.name, data });
    }
    attachmentFiles = [...attachmentFiles, ...newAttachments];
    e.target.value = ""; // reset so same file can be re-selected
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]); // strip data: prefix
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function removeAttachment(idx) {
    attachmentFiles = attachmentFiles.filter((_, i) => i !== idx);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!to || !subject) return;
    sending = true;
    try {
      const flags = {
        ...(accountUuid ? { account: accountUuid } : {}),
        ...(cc ? { cc } : {}),
        ...(bcc ? { bcc } : {}),
        priority,
        ...(bodyFormat !== "markdown" ? { [`body-format`]: bodyFormat } : {}),
      };
      const remaining = [to, subject, body];
      // Attachments passed as --file flags
      for (const att of attachmentFiles) {
        remaining.push(`--file`);
        remaining.push(`${att.name}:${att.data}`);
      }
      await onsubmit({
        tokens: ["email", "send"],
        flags,
        remaining,
      });
      // Clear dirty state after successful submit
      onDirtyChange(false);
    } finally {
      sending = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="email-form">
  <div class="row-fields">
    <FormField label="Account" class="flex-1">
      {#snippet children()}
        <select id="account" class="ff-input" bind:value={accountUuid}>
          {#each accounts as acct}
            <option value={acct.uuid}>{acct.email}</option>
          {/each}
        </select>
      {/snippet}
    </FormField>
    <FormField label="Priority" class="flex-1">
      {#snippet children()}
        <select id="priority" class="ff-input" bind:value={priority}>
          <option value="1">1 — Highest</option>
          <option value="2">2 — High</option>
          <option value="3" selected>3 — Normal</option>
          <option value="4">4 — Low</option>
          <option value="5">5 — Lowest</option>
        </select>
      {/snippet}
    </FormField>
  </div>

  <FormField label="To" required={true}>
    {#snippet children()}
      <input id="to" type="email" class="ff-input" bind:value={to} required placeholder="recipient@example.com" />
    {/snippet}
  </FormField>

  <div class="row-fields">
    <FormField label="CC" class="flex-1">
      {#snippet children()}
        <input id="cc" type="email" class="ff-input" bind:value={cc} placeholder="cc@example.com" />
      {/snippet}
    </FormField>
    <FormField label="BCC" class="flex-1">
      {#snippet children()}
        <input id="bcc" type="email" class="ff-input" bind:value={bcc} placeholder="bcc@example.com" />
      {/snippet}
    </FormField>
  </div>

  <FormField label="Subject" required={true}>
    {#snippet children()}
      <input id="subject" type="text" class="ff-input" bind:value={subject} required placeholder="Subject" />
    {/snippet}
  </FormField>

  <FormField label="Body" hint="Markdown (default) — use dropdown to switch">
    {#snippet children()}
      <div class="body-area">
        <div class="body-format-bar">
          <select class="format-select" bind:value={bodyFormat}>
            <option value="markdown">Markdown</option>
            <option value="html">HTML</option>
            <option value="plain">Plain Text</option>
          </select>
          <span class="toolbar-spacer"></span>
          <CowriteButton {cowrite} />
        </div>
        <textarea id="body" class="ff-textarea" bind:value={body} rows="8"
          placeholder="Message body (Markdown supported)"></textarea>
      </div>
    {/snippet}
  </FormField>

  <!-- File attachments -->
  <FormField label="Attachments">
    {#snippet children()}
      <div class="attachment-area">
        <input type="file" class="file-input" multiple onchange={handleAttachmentUpload} />
        {#if attachmentFiles.length > 0}
          <div class="attachment-list">
            {#each attachmentFiles as att, i}
              <div class="attachment-item">
                <span class="att-name">{att.name}</span>
                <button type="button" class="att-remove" onclick={() => removeAttachment(i)} aria-label="Remove">✕</button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/snippet}
  </FormField>

  <div class="form-actions">
    <button type="button" class="btn-draft" onclick={saveDraft} disabled={savingDraft || !to && !subject && !body}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" class="btn-primary" disabled={sending || !to || !subject}>
      {sending ? "Sending..." : "Send"} <kbd>⌃Enter</kbd>
    </button>
  </div>

  {#if cowrite.isActive}
    <CowritePanel {cowrite} />
  {/if}
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .email-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; position: relative; }
  .row-fields { display: flex; gap: 0.75rem; }
  .row-fields :global(.flex-1) { flex: 1; }
  :global(.ff-input) {
    width: 100%; padding: 0.5rem 0.6rem; background: #16213e; border: 1px solid #333;
    color: #e0e0e0; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s; box-sizing: border-box;
  }
  :global(.ff-input:focus) { border-color: #5a5a8a; }
  :global(.ff-textarea) {
    width: 100%; padding: 0.5rem 0.6rem; background: #16213e; border: 1px solid #333;
    color: #e0e0e0; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s; box-sizing: border-box;
    resize: vertical; min-height: 120px;
  }
  :global(.ff-textarea:focus) { border-color: #5a5a8a; }
  :global(.ff-input-has-error) { border-color: #8a4a4a; }
  .body-area { display: flex; flex-direction: column; gap: 0.3rem; }
  .body-format-bar { display: flex; align-items: center; gap: 0.5rem; }
  .format-select {
    padding: 0.25rem 0.5rem; background: #2a2a3e; border: 1px solid #444;
    color: #e0e0e0; border-radius: 4px; font-family: monospace; font-size: 0.78rem;
    cursor: pointer;
  }
  .toolbar-spacer { flex: 1; }
  .attachment-area { display: flex; flex-direction: column; gap: 0.4rem; }
  .file-input {
    font-family: monospace; font-size: 0.8rem; color: #ccc;
  }
  .file-input::file-selector-button {
    background: #2a2a3e; border: 1px solid #444; border-radius: 4px;
    color: #e0e0e0; padding: 0.3rem 0.6rem; font-family: monospace; font-size: 0.8rem;
    cursor: pointer; margin-right: 0.5rem;
  }
  .file-input::file-selector-button:hover { background: #3a3a5a; }
  .attachment-list { display: flex; flex-direction: column; gap: 0.25rem; }
  .attachment-item {
    display: flex; align-items: center; justify-content: space-between;
    background: #2a2a3e; padding: 0.25rem 0.5rem; border-radius: 4px;
    font-family: monospace; font-size: 0.8rem;
  }
  .att-name { color: #ccc; }
  .att-remove {
    background: none; border: none; color: #8a4a4a; cursor: pointer;
    font-size: 0.8rem; padding: 0.1rem 0.3rem;
  }
  .att-remove:hover { color: #cc6a6a; }
  .form-actions { display: flex; align-items: center; gap: 0.5rem; }
  .btn-draft {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #ccc;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.82rem;
    transition: background 0.15s;
    white-space: nowrap;
  }
  .btn-draft:hover:not(:disabled) { background: #3a3a5a; }
  .btn-draft:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-draft kbd {
    display: inline-block;
    padding: 1px 4px;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    font-size: 0.7rem;
    margin-left: 0.2rem;
  }
</style>

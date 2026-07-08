<script>
  /** Email compose form — used when !email send is typed interactively. */

  import { email as emailApi, contacts as contactsApi, drafts as draftsApi } from "./api.js";
  import EmbedInstallDialog from "./EmbedInstallDialog.svelte";
  import FormField from "./FormField.svelte";
  import PreviewDialog from "./PreviewDialog.svelte";
  import { createCowrite, CowriteButton, CowritePanel } from "./cowrite/index.js";
  import MultiEntryField from "./MultiEntryField.svelte";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // Snapshot of initial props for dirty-state comparison.
  // $state ensures Svelte treats this as a reactive binding without tracking
  // updates — intentionally a one-time capture, not a live $derived.
  // svelte-ignore state_referenced_locally — intentionally captured at mount for dirty-state comparison
  let _initial = $state(initialData);

  let accountEmail = $state(_initial.account || "");
  let toList = $state(_initial.to ? _initial.to.split(",").map((s) => s.trim()).filter(Boolean) : []);
  let subject = $state(_initial.subject || "");
  let body = $state(_initial.body || "");
  let ccList = $state(_initial.cc ? _initial.cc.split(",").map((s) => s.trim()).filter(Boolean) : []);
  let bccList = $state(_initial.bcc ? _initial.bcc.split(",").map((s) => s.trim()).filter(Boolean) : []);
  let priority = $state(_initial.priority || "3");
  let bodyFormat = $state(_initial["body-format"] || _initial.body_format || "markdown"); // "markdown" | "html" | "plain"
  let attachmentFiles = $state(_initial.files || []); // Array of {name, data} (base64)
  let saveAsSample = $state(true); // save as writing sample for LLM style learning
  let sending = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);
  let accounts = $state([]);
  let contactSuggestions = $state([]); // email addresses from contacts

  // ── Signature state ────────────────────────────────────────────────
  let signatureList = $state([]); // [{uuid, name, signature_text, signature_format, ...}]
  let useSignature = $state(true);
  let selectedSignatureName = $state("default");
  let signaturePreview = $state("");
  let signatureFormat = $state("plain");

  /** Load all signatures (global — not per-account) */
  function loadAllSignatures() {
    fetch("/api/v1/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tokens: ["email", "signature", "list"],
        flags: {},
      }),
    })
      .then((r) => r.json())
      .then((cmdData) => {
        const sigs = cmdData.data?.signatures || cmdData.signatures || [];
        signatureList = sigs;
        if (sigs.length > 0) {
          const def = sigs[0];
          selectedSignatureName = def.name;
          signaturePreview = def.signature_text || "";
          signatureFormat = def.signature_format || "plain";
          useSignature = true;
        } else {
          signaturePreview = "";
          signatureFormat = "plain";
          useSignature = false;
        }
      })
      .catch(() => {
        // Silently fail — no signatures available
        signatureList = [];
        signaturePreview = "";
        signatureFormat = "plain";
        useSignature = false;
      });
  }

  // Load signatures on mount (no account dependency)
  $effect(() => {
    loadAllSignatures();
  });

  // When the selected signature changes, update the preview
  function onSignatureSelect(name) {
    selectedSignatureName = name;
    const found = signatureList.find((s) => s.name === name);
    signaturePreview = found ? (found.signature_text || "") : "";
    signatureFormat = found ? (found.signature_format || "plain") : "plain";
  }

  /** Preview state for body and signature */
  let preview = $state(null);
  function previewSignature() {
    if (!signaturePreview) return;
    import("./preview.svelte.js").then((mod) => {
      const state = mod.createPreviewState();
      preview = state;
      state.show(signaturePreview, signatureFormat, "Signature Preview");
    });
  }
  function previewBody() {
    if (!body) return;
    import("./preview.svelte.js").then((mod) => {
      const state = mod.createPreviewState();
      preview = state;
      state.show(body, bodyFormat, "Body Preview");
    });
  }

  // ── Load contacts for recipient suggestions ──────────────────────────
  $effect(() => {
    contactsApi.list({ limit: 100 }).then((data) => {
      const contacts = data.contacts || [];
      const emails = new Set();
      for (const c of contacts) {
        const raw = c.emails;
        if (Array.isArray(raw)) {
          for (const e of raw) {
            if (typeof e === "string" && e.includes("@")) emails.add(e);
            else if (e?.value && e.value.includes("@")) emails.add(e.value);
          }
        } else if (typeof raw === "string") {
          try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
              for (const e of parsed) {
                if (typeof e === "string" && e.includes("@")) emails.add(e);
                else if (e?.value && e.value.includes("@")) emails.add(e.value);
              }
            }
          } catch { /* ignore */ }
        }
      }
      contactSuggestions = [...emails].sort();
    }).catch(() => {});
  });

  /** Autocomplete query for MultiEntryField: filter contact suggestions by partial match */
  function searchContactEmails(partial) {
    if (!partial || partial.length < 1) return [];
    const q = partial.toLowerCase();
    const matches = contactSuggestions.filter((e) => e.toLowerCase().includes(q));
    return matches.map((email) => ({ label: email, value: email }));
  }

  // ── LLM co-writing ─────────────────────────────────────────────────
  let cowrite = $state(createCowrite({
    formType: "email-send",
    getCurrentContent: () => ({
      to: toList.join(", "),
      subject,
      body,
      cc: ccList.join(", "),
      bcc: bccList.join(", "),
    }),
    applyEdit: (field, text) => {
      if (field === "to") toList = text.split(",").map((s) => s.trim()).filter(Boolean);
      else if (field === "subject") subject = text;
      else if (field === "body") body = text;
      else if (field === "cc") ccList = text.split(",").map((s) => s.trim()).filter(Boolean);
      else if (field === "bcc") bccList = text.split(",").map((s) => s.trim()).filter(Boolean);
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
        { account: accountEmail, to: toList.join(","), subject, body, cc: ccList.join(","), bcc: bccList.join(","), priority, bodyFormat },
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
    // Ctrl+Shift+P — preview body
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      if (body.trim()) previewBody();
    }
    // q — close tab; prompt save draft if dirty
    if (e.key === "q" && !e.ctrlKey && !e.metaKey && dirty) {
      if (confirm("You have unsaved changes. Save as draft?")) {
        saveDraft();
      }
      // Don't preventDefault — let TabView's global q handler close the tab
    }
  }

  // Dirty state — compare current against initial
  let initialToArray = $derived(_initial.to ? _initial.to.split(",").map((s) => s.trim()).filter(Boolean) : []);
  let dirty = $derived(
    toList.length !== initialToArray.length || toList.some((e, i) => e !== initialToArray[i])
    || subject !== (_initial.subject || "")
    || body !== (_initial.body || "")
    || ccList.length > 0
    || bccList.length > 0
    || priority !== (_initial.priority || "3")
    || bodyFormat !== "markdown"
    || attachmentFiles.length > 0
    || saveAsSample !== true
  );
  $effect(() => { onDirtyChange(dirty); });

  // Last-used account persistence
  const LS_LAST_ACCOUNT = "lighterbird:email:lastUsedAccount";
  function getLastUsedAccount() {
    try { return localStorage.getItem(LS_LAST_ACCOUNT) || ""; } catch { return ""; }
  }
  function saveLastUsedAccount(email) {
    try { localStorage.setItem(LS_LAST_ACCOUNT, email); } catch { /* best-effort */ }
  }

  $effect(() => {
    emailApi.listAccounts().then((data) => {
      accounts = data.accounts || [];
      if (accounts.length > 0 && !accountEmail) {
        // Try last-used, fall back to first
        const last = getLastUsedAccount();
        const match = last ? accounts.find((a) => a.email === last) : null;
        accountEmail = match ? match.email : accounts[0].email;
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
    if (toList.length === 0 || !subject) return;
    sending = true;
    try {
      if (accountEmail) saveLastUsedAccount(accountEmail);
      // Resolve signature: pass --signature-name, or --no-signature if disabled
      const flags = {
        ...(accountEmail ? { account: accountEmail } : {}),
        ...(ccList.length > 0 ? { cc: ccList.join(",") } : {}),
        ...(bccList.length > 0 ? { bcc: bccList.join(",") } : {}),
        priority,
        ...(bodyFormat !== "markdown" ? { [`body-format`]: bodyFormat } : {}),
        ...(saveAsSample === false ? { "no-save-sample": "true" } : {}),
        // Signature: pass --signature-name, or --no-signature if disabled
        ...(!useSignature ? { "no-signature": "true" } : {}),
        ...(useSignature && selectedSignatureName ? { "signature-name": selectedSignatureName } : {}),
        // File attachments as proper --file flag (never in remaining/body)
        ...(attachmentFiles.length > 0 ? { file: attachmentFiles.map((att) => `${att.name}:${att.data}`).join(",") } : {}),
      };
      const toStr = toList.join(",");
      const remaining = [toStr, subject, body];
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
  <!-- Toolbar -->
  <div class="form-toolbar">
    <div class="toolbar-left">
      <span class="toolbar-title">Compose Email</span>
    </div>
    <div class="toolbar-right">
      <CowriteButton {cowrite} />
    </div>
  </div>

  <div class="row-fields">
    <FormField label="Account" class="flex-1">
      {#snippet children()}
        <select id="account" class="ff-input" bind:value={accountEmail}>
          {#each accounts as acct}
            <option value={acct.email}>{acct.email}</option>
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
      <MultiEntryField
        label=""
        bind:entries={toList}
        placeholder="recipient@example.com"
        autocompleteQuery={searchContactEmails}
        allowDuplicates={false}
      />
    {/snippet}
  </FormField>

  <div class="row-fields multi-row">
    <div class="multi-field-wrapper flex-1">
      <MultiEntryField
        label="CC"
        bind:entries={ccList}
        placeholder="cc@example.com"
        autocompleteQuery={searchContactEmails}
      />
    </div>
    <div class="multi-field-wrapper flex-1">
      <MultiEntryField
        label="BCC"
        bind:entries={bccList}
        placeholder="bcc@example.com"
        autocompleteQuery={searchContactEmails}
      />
    </div>
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
          <button type="button" class="preview-btn" onclick={previewBody}
            disabled={!body.trim()} title="Preview body (Ctrl+Shift+P)">
            Preview
          </button>
        </div>
        <textarea id="body" class="ff-textarea" bind:value={body} rows="8"
          placeholder="Message body (Markdown supported)"></textarea>
      </div>
    {/snippet}
  </FormField>

  <!-- Writing sample opt-out -->
  <div class="writing-sample-toggle">
    <label class="toggle-label">
      <input type="checkbox" bind:checked={saveAsSample} />
      Save as writing sample for style learning
    </label>
    <span class="toggle-hint">Your writing style will be used to improve LLM suggestions</span>
  </div>

  <!-- Signature -->
  <FormField label="Signature">
    {#snippet children()}
      <div class="signature-area">
        <label class="toggle-label sig-toggle">
          <input type="checkbox" bind:checked={useSignature} />
          Attach signature
        </label>
        {#if useSignature}
          {#if signatureList.length > 0}
            <div class="sig-select-row">
              <select class="ff-input sig-select"
                value={selectedSignatureName}
                onchange={(e) => onSignatureSelect(e.target.value)}>
                {#each signatureList as sig}
                  <option value={sig.name}>{sig.name}</option>
                {/each}
              </select>
              <span class="sig-format-badge">{signatureFormat}</span>
              <button type="button" class="sig-preview-btn" onclick={previewSignature}
                title="Preview signature" disabled={!signaturePreview}>
                Preview
              </button>
            </div>
            <div class="sig-preview">{signaturePreview}</div>
          {:else}
            <p class="sig-empty">No signatures configured. Use <code>!email signature add</code> to create one.</p>
          {/if}
        {/if}
      </div>
    {/snippet}
  </FormField>

  {#if preview}
    <PreviewDialog
      showing={preview.showing}
      htmlContent={preview.htmlContent}
      title={preview.title}
      onclose={() => preview.close()}
    />
  {/if}

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
    <button type="button" class="btn-draft" onclick={saveDraft} disabled={savingDraft || toList.length === 0 && !subject && !body}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" class="btn-primary" disabled={sending || toList.length === 0 || !subject}>
      {sending ? "Sending..." : "Send"} <kbd>Ctrl+Enter</kbd>
    </button>
  </div>

  {#if cowrite.isActive}
    <CowritePanel {cowrite} />
  {/if}

  {#if cowrite.embedRequired}
    <EmbedInstallDialog
      models={cowrite.embedRequired.models}
      oninstall={(modelKey) => {
        cowrite.embedRequired = null;
        // Re-invoke cowrite with the same instruction
        cowrite.startCowrite(cowrite.instruction);
      }}
      onskip={() => { cowrite.embedRequired = null; }}
    />
  {/if}
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .email-form { padding: 1rem 1rem 0 1rem; display: flex; flex-direction: column; gap: 0.75rem; position: relative; }
  .form-toolbar {
    display: flex; align-items: center; gap: 0.5rem;
    margin: -1rem -1rem 0 -1rem; padding: 0.4rem 0.5rem;
    background: #16162a; border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
  .toolbar-right { margin-left: auto; }
  .toolbar-title { color: #b0b0c0; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
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
  .preview-btn {
    padding: 0.25rem 0.5rem; border: 1px solid #444; border-radius: 4px;
    background: transparent; color: #b0b0c0; font-family: monospace;
    font-size: 0.72rem; cursor: pointer; transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .preview-btn:hover:not(:disabled) { background: #2a2a44; color: #e0e0e0; }
  .preview-btn:disabled { opacity: 0.4; cursor: not-allowed; }
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
  .multi-row { align-items: flex-start; }
  .multi-field-wrapper { position: relative; }
  .writing-sample-toggle {
    display: flex; flex-direction: column; gap: 0.15rem;
    padding: 0.4rem 0;
  }
  .toggle-label {
    display: flex; align-items: center; gap: 0.4rem;
    font-family: monospace; font-size: 0.82rem; color: #b0b0c0;
    cursor: pointer;
  }
  .toggle-label input { accent-color: #5a5a8a; cursor: pointer; }
  .toggle-hint {
    font-family: monospace; font-size: 0.72rem; color: #707080;
    margin-left: 1.2rem;
  }

  .signature-area {
    display: flex; flex-direction: column; gap: 0.35rem;
  }
  .sig-toggle { font-size: 0.82rem; }
  .sig-select { font-size: 0.82rem; max-width: 16rem; }
  .sig-select-row {
    display: flex; align-items: center; gap: 0.4rem;
  }
  .sig-format-badge {
    font-family: monospace; font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
    background: #2a2a3e; border: 1px solid #444; border-radius: 3px;
    color: #9090b0; text-transform: uppercase;
    white-space: nowrap; flex-shrink: 0;
  }
  .sig-preview-btn {
    padding: 0.15rem 0.5rem;
    border: 1px solid #444; border-radius: 4px;
    background: transparent; color: #b0b0c0;
    font-family: monospace; font-size: 0.72rem;
    cursor: pointer; white-space: nowrap;
    transition: background 0.1s, color 0.1s;
  }
  .sig-preview-btn:hover:not(:disabled) { background: #2a2a44; color: #e0e0e0; }
  .sig-preview-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .sig-preview {
    font-family: monospace; font-size: 0.78rem; color: #909090;
    background: #1a1a2e; border: 1px solid #333; border-radius: 4px;
    padding: 0.4rem 0.6rem; white-space: pre-wrap; max-height: 4rem;
    overflow-y: auto;
  }
  .sig-empty {
    font-family: monospace; font-size: 0.78rem; color: #707080;
    font-style: italic;
  }
  .sig-empty code { background: #2a2a3e; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.75rem; }
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

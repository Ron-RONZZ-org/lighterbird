<script>
  /**
   * Letter form — add received or send a new letter.
   *
   * Features:
   *   - Multiline sender/recipient textareas with profile/contact import dialogs
   *   - Inline body editor with format selection (markdown/html/text) and file upload toggle
   *   - Preview toggle for body content
   *   - Dirty-form guard with beforeunload
   *   - Keyboard: Ctrl+Enter to submit, Ctrl+S to save draft
   *   - q-key prompt to save draft on unsaved changes
   *   - LLM co-writing integration (Ask LLM)
   *   - Contact suggestions for recipient field
   */
  import { contacts as contactsApi, drafts as draftsApi } from "./api.js";
  import SearchDialog from "./SearchDialog.svelte";
  import LetterBodyEditor from "./LetterBodyEditor.svelte";
  import { createCowrite, CowriteButton, CowritePanel } from "./cowrite/index.js";

  let { initialData = {}, formType = "add", onsubmit, onDirtyChange } = $props();

  // ── Form state ─────────────────────────────────────────────────────────
  // svelte-ignore state_referenced_locally
  let object = $state(initialData.object || "");
  // svelte-ignore state_referenced_locally
  let senderText = $state(initialData.sender_manual || initialData.sender || "");
  // svelte-ignore state_referenced_locally
  let recipientText = $state(initialData.recipient_manual || initialData.recipient || "");
  // svelte-ignore state_referenced_locally
  let senderProfile = $state(initialData["sender-profile"] || initialData.sender_profile || "");
  // svelte-ignore state_referenced_locally
  let recipientContact = $state(initialData["recipient-contact"] || initialData.recipient_contact || "");
  // svelte-ignore state_referenced_locally
  let respondTo = $state(initialData["respond-to"] || initialData.respond_to_uuid || "");
  let bodyContent = $state("");
  let bodyFormat = $state("markdown");
  // svelte-ignore state_referenced_locally
  let bodyFilePath = $state(initialData.body || "");
  let bodyProvided = $state(false); // tracks if body was ever edited / file specified

  let returnIdKey = $derived(initialData._returnIdKey || "persistent-letter-list");
  let returnType = $derived(initialData._returnType || "letter-list");
  let returnTitle = $derived(initialData._returnTitle || "Letters");

  // ── Draft state ─────────────────────────────────────────────────────────
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  // svelte-ignore state_referenced_locally
  let draftUuid = $state(initialData._draft_uuid || null);

  // ── Contact suggestions for recipient ──────────────────────────────────
  let contactSuggestions = $state([]);
  let showSuggestions = $state(false);
  let filteredSuggestions = $derived(
    contactSuggestions.filter((s) => {
      if (!recipientText.trim()) return false;
      const q = recipientText.toLowerCase();
      return s.label.toLowerCase().includes(q);
    }).slice(0, 8)
  );

  $effect(() => {
    contactsApi.list({ limit: 100 }).then((data) => {
      const contacts = data.contacts || [];
      const entries = [];
      for (const c of contacts) {
        const name = c.full_name || c.given_name || c.name || "";
        const addr = c.address || "";
        let email = "";
        const raw = c.emails;
        if (Array.isArray(raw)) {
          for (const e of raw) {
            if (typeof e === "string" && e.includes("@")) { email = e; break; }
            else if (e?.value && e.value.includes("@")) { email = e.value; break; }
          }
        } else if (typeof raw === "string") {
          try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed) && parsed.length > 0) {
              const first = parsed[0];
              email = typeof first === "string" ? first : (first?.value || "");
            }
          } catch { /* ignore */ }
        }
        if (name || email || addr) {
          entries.push({ label: [name, addr, email].filter(Boolean).join(" — "), name, addr, email });
        }
      }
      contactSuggestions = entries;
    }).catch(() => {});
  });

  // ── Dynamic labels based on form type ─────────────────────────────────
  let senderLabel = $derived(formType === "add" ? "Sender" : "Your Address / Identity");
  let recipientLabel = $derived(formType === "add" ? "Recipient" : "Recipient Address");
  let submitLabel = $derived(formType === "add" ? "Add Letter" : "Send Letter");

  // ── Dialog states ──────────────────────────────────────────────────────
  let showSenderDialog = $state(false);
  let showRecipientDialog = $state(false);

  // ── Dirty tracking ─────────────────────────────────────────────────────
  let dirty = $derived(
    object || senderText || recipientText || senderProfile || recipientContact
    || respondTo || bodyProvided
  );
  $effect(() => { onDirtyChange?.(dirty); });

  // ── beforeunload guard ─────────────────────────────────────────────────
  $effect(() => {
    if (dirty) {
      const handler = (e) => {
        e.preventDefault();
        e.returnValue = "";
      };
      window.addEventListener("beforeunload", handler);
      return () => window.removeEventListener("beforeunload", handler);
    }
  });

  // ── Body change handlers ───────────────────────────────────────────────
  function onBodyChange(body, format) {
    bodyContent = body;
    bodyFormat = format;
    if (body.trim()) bodyProvided = true;
  }

  function onBodyPathChange(path) {
    bodyFilePath = path;
    if (path.trim()) bodyProvided = true;
  }

  // ── Import from profile/contact ────────────────────────────────────────
  function handleProfileSelect(profile) {
    // Format: name \n address \n email \n phone
    const lines = [];
    lines.push(profile.full_name || profile.given_name || "");
    lines.push(profile.address || "");
    // Primary email
    let email = "";
    try {
      const emails = typeof profile.emails === "string" ? JSON.parse(profile.emails) : (profile.emails || []);
      if (Array.isArray(emails) && emails.length > 0) {
        email = emails[0].value || emails[0] || "";
      }
    } catch { email = ""; }
    lines.push(email);
    // Primary phone
    let phone = "";
    try {
      const phones = typeof profile.phones === "string" ? JSON.parse(profile.phones) : (profile.phones || []);
      if (Array.isArray(phones) && phones.length > 0) {
        phone = phones[0].value || phones[0] || "";
      }
    } catch { phone = ""; }
    lines.push(phone);

    senderText = lines.join("\n");
    senderProfile = profile.uuid || "";
  }

  function handleContactSelect(contact) {
    const lines = [];
    lines.push(contact.full_name || contact.given_name || contact.name || "");
    lines.push(contact.address || "");
    // Primary email
    let email = "";
    try {
      const emails = typeof contact.emails === "string" ? JSON.parse(contact.emails) : (contact.emails || []);
      if (Array.isArray(emails) && emails.length > 0) {
        email = emails[0].value || emails[0] || "";
      }
    } catch { email = ""; }
    lines.push(email);
    // Primary phone
    let phone = "";
    try {
      const phones = typeof contact.phones === "string" ? JSON.parse(contact.phones) : (contact.phones || []);
      if (Array.isArray(phones) && phones.length > 0) {
        phone = phones[0].value || phones[0] || "";
      }
    } catch { phone = ""; }
    lines.push(phone);

    recipientText = lines.join("\n");
    recipientContact = contact.uuid || "";
  }

  // ── LLM co-writing ─────────────────────────────────────────────────────
  // svelte-ignore state_referenced_locally
  const _formType = formType;
  let cowrite = $state(createCowrite({
    formType: _formType === "send" ? "letter-send" : "letter-add",
    getCurrentContent: () => ({
      ...(formType === "send" ? { object } : {}),
      sender: senderText,
      recipient: recipientText,
      body: bodyContent,
    }),
    applyEdit: (field, text) => {
      if (field === "object") object = text;
      else if (field === "sender") senderText = text;
      else if (field === "recipient") recipientText = text;
      else if (field === "body") { bodyContent = text; bodyProvided = true; }
    },
  }));

  // ── Save draft ─────────────────────────────────────────────────────────
  async function saveDraft() {
    if (savingDraft) return;
    savingDraft = true;
    draftSaved = false;
    try {
      const title = object || "(no subject)";
      const data = {
        object, sender: senderText, recipient: recipientText,
        sender_profile: senderProfile, recipient_contact: recipientContact,
        respond_to: respondTo, body: bodyContent, body_format: bodyFormat,
        body_file_path: bodyFilePath, body_provided: bodyProvided,
      };
      if (formType === "add") {
        data._formType = "add";
      }
      const result = await draftsApi.save("letter", title, data, draftUuid);
      draftUuid = result.uuid;
      draftSaved = true;
      setTimeout(() => { draftSaved = false; }, 2000);
    } catch { /* silent */ }
    finally { savingDraft = false; }
  }

  // ── Form submission ────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault();

    const flags = {};
    let tokens;

    if (formType === "add") {
      if (!object.trim()) return;
      tokens = ["letter", "add", object.trim()];
      if (senderText.trim()) flags.sender = senderText.trim();
      if (recipientText.trim()) flags.recipient = recipientText.trim();
      if (respondTo.trim()) flags["respond-to"] = respondTo.trim();
    } else {
      if (!recipientText.trim() && !recipientContact.trim()) return;
      tokens = ["letter", "send", recipientText.trim() || recipientContact.trim()];
      if (object.trim()) flags.object = object.trim();
      if (senderText.trim()) flags.sender = senderText.trim();
      if (respondTo.trim()) flags["respond-to"] = respondTo.trim();
      if (senderProfile) flags["sender-profile"] = senderProfile;
      if (recipientContact) flags["recipient-contact"] = recipientContact;
    }

    // Body: prefer inline text, fall back to file path
    if (bodyContent.trim()) {
      flags["body-text"] = bodyContent.trim();
      flags["body-format"] = bodyFormat;
    } else if (bodyFilePath.trim()) {
      flags.body = bodyFilePath.trim();
    }

    await onsubmit({ tokens, flags, remaining: [] });
  }

  // ── Keyboard shortcuts ─────────────────────────────────────────────────
  function handleFormKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveDraft();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
    // q — prompt save draft if dirty
    if (e.key === "q" && !e.ctrlKey && !e.metaKey && dirty) {
      e.preventDefault();
      if (confirm("You have unsaved changes. Save as draft?")) {
        saveDraft();
      }
    }
  }
</script>

<svelte:window onkeydown={handleFormKeydown} />

<form class="letter-form" onsubmit={handleSubmit}>
  {#if formType === "add"}
    <div class="field-row">
      <label for="object">Subject/Object</label>
      <input id="object" type="text" bind:value={object} placeholder="Letter subject" required />
    </div>
  {/if}

  <!-- Sender field (multiline) -->
  <div class="field-row">
    <div class="field-header">
      <label for="sender">{senderLabel}</label>
      <button type="button" class="import-btn" onclick={() => (showSenderDialog = true)} title="Import from profile">
        &#128279; Profile
      </button>
    </div>
    <textarea
      id="sender"
      class="multi-textarea"
      bind:value={senderText}
      placeholder="Your name&#10;Street address&#10;email@example.com&#10;+1-234-567-8900"
      rows="4"
    ></textarea>
  </div>

  <!-- Recipient field (multiline) with contact suggestions -->
  <div class="field-row">
    <div class="field-header">
      <label for="recipient">{recipientLabel}</label>
      <button type="button" class="import-btn" onclick={() => (showRecipientDialog = true)} title="Import from contact">
        &#128279; Contact
      </button>
    </div>
    <textarea
      id="recipient"
      class="multi-textarea"
      bind:value={recipientText}
      placeholder="Recipient name&#10;Street address&#10;email@example.com&#10;+1-234-567-8900"
      rows="4"
      onfocus={() => { if (recipientText.trim()) showSuggestions = true; }}
      onblur={() => setTimeout(() => { showSuggestions = false; }, 200)}
      oninput={() => { showSuggestions = true; }}
    ></textarea>
    {#if showSuggestions && filteredSuggestions.length > 0}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="suggestion-popup" role="listbox" onmousedown={(e) => e.preventDefault()}>
        {#each filteredSuggestions as entry}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div class="suggestion-item" role="option" onmousedown={() => { recipientText = entry.label; showSuggestions = false; }}>
            {entry.label}
          </div>
        {/each}
      </div>
    {/if}
  </div>

  {#if formType === "send"}
    <div class="field-row">
      <label for="object">Subject/Object</label>
      <input id="object" type="text" bind:value={object} placeholder="Letter subject" />
    </div>
  {/if}

  <!-- Body editor with cowrite button -->
  <div class="field-row">
    <div class="body-header">
      <span class="body-header-label">Body</span>
      <CowriteButton {cowrite} />
    </div>
    <LetterBodyEditor
      bind:body={bodyContent}
      bind:bodyFormat={bodyFormat}
      bind:bodyPath={bodyFilePath}
      onbodychange={onBodyChange}
      onbodypathchange={onBodyPathChange}
    />
  </div>

  <!-- Optional respond-to -->
  <div class="field-row">
    <label for="respond-to">Respond To (UUID)</label>
    <input id="respond-to" type="text" bind:value={respondTo} placeholder="UUID of letter this responds to" />
  </div>

  <div class="button-row">
    <button type="button" class="btn-draft" onclick={saveDraft} disabled={savingDraft || !dirty}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" class="submit-btn">{submitLabel} <kbd>⌃Enter</kbd></button>
  </div>
</form>

<!-- Sender profile search dialog -->
{#if showSenderDialog}
  <SearchDialog
    endpoint="/profiles/profiles"
    title="Select Profile"
    placeholder="Search profiles…"
    onselect={handleProfileSelect}
    onclose={() => (showSenderDialog = false)}
  />
{/if}

<!-- Recipient contact search dialog -->
{#if showRecipientDialog}
  <SearchDialog
    endpoint="/contacts/contacts"
    title="Select Contact"
    placeholder="Search contacts…"
    onselect={handleContactSelect}
    onclose={() => (showRecipientDialog = false)}
  />
{/if}

{#if cowrite.isActive}
  <CowritePanel {cowrite} />
{/if}

<style>
  .letter-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem;
    font-family: monospace;
    font-size: 0.85rem;
    position: relative;
  }
  .field-row {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .field-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .field-row > label,
  .field-header label {
    color: var(--clr-sub);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .field-row input[type="text"] {
    padding: 0.4rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    outline: none;
  }
  .field-row input[type="text"]:focus {
    border-color: #6a6a9a;
  }
  .field-row input::placeholder {
    color: #555;
  }
  .multi-textarea {
    width: 100%;
    padding: 0.4rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    line-height: 1.5;
    resize: vertical;
    outline: none;
    box-sizing: border-box;
  }
  .multi-textarea:focus {
    border-color: #6a6a9a;
  }
  .multi-textarea::placeholder {
    color: #555;
  }
  .import-btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: transparent;
    color: #7c9acc;
    font-family: monospace;
    font-size: 0.72rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .import-btn:hover {
    background: #1a2a44;
    color: #99bbee;
  }
  .button-row {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
    align-items: center;
  }
  .submit-btn {
    padding: 0.4rem 1rem;
    border: 1px solid #3a6a3a;
    border-radius: 4px;
    background: #1e3a1e;
    color: #7fdb7f;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .submit-btn:hover {
    background: #2a4a2a;
  }
  .submit-btn kbd {
    display: inline-block;
    padding: 0 3px;
    margin-left: 2px;
    font-family: monospace;
    font-size: 0.68rem;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    color: #999;
    line-height: 1.3;
  }
  .btn-draft {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #ccc;
    padding: 0.4rem 0.8rem;
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
  .body-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .body-header-label {
    color: var(--clr-sub);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .suggestion-popup {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 4px;
    max-height: 200px;
    overflow-y: auto;
    z-index: 10;
  }
  .suggestion-item {
    padding: 0.3rem 0.5rem;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.78rem;
    color: #d0d0e0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .suggestion-item:hover {
    background: #2a2a44;
    color: #fff;
  }
</style>

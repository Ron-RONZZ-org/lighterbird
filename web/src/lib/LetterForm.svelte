<script>
  /**
   * Letter form — add received or send a new letter.
   *
   * Features:
   *   - Multiline sender/recipient textareas with profile/contact import dialogs
   *   - Inline body editor with format selection (markdown/html/text) and file upload toggle
   *   - Preview toggle for body content
   *   - Dirty-form guard with beforeunload
   *   - Keyboard: Ctrl+Enter to submit
   */
  import SearchDialog from "./SearchDialog.svelte";
  import LetterBodyEditor from "./LetterBodyEditor.svelte";

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
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
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

  <!-- Recipient field (multiline) -->
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
    ></textarea>
  </div>

  {#if formType === "send"}
    <div class="field-row">
      <label for="object">Subject/Object</label>
      <input id="object" type="text" bind:value={object} placeholder="Letter subject" />
    </div>
  {/if}

  <!-- Body editor -->
  <div class="field-row">
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

<style>
  .letter-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem;
    font-family: monospace;
    font-size: 0.85rem;
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
</style>

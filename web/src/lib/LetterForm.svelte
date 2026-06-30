<script>
  /** Letter form — add received or send a new letter. */

  let { initialData = {}, formType = "add", onsubmit, onDirtyChange } = $props();

  let object = $state(initialData.object || "");
  let recipient = $state(initialData.recipient || "");
  let sender = $state(initialData.sender || "");
  let bodyPath = $state(initialData.body || "");
  let respondTo = $state(initialData["respond-to"] || "");
  let senderProfile = $state(initialData["sender-profile"] || "");
  let recipientContact = $state(initialData["recipient-contact"] || "");

  let returnIdKey = $derived(initialData._returnIdKey || "persistent-letter-list");
  let returnType = $derived(initialData._returnType || "letter-list");
  let returnTitle = $derived(initialData._returnTitle || "Letters");

  let dirty = $derived(
    object || recipient || sender || bodyPath || respondTo || senderProfile || recipientContact
  );
  $effect(() => { onDirtyChange?.(dirty); });

  async function handleSubmit(e) {
    e.preventDefault();

    const flags = {};

    if (formType === "add") {
      if (!object.trim()) return;
      if (sender.trim()) flags.sender = sender.trim();
      if (bodyPath.trim()) flags.body = bodyPath.trim();
      if (respondTo.trim()) flags["respond-to"] = respondTo.trim();
      if (recipient.trim()) flags.recipient = recipient.trim();

      await onsubmit({
        tokens: ["letter", "add", object.trim()],
        flags,
        remaining: [],
      });
    } else {
      if (!recipient.trim()) return;
      if (object.trim()) flags.object = object.trim();
      if (sender.trim()) flags["sender-profile"] = sender.trim();
      if (bodyPath.trim()) flags.body = bodyPath.trim();
      if (respondTo.trim()) flags["respond-to"] = respondTo.trim();
      if (recipientContact.trim()) flags["recipient-contact"] = recipientContact.trim();

      await onsubmit({
        tokens: ["letter", "send", recipient.trim()],
        flags,
        remaining: [],
      });
    }
  }
</script>

<form class="letter-form" onsubmit={handleSubmit}>
  {#if formType === "add"}
    <div class="field-row">
      <label for="object">Subject/Object</label>
      <input id="object" type="text" bind:value={object} placeholder="Letter subject" required />
    </div>
    <div class="field-row">
      <label for="sender">Sender</label>
      <input id="sender" type="text" bind:value={sender} placeholder="Sender name (free text)" />
    </div>
    <div class="field-row">
      <label for="recipient">Recipient</label>
      <input id="recipient" type="text" bind:value={recipient} placeholder="Recipient name (free text)" />
    </div>
  {:else}
    <div class="field-row">
      <label for="recipient">Recipient</label>
      <input id="recipient" type="text" bind:value={recipient} placeholder="Recipient name" required />
    </div>
    <div class="field-row">
      <label for="object">Subject/Object</label>
      <input id="object" type="text" bind:value={object} placeholder="Letter subject" />
    </div>
    <div class="field-row">
      <label for="sender-profile">Sender Profile</label>
      <input id="sender-profile" type="text" bind:value={senderProfile} placeholder="Profile UUID" />
    </div>
    <div class="field-row">
      <label for="recipient-contact">Recipient Contact</label>
      <input id="recipient-contact" type="text" bind:value={recipientContact} placeholder="Contact UUID" />
    </div>
  {/if}

  <div class="field-row">
    <label for="body">Body File</label>
    <input id="body" type="text" bind:value={bodyPath} placeholder="Path to .md/.html/.txt file" />
    <span class="hint">Supports .md, .html, .txt</span>
  </div>

  <div class="field-row">
    <label for="respond-to">Respond To</label>
    <input id="respond-to" type="text" bind:value={respondTo} placeholder="UUID of letter this responds to" />
  </div>

  <div class="button-row">
    <button type="submit" class="submit-btn">
      {formType === "add" ? "Add Letter" : "Send Letter"}
    </button>
  </div>
</form>

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
  .field-row label {
    color: var(--clr-sub);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .field-row input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    outline: none;
  }
  .field-row input:focus {
    border-color: #6a6a9a;
  }
  .field-row input::placeholder {
    color: #555;
  }
  .hint {
    font-size: 0.72rem;
    color: var(--clr-muted);
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
</style>

<script>
  import SearchDialog from "./SearchDialog.svelte";

  let {
    senderLabel = "Sender",
    recipientLabel = "Recipient",
    senderText = $bindable(""),
    recipientText = $bindable(""),
    contactSuggestions = [],
    filteredSuggestions = [],
    showSuggestions = false,
    onOpenSenderDialog = () => {},
    onOpenRecipientDialog = () => {},
    onSuggestionSelect = () => {},
    // Dialog states (controlled by parent)
    showSenderDialog = false,
    showRecipientDialog = false,
    onSenderDialogClose = () => {},
    onRecipientDialogClose = () => {},
    onProfileSelect = () => {},
    onContactSelect = () => {},
    onRecipientFocus = () => {},
    onRecipientBlur = () => {},
    onRecipientInput = () => {},
  } = $props();
</script>

<!-- Sender field (multiline) -->
<div class="field-row">
  <div class="field-header">
    <label for="sender">{senderLabel}</label>
    <button type="button" class="import-btn" onclick={onOpenSenderDialog} title="Import from profile">
      &#x1F517; Profile
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
    <button type="button" class="import-btn" onclick={onOpenRecipientDialog} title="Import from contact">
      &#x1F517; Contact
    </button>
  </div>
  <textarea
    id="recipient"
    class="multi-textarea"
    bind:value={recipientText}
    placeholder="Recipient name&#10;Street address&#10;email@example.com&#10;+1-234-567-8900"
    rows="4"
    onfocus={onRecipientFocus}
    onblur={onRecipientBlur}
    oninput={onRecipientInput}
  ></textarea>
  {#if showSuggestions && filteredSuggestions.length > 0}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="suggestion-popup" role="listbox" tabindex="-1" onmousedown={(e) => e.preventDefault()}>
      {#each filteredSuggestions as entry}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="suggestion-item" role="option" tabindex="-1" aria-selected={false} onmousedown={() => { onSuggestionSelect(entry); }}>
          {entry.label}
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Sender profile search dialog -->
{#if showSenderDialog}
  <SearchDialog
    endpoint="/profiles/profiles"
    title="Select Profile"
    placeholder="Search profiles\u2026"
    onselect={onProfileSelect}
    onclose={onSenderDialogClose}
  />
{/if}

<!-- Recipient contact search dialog -->
{#if showRecipientDialog}
  <SearchDialog
    endpoint="/contacts/contacts"
    title="Select Contact"
    placeholder="Search contacts\u2026"
    onselect={onContactSelect}
    onclose={onRecipientDialogClose}
  />
{/if}

<style>
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
  .field-header label {
    color: var(--clr-sub);
    font-size: 0.8rem;
    font-weight: 600;
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

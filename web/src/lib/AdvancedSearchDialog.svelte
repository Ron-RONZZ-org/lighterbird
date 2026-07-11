<script>
  /**
   * AdvancedSearchDialog.svelte
   *
   * Modal dialog for advanced email search with all available fields.
   * Header and Body are separate fields; the checkboxes are removed.
   * Folder is a <select> dropdown fetched from the API.
   * Dates use From/To labels (inclusive).
   */
  import { createDialogTrap } from "./listTabShared.svelte.js";
  import { email as emailApi } from "./api.js";

  let {
    show = false,
    currentFilters = {},
    accountEmail = "",
    onSearch = () => {},
    onClose = () => {},
  } = $props();

  // Local state for form fields
  let headerText = $state("");
  let bodyText = $state("");
  let from = $state("");
  let subject = $state("");
  let to = $state("");
  let cc = $state("");
  let bcc = $state("");
  let participant = $state("");
  let priority = $state("");
  let folder = $state("");
  let dateFrom = $state("");
  let dateTo = $state("");

  // Folder list for the dropdown
  let folderList = $state([]);

  // Load folders when dialog opens
  $effect(() => {
    if (show) {
      emailApi.listFolders().then((res) => {
        folderList = res.folders || [];
      }).catch(() => {});
    }
  });

  // Sync local state from currentFilters when dialog opens
  $effect(() => {
    if (show) {
      headerText = currentFilters.header_text || "";
      bodyText = currentFilters.body_text || "";
      from = currentFilters.from || "";
      subject = currentFilters.subject || "";
      to = currentFilters.to || "";
      cc = currentFilters.cc || "";
      bcc = currentFilters.bcc || "";
      participant = currentFilters.participant || "";
      priority = currentFilters.priority || "";
      folder = currentFilters.folder || "";
      dateFrom = currentFilters.date_from || "";
      dateTo = currentFilters.date_to || "";
    }
  });

  // Filter folders by account if accountEmail is known
  let filteredFolders = $derived(
    accountEmail
      ? folderList.filter((f) => f.account_email === accountEmail)
      : folderList,
  );

  function resetAll() {
    headerText = ""; bodyText = ""; from = ""; subject = "";
    to = ""; cc = ""; bcc = ""; participant = "";
    priority = ""; folder = ""; dateFrom = ""; dateTo = "";
  }

  function handleSearch() {
    const filters = {};
    // Header search → local SQL (subject, from, to, cc)
    if (headerText) filters.header_text = headerText;
    // Body search → IMAP SEARCH
    if (bodyText) filters.body_text = bodyText;
    // Structured header fields
    if (from) filters.from = from;
    if (subject) filters.subject = subject;
    if (to) filters.to = to;
    if (cc) filters.cc = cc;
    if (bcc) filters.bcc = bcc;
    if (participant) filters.participant = participant;
    if (priority) filters.priority = priority;
    if (folder) filters.folder = folder;
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;

    onSearch(filters);
    onClose();
  }

  const trapKeydown = createDialogTrap(null, (e) => {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault(); handleSearch();
    }
  });

  let overlay = $state(null);
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="overlay" onclick={onClose} onkeydown={trapKeydown} role="dialog"
       aria-modal="true" aria-label="Advanced email search"
       bind:this={overlay} tabindex="0">
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div class="dialog" onclick={(e) => e.stopPropagation()} role="document">
      <h3>Advanced Search</h3>

      <div class="form-grid">
        <!-- Row 1: Standard header fields (2 cols) -->
        <div class="field">
          <label for="as-from">From</label>
          <input id="as-from" type="text" placeholder="Sender address or name"
                 bind:value={from} />
        </div>
        <div class="field">
          <label for="as-subject">Subject</label>
          <input id="as-subject" type="text" placeholder="Subject contains…"
                 bind:value={subject} />
        </div>
        <div class="field">
          <label for="as-to">To</label>
          <input id="as-to" type="text" placeholder="Recipient address"
                 bind:value={to} />
        </div>
        <div class="field">
          <label for="as-cc">CC</label>
          <input id="as-cc" type="text" placeholder="CC address"
                 bind:value={cc} />
        </div>
        <div class="field">
          <label for="as-bcc">BCC</label>
          <input id="as-bcc" type="text" placeholder="BCC address (sent only)"
                 bind:value={bcc} />
        </div>
        <div class="field">
          <label for="as-participant">Participant</label>
          <input id="as-participant" type="text"
                 placeholder="In From, To, or CC"
                 bind:value={participant} />
        </div>
        <div class="field">
          <label for="as-priority">Priority</label>
          <select id="as-priority" bind:value={priority}>
            <option value="">Any</option>
            <option value="1">1 — Urgent</option>
            <option value="2">2</option>
            <option value="3">3 — High</option>
            <option value="5">5 — Normal</option>
            <option value="7">7 — Low</option>
            <option value="9">9</option>
            <option value="10">10 — Least urgent</option>
          </select>
        </div>
        <div class="field">
          <label for="as-folder">Folder</label>
          <select id="as-folder" bind:value={folder}>
            <option value="">All folders</option>
            {#each filteredFolders as fldr (fldr.label)}
              <option value={fldr.folder_name}>{fldr.label}</option>
            {/each}
          </select>
        </div>
        <div class="field">
          <label for="as-date-from">From date</label>
          <input id="as-date-from" type="date" bind:value={dateFrom} />
        </div>
        <div class="field">
          <label for="as-date-to">To date</label>
          <input id="as-date-to" type="date" bind:value={dateTo} />
        </div>
      </div>

      <!-- Full-width fields: Header text + Body text (replace free text + checkboxes) -->
      <div class="text-fields">
        <div class="field full">
          <label for="as-header">Header</label>
          <input id="as-header" type="text"
                 placeholder="Search in subject, from, to, cc (fast, local)"
                 bind:value={headerText} />
        </div>
        <div class="field full">
          <label for="as-body">Body</label>
          <input id="as-body" type="text"
                 placeholder="Search in message body (via IMAP, slower)"
                 bind:value={bodyText} />
        </div>
      </div>

      <div class="actions">
        <button class="btn primary" onclick={handleSearch}>Search</button>
        <button class="btn" onclick={resetAll}>Reset</button>
        <button class="btn" onclick={onClose}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.65);
    display: flex; align-items: center; justify-content: center;
    z-index: 300;
  }
  .dialog {
    background: #1e1e32; border: 1px solid #444;
    border-radius: 10px; padding: 1.5rem;
    min-width: 520px; max-width: 600px;
    max-height: 85vh; overflow-y: auto;
    font-family: monospace; color: #e0e0e0;
  }
  h3 { margin: 0 0 1rem; font-size: 1rem; font-weight: 600; }
  .form-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
  }
  .text-fields {
    display: flex; flex-direction: column; gap: 0.6rem;
    margin: 0.8rem 0;
    border-top: 1px solid #333;
    padding-top: 0.8rem;
  }
  .field { display: flex; flex-direction: column; gap: 0.2rem; }
  .field.full { width: 100%; }
  .field label {
    font-size: 0.72rem; color: #7c7c9a;
    text-transform: uppercase; letter-spacing: 0.06em;
  }
  .field input, .field select {
    padding: 0.35rem 0.5rem;
    border: 1px solid #444; border-radius: 4px;
    background: #16162a; color: #e0e0e0;
    font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .field input:focus, .field select:focus { border-color: #6a6a9a; }
  .actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.5rem; }
  .btn {
    padding: 0.4rem 1rem; border: 1px solid #444;
    border-radius: 4px; background: #2a2a3e; color: #e0e0e0;
    cursor: pointer; font-family: monospace; font-size: 0.85rem;
    transition: background 0.1s;
  }
  .btn:hover { background: #3a3a5e; }
  .btn.primary { background: #3a5a8a; border-color: #4a6a9a; }
  .btn.primary:hover { background: #4a6a9a; }
</style>

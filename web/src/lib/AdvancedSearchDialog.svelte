<script>
  /**
   * AdvancedSearchDialog.svelte
   *
   * Modal dialog for advanced email search with all available fields.
   * On submit, calls onSearch with the collected filters.
   * If currentFilters is passed, fields are pre-filled for editing.
   */
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    show = false,
    currentFilters = {},
    onSearch = () => {},
    onClose = () => {},
  } = $props();

  // Local state for form fields (initialized from currentFilters)
  let query = $state("");
  let from = $state("");
  let sender = $state("");
  let subject = $state("");
  let to = $state("");
  let cc = $state("");
  let bcc = $state("");
  let participant = $state("");
  let priority = $state("");
  let after = $state("");
  let before = $state("");
  let body = $state(false);
  let header = $state(false);
  let folder = $state("");

  // Sync local state from currentFilters when dialog opens
  $effect(() => {
    if (show) {
      query = currentFilters.query || "";
      from = currentFilters.from || "";
      sender = currentFilters.sender || "";
      subject = currentFilters.subject || "";
      to = currentFilters.to || "";
      cc = currentFilters.cc || "";
      bcc = currentFilters.bcc || "";
      participant = currentFilters.participant || "";
      priority = currentFilters.priority || "";
      after = currentFilters.after || "";
      before = currentFilters.before || "";
      body = !!currentFilters.body;
      header = !!currentFilters.header;
      folder = currentFilters.folder || "";
    }
  });

  function resetAll() {
    query = ""; from = ""; sender = ""; subject = "";
    to = ""; cc = ""; bcc = ""; participant = "";
    priority = ""; after = ""; before = "";
    body = false; header = false; folder = "";
  }

  function handleSearch() {
    const filters = {};
    if (query) filters.query = query;
    if (from) filters.from = from;
    if (sender) filters.sender = sender;
    if (subject) filters.subject = subject;
    if (to) filters.to = to;
    if (cc) filters.cc = cc;
    if (bcc) filters.bcc = bcc;
    if (participant) filters.participant = participant;
    if (priority) filters.priority = priority;
    if (after) filters.after = after;
    if (before) filters.before = before;
    if (body) filters.body = true;
    if (header) filters.header = true;
    if (folder) filters.folder = folder;
    onSearch(filters);
    onClose();
  }

  const trapKeydown = createDialogTrap(null, (e) => {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault(); handleSearch();
    }
  });

  let overlay;
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
        <div class="field">
          <label for="as-query">Free text</label>
          <input id="as-query" type="text" placeholder="Search all fields…"
                 bind:value={query} />
        </div>
        <div class="field">
          <label for="as-from">From</label>
          <input id="as-from" type="text" placeholder="Sender address or name"
                 bind:value={from} />
        </div>
        <div class="field">
          <label for="as-sender">Sender (alias)</label>
          <input id="as-sender" type="text" placeholder="Alias for --from"
                 bind:value={sender} />
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
          <input id="as-folder" type="text" placeholder="Folder name"
                 bind:value={folder} />
        </div>
        <div class="field">
          <label for="as-after">After date</label>
          <input id="as-after" type="date" bind:value={after} />
        </div>
        <div class="field">
          <label for="as-before">Before date</label>
          <input id="as-before" type="date" bind:value={before} />
        </div>
      </div>

      <div class="check-row">
        <label>
          <input type="checkbox" bind:checked={body} />
          Search message body (IMAP, slower)
        </label>
        <label>
          <input type="checkbox" bind:checked={header} />
          Headers only (fast)
        </label>
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
  .field { display: flex; flex-direction: column; gap: 0.2rem; }
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
  .check-row {
    display: flex; gap: 1.5rem; margin: 0.8rem 0;
    font-size: 0.82rem;
  }
  .check-row label { display: flex; align-items: center; gap: 0.3rem; cursor: pointer; }
  .actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
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

<script>
  /**
   * Generic search+select dialog.
   *
   * Props:
   *   endpoint  — API endpoint path (e.g. "/contacts/contacts")
   *   title     — Dialog heading
   *   fields    — Array of field names to display as columns (e.g. ["full_name", "emails"])
   *   labelFn   — Optional function(item) returning a display label
   *   detailFn  — Optional function(item) returning one-line detail string
   *   placeholder — Search input placeholder
   *   onselect  — Called with the selected item object
   *   onclose   — Called when dialog is dismissed
   */
  let { endpoint = "", title = "Search", fields = [], labelFn, detailFn, placeholder = "Type to search…", onselect, onclose } = $props();

  let query = $state("");
  let results = $state([]);
  let loading = $state(false);
  let error = $state("");
  let selectedIndex = $state(-1);

  let controller = null;

  function doSearch(q) {
    if (controller) controller.abort();
    if (q.trim().length < 2) {
      results = [];
      loading = false;
      return;
    }
    loading = true;
    error = "";
    controller = new AbortController();
    const qs = new URLSearchParams({ query: q.trim(), limit: "20" });
    fetch(`/api/v1${endpoint}?${qs}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        const items = data?.profiles || data?.contacts || data?.results || data || [];
        results = Array.isArray(items) ? items : [];
        selectedIndex = results.length > 0 ? 0 : -1;
        loading = false;
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        error = `Search failed: ${err.message}`;
        loading = false;
      });
  }

  let debounceTimer;
  function onInput(e) {
    query = e.target.value;
    clearTimeout(debounceTimer);
    if (query.trim().length < 2) {
      results = [];
      return;
    }
    debounceTimer = setTimeout(() => doSearch(query), 300);
  }

  function handleSelect(item) {
    onselect?.(item);
    onclose?.();
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      onclose?.();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
    } else if (e.key === "Enter" && selectedIndex >= 0 && selectedIndex < results.length) {
      e.preventDefault();
      handleSelect(results[selectedIndex]);
    }
  }

  function defaultLabel(item) {
    if (fields.length > 0) return item[fields[0]] || "(unnamed)";
    return item.full_name || item.given_name || item.name || "(unnamed)";
  }

  function formatEmails(item) {
    try {
      const emails = typeof item.emails === "string" ? JSON.parse(item.emails) : (item.emails || []);
      if (Array.isArray(emails) && emails.length > 0) {
        return emails.map((e) => e.value || e).join(", ");
      }
    } catch {}
    return "";
  }

  function formatPhones(item) {
    try {
      const phones = typeof item.phones === "string" ? JSON.parse(item.phones) : (item.phones || []);
      if (Array.isArray(phones) && phones.length > 0) {
        return phones.map((p) => p.value || p).join(", ");
      }
    } catch {}
    return "";
  }

  function defaultDetail(item) {
    const parts = [];
    const email = formatEmails(item);
    if (email) parts.push(email);
    const phone = formatPhones(item);
    if (phone) parts.push(phone);
    return parts.join(" · ");
  }

  /** Build a structured text block for letter-head auto-fill: name \\n address \\n email \\n phone */
  function buildStructuredText(item) {
    const lines = [];
    // Name
    lines.push(item.full_name || item.given_name || item.name || "");
    // Address
    lines.push(item.address || "");
    // Email
    const email = formatEmails(item);
    lines.push(email || "");
    // Phone
    const phone = formatPhones(item);
    lines.push(phone || "");
    return lines.join("\n");
  }
</script>

<div class="dialog-backdrop" onclick={onclose} onkeydown={handleKeydown} role="button" tabindex="-1" aria-label="Close">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="dialog" onclick={(e) => e.stopPropagation()} onkeydown={handleKeydown}>
    <div class="dialog-header">
      <span class="dialog-title">{title}</span>
      <button class="close-btn" onclick={onclose} aria-label="Close">&times;</button>
    </div>

    <div class="search-row">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        class="search-input"
        placeholder={placeholder}
        value={query}
        oninput={onInput}
        onkeydown={handleKeydown}
        autofocus
      />
      {#if loading}
        <span class="spinner" aria-label="Searching…"></span>
      {/if}
    </div>

    {#if error}
      <p class="error-msg">{error}</p>
    {/if}

    {#if query.trim().length >= 2 && !loading && results.length === 0 && !error}
      <p class="no-results">No results found.</p>
    {/if}

    <div class="results-list" role="listbox">
      {#each results as item, i}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div
          class="result-item"
          class:selected={i === selectedIndex}
          role="option"
          aria-selected={i === selectedIndex}
          tabindex="-1"
          onclick={() => handleSelect(item)}
          onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(item); } }}
          onmouseenter={() => (selectedIndex = i)}
        >
          <span class="result-label">{labelFn ? labelFn(item) : defaultLabel(item)}</span>
          <span class="result-detail">{detailFn ? detailFn(item) : defaultDetail(item)}</span>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .dialog-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .dialog {
    background: #1a1a30;
    border: 1px solid #444;
    border-radius: 8px;
    width: min(500px, 90vw);
    max-height: min(500px, 80vh);
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
  }
  .dialog-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid #333;
  }
  .dialog-title {
    font-family: monospace;
    font-size: 0.9rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .close-btn {
    background: none;
    border: none;
    color: #7c7c9a;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0.1rem 0.3rem;
    border-radius: 4px;
  }
  .close-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .search-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid #2a2a44;
  }
  .search-input {
    flex: 1;
    padding: 0.4rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    outline: none;
  }
  .search-input:focus {
    border-color: #6a6a9a;
  }
  .search-input::placeholder {
    color: #555;
  }
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid #444;
    border-top-color: #6a6a9a;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .error-msg {
    color: #c44;
    padding: 0.5rem 1rem;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .no-results {
    color: var(--clr-muted);
    padding: 2rem;
    text-align: center;
    font-family: monospace;
    font-size: 0.85rem;
  }
  .results-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.3rem 0;
  }
  .result-item {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: background 0.1s;
  }
  .result-item:hover,
  .result-item.selected {
    background: #222244;
    border-left-color: #6a6a9a;
  }
  .result-label {
    font-family: monospace;
    font-size: 0.85rem;
    color: #e0e0e0;
  }
  .result-detail {
    font-size: 0.72rem;
    color: var(--clr-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>

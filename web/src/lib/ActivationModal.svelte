<script>
  import { sieve as sieveApi } from "./api.js";

  let { script, accounts, show = false, onClose } = $props();

  // All accounts with activation status for this script
  let activationMap = $state({});
  let searchQuery = $state("");

  // Filtered accounts based on search
  let filteredAccounts = $derived.by(() => {
    if (!searchQuery.trim()) return accounts || [];
    const q = searchQuery.toLowerCase();
    return (accounts || []).filter((a) => a.email.toLowerCase().includes(q));
  });

  // Split into active and inactive
  let activeAccounts = $derived(
    (accounts || []).filter((a) => activationMap[a.uuid]?.active)
  );
  let inactiveAccounts = $derived(
    filteredAccounts.filter((a) => !activationMap[a.uuid]?.active)
  );

  let loading = $state(false);

  // Load activation state
  $effect(() => {
    if (show && script && accounts?.length) {
      loadActivations();
    }
  });

  async function loadActivations() {
    loading = true;
    try {
      const result = await sieveApi.list({});
      const map = {};
      for (const acct of accounts || []) {
        const matching = (result.scripts || []).find(
          (s) => s.name === script.name && s.aktivado
        );
        // aktivado is per-account — fetch each separately
        try {
          const detail = await sieveApi.get(script.name, acct.uuid);
          if (detail?.aktivado) {
            map[acct.uuid] = detail.aktivado;
          }
        } catch { /* not activated */ }
      }
      activationMap = map;
    } catch { /* silent */ }
    loading = false;
  }

  async function toggleActivation(acct, activate) {
    try {
      if (activate) {
        await sieveApi.activate(script.name, acct.uuid);
      } else {
        await sieveApi.deactivate(script.name, acct.uuid);
      }
      await loadActivations();
    } catch (err) {
      // error will be shown via the error popup
      throw err;
    }
  }

  async function activateAll() {
    loading = true;
    for (const acct of accounts || []) {
      try {
        await sieveApi.activate(script.name, acct.uuid);
      } catch { /* skip failed */ }
    }
    await loadActivations();
    loading = false;
  }

  async function deactivateAll() {
    loading = true;
    for (const acct of activeAccounts) {
      try {
        await sieveApi.deactivate(script.name, acct.uuid);
      } catch { /* skip failed */ }
    }
    await loadActivations();
    loading = false;
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="modal-overlay" onclick={() => onClose?.()}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Activation management">
      <div class="modal-header">
        <h3>Activation: {script?.name}</h3>
        <button class="close-btn" onclick={() => onClose?.()} title="Close">✕</button>
      </div>

      <div class="modal-body">
        <!-- Bulk actions -->
        <div class="bulk-actions">
          <button class="btn" onclick={activateAll} disabled={loading}>Activate on all</button>
          <button class="btn danger" onclick={deactivateAll}
            disabled={loading || activeAccounts.length === 0}>Deactivate on all</button>
        </div>

        <!-- Search bar -->
        <div class="search-bar">
          <input
            type="text"
            placeholder="Search accounts by email..."
            bind:value={searchQuery}
          />
        </div>

        {#if loading}
          <p class="loading-text">Loading...</p>
        {/if}

        <!-- Active accounts -->
        {#if activeAccounts.length > 0}
          <h4>Active ({activeAccounts.length})</h4>
          <div class="account-list">
            {#each activeAccounts as acct (acct.uuid)}
              <div class="account-row active">
                <span class="account-email">{acct.email}</span>
                <span class="account-priority">priority={activationMap[acct.uuid]?.priority ?? 0}</span>
                <button class="btn small danger" onclick={() => toggleActivation(acct, false)}
                  title="Deactivate on this account">✕</button>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Inactive (searchable) accounts -->
        {#if inactiveAccounts.length > 0}
          <h4>{searchQuery ? "Matching accounts" : "Available accounts"} ({inactiveAccounts.length})</h4>
          <div class="account-list">
            {#each inactiveAccounts as acct (acct.uuid)}
              <div class="account-row inactive">
                <span class="account-email">{acct.email}</span>
                <button class="btn small primary" onclick={() => toggleActivation(acct, true)}
                  title="Activate on this account">+ Activate</button>
              </div>
            {/each}
          </div>
        {:else if !loading && searchQuery}
          <p class="empty-text">No accounts match "{searchQuery}"</p>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal {
    background: #1a1a2e;
    border: 1px solid #4a4a6a;
    border-radius: 6px;
    width: 480px;
    max-width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    font-family: monospace;
    font-size: 0.85rem;
  }
  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.7rem 1rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .modal-header h3 {
    margin: 0;
    font-size: 0.95rem;
    color: #e0e0e0;
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--clr-muted);
    font-size: 1.1rem;
    cursor: pointer;
    padding: 0.2rem;
  }
  .close-btn:hover { color: #e0e0e0; }
  .modal-body {
    padding: 0.7rem 1rem;
    overflow-y: auto;
    flex: 1;
  }
  .bulk-actions {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.7rem;
  }
  .btn {
    padding: 0.3rem 0.6rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
  }
  .btn:hover { background: #3a3a5a; }
  .btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .btn.primary:hover { background: #1e3a1e; }
  .btn.danger { border-color: #8a3a3a; color: #e07070; }
  .btn.danger:hover { background: #3a2020; }
  .btn.small { padding: 0.15rem 0.4rem; font-size: 0.72rem; }
  .btn:disabled { opacity: 0.5; }
  .search-bar { margin-bottom: 0.7rem; }
  .search-bar input {
    width: 100%;
    padding: 0.35rem 0.5rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    box-sizing: border-box;
  }
  .search-bar input:focus { outline: none; border-color: #6a6a9a; }
  h4 {
    margin: 0.5rem 0 0.3rem 0;
    color: var(--clr-muted);
    font-size: 0.78rem;
  }
  .account-list {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .account-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3rem 0.5rem;
    border-radius: 3px;
    gap: 0.5rem;
  }
  .account-row.active { background: #1a2a1e; }
  .account-row.inactive:hover { background: #2a2a44; }
  .account-email {
    flex: 1;
    color: #e0e0e0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .account-priority {
    color: var(--clr-muted);
    font-size: 0.72rem;
  }
  .loading-text, .empty-text {
    color: var(--clr-muted);
    text-align: center;
    padding: 1rem;
  }
</style>

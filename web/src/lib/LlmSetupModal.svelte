<script>
  let {
    onConfigured = () => {},
    onDismiss = () => {},
  } = $props();

  let step = $state("select"); // "select" | "enter-key" | "custom" | "done"
  let providerType = $state("openai");
  let apiKey = $state("");
  let baseUrl = $state("");
  let model = $state("");
  let saving = $state(false);
  let error = $state("");

  const PROVIDERS = [
    {
      id: "openai",
      name: "OpenAI",
      baseUrl: "https://api.openai.com",
      model: "gpt-4o",
      desc: "GPT-4o, GPT-4, GPT-3.5",
      needsKey: true,
    },
    {
      id: "deepseek",
      name: "DeepSeek",
      baseUrl: "https://api.deepseek.com",
      model: "deepseek-chat",
      desc: "DeepSeek-V3, DeepSeek-R1",
      needsKey: true,
    },
    {
      id: "ollama",
      name: "Ollama (local)",
      baseUrl: "http://localhost:11434",
      model: "llama3.2",
      desc: "Run models locally, no API key needed",
      needsKey: false,
    },
    {
      id: "custom",
      name: "Custom provider",
      baseUrl: "",
      model: "",
      desc: "Any OpenAI-compatible API",
      needsKey: true,
    },
  ];

  let selectedProvider = $state(null);

  function selectProvider(p) {
    selectedProvider = p;
    providerType = p.id;
    baseUrl = p.baseUrl;
    model = p.model;
    apiKey = "";
    error = "";

    if (p.id === "ollama") {
      step = "done";
      saveConfig();
    } else if (p.id === "custom") {
      step = "custom";
    } else {
      step = "enter-key";
    }
  }

  async function saveConfig() {
    saving = true;
    error = "";
    try {
      const resp = await fetch("/api/v1/llm/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: providerType,
          api_key: apiKey,
          base_url: baseUrl,
          model: model,
          temperature: 0.7,
          max_tokens: 2048,
        }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${resp.status}`);
      }
      onConfigured();
    } catch (err) {
      error = err.message;
    } finally {
      saving = false;
    }
  }

  function handleCustomSave() {
    if (!baseUrl) {
      error = "Base URL is required.";
      return;
    }
    if (!model) {
      error = "Model name is required.";
      return;
    }
    step = "done";
    saveConfig();
  }
</script>

{#if step === "select"}
  <div class="modal-overlay" onclick={onDismiss}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>Configure LLM</h2>
        <p class="subtitle">Choose a provider to enable AI chat</p>
      </div>
      <div class="provider-list">
        {#each PROVIDERS as p}
          <button class="provider-card" onclick={() => selectProvider(p)}>
            <span class="provider-name">{p.name}</span>
            <span class="provider-desc">{p.desc}</span>
          </button>
        {/each}
      </div>
      <button class="dismiss-btn" onclick={onDismiss}>Skip — use !commands only</button>
    </div>
  </div>

{:else if step === "enter-key"}
  <div class="modal-overlay" onclick={onDismiss}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>{selectedProvider?.name}</h2>
        <p class="subtitle">Paste your API key to get started</p>
      </div>
      <div class="form">
        <label class="field">
          <span class="field-label">API Key</span>
          <input
            type="password"
            class="text-input"
            bind:value={apiKey}
            placeholder="sk-..."
            autofocus
          />
        </label>
        {#if error}
          <p class="error">{error}</p>
        {/if}
        <div class="form-actions">
          <button class="btn-primary" onclick={saveConfig} disabled={saving || !apiKey}>
            {saving ? "Saving…" : "Save & Start"}
          </button>
          <button class="btn-secondary" onclick={() => { step = "select"; }}>Back</button>
        </div>
      </div>
    </div>
  </div>

{:else if step === "custom"}
  <div class="modal-overlay" onclick={onDismiss}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>Custom Provider</h2>
        <p class="subtitle">Configure any OpenAI-compatible API</p>
      </div>
      <div class="form">
        <label class="field">
          <span class="field-label">Base URL</span>
          <input type="text" class="text-input" bind:value={baseUrl} placeholder="https://api.example.com" autofocus />
        </label>
        <label class="field">
          <span class="field-label">Model</span>
          <input type="text" class="text-input" bind:value={model} placeholder="gpt-4o" />
        </label>
        <label class="field">
          <span class="field-label">API Key</span>
          <input type="password" class="text-input" bind:value={apiKey} placeholder="sk-..." />
        </label>
        {#if error}
          <p class="error">{error}</p>
        {/if}
        <div class="form-actions">
          <button class="btn-primary" onclick={handleCustomSave} disabled={saving || !baseUrl || !model}>
            {saving ? "Saving…" : "Save & Start"}
          </button>
          <button class="btn-secondary" onclick={() => { step = "select"; }}>Back</button>
        </div>
      </div>
    </div>
  </div>

{:else if step === "done"}
  <div class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h2>✓ Configured</h2>
        <p class="subtitle">{selectedProvider?.name} is ready. You can now chat with the AI.</p>
      </div>
      <div class="form-actions" style="justify-content: center; margin-top: 1rem;">
        <button class="btn-primary" onclick={onConfigured}>Start Chatting</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 16px;
    padding: 1.5rem;
    width: 400px;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h2 {
    font-size: 1.1rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .subtitle {
    font-size: 0.8rem;
    color: #7c7c9a;
    margin-top: 0.25rem;
  }
  .provider-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .provider-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 0.75rem 1rem;
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 10px;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    transition: background 0.1s, border-color 0.1s;
    width: 100%;
    text-align: left;
  }
  .provider-card:hover {
    background: #3a3a5a;
    border-color: #7c7c9a;
  }
  .provider-name { font-weight: 600; }
  .provider-desc { font-size: 0.78rem; color: #7c7c9a; margin-top: 2px; }
  .dismiss-btn {
    display: block;
    margin: 1rem auto 0;
    background: none;
    border: none;
    color: #5a5a7a;
    font-size: 0.8rem;
    cursor: pointer;
    text-align: center;
  }
  .dismiss-btn:hover { color: #9a9ac0; }

  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-label {
    font-size: 0.78rem;
    color: #7c7c9a;
    font-family: monospace;
  }
  .text-input {
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 0.6rem 0.8rem;
    color: #e0e0e0;
    font-size: 0.9rem;
    outline: none;
    font-family: monospace;
  }
  .text-input:focus { border-color: #7c7c9a; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary {
    padding: 0.5rem 1rem;
    border-radius: 8px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-primary {
    background: #3a6a3a;
    color: #e0e0e0;
    border-color: #4a8a4a;
    flex: 1;
  }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>

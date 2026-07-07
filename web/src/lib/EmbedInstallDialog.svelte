<script>
  /**
   * EmbedInstallDialog — model picker for installing a local embedding model.
   *
   * Props:
   *   models: Array of {label, hf_id, dim, size_mb, languages}
   *   oninstall(model_key): called after successful install
   *   onskip(): called when user dismisses
   */

  let { models = [], oninstall = () => {}, onskip = () => {} } = $props();

  /** Selected model key (default: bge-small-en-v1.5) */
  let selectedModel = $state("bge-small-en-v1.5");
  let installing = $state(false);
  let statusMsg = $state("");

  function getModel(key) {
    return models.find((m) => m.hf_id?.includes(key) || m.hf_id === key) || {};
  }

  /** Model key from human-readable label */
  function modelKeyForLabel(label) {
    if (label.includes("Multilingual")) return "paraphrase-multilingual-MiniLM-L12-v2";
    return "bge-small-en-v1.5";
  }

  async function handleInstall() {
    installing = true;
    statusMsg = "Installing embedding model…";
    try {
      const resp = await fetch("/api/v1/embed/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: selectedModel }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Install failed" }));
        statusMsg = err.detail || "Install failed";
        installing = false;
        return;
      }
      const result = await resp.json();
      statusMsg = result.message || "Install complete";
      setTimeout(() => oninstall(selectedModel), 800);
    } catch (err) {
      statusMsg = err.message || "Network error";
      installing = false;
    }
  }

  function handleSkip() {
    onskip();
  }

  function selectModel(label) {
    selectedModel = modelKeyForLabel(label);
  }
</script>

<div class="embed-overlay">
  <div class="embed-dialog">
    <h3 class="dialog-title">Style-Aware Suggestions</h3>
    <p class="dialog-desc">
      Improve LLM writing suggestions by installing a local embedding model.
      Your writing stays on your machine — no data is sent externally.
    </p>

    <div class="model-options">
      {#each models as m}
        {@const key = modelKeyForLabel(m.label)}
        <label class="model-card" class:selected={selectedModel === key}>
          <input
            type="radio"
            name="embed-model"
            value={key}
            checked={selectedModel === key}
            onchange={() => selectModel(m.label)}
            disabled={installing}
          />
          <div class="model-info">
            <span class="model-name">{m.label}</span>
            <span class="model-meta">{m.size_mb} MB &middot; {m.dim} dim</span>
          </div>
        </label>
      {/each}
    </div>

    {#if statusMsg}
      <p class="status-msg">{statusMsg}</p>
    {/if}

    <div class="dialog-actions">
      <button class="btn-skip" onclick={handleSkip} disabled={installing}>
        Skip
      </button>
      <button class="btn-install" onclick={handleInstall} disabled={installing}>
        {installing ? "Installing…" : "Install"}
      </button>
    </div>
  </div>
</div>

<style>
  .embed-overlay {
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center;
  }
  .embed-dialog {
    background: #1a1a2e; border: 1px solid #444; border-radius: 8px;
    padding: 1.5rem; max-width: 420px; width: 90%;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .dialog-title {
    margin: 0 0 0.3rem 0; font-size: 1.05rem; color: #e0e0f0;
    font-family: monospace;
  }
  .dialog-desc {
    margin: 0 0 1rem 0; font-size: 0.82rem; color: #9090a0;
    font-family: monospace; line-height: 1.4;
  }
  .model-options { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
  .model-card {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.6rem 0.8rem; border: 1px solid #333; border-radius: 6px;
    cursor: pointer; transition: border-color 0.15s, background 0.15s;
    background: #16162a;
  }
  .model-card:hover { border-color: #5a5a8a; background: #1e1e3a; }
  .model-card.selected { border-color: #6a6a9a; background: #22224a; }
  .model-card input { accent-color: #6a6a9a; }
  .model-info { display: flex; flex-direction: column; gap: 0.15rem; }
  .model-name { font-family: monospace; font-size: 0.85rem; color: #d0d0e0; }
  .model-meta { font-family: monospace; font-size: 0.72rem; color: #707080; }
  .status-msg {
    font-family: monospace; font-size: 0.78rem; color: #b0b0c0;
    margin: 0 0 0.8rem 0; text-align: center;
  }
  .dialog-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .btn-skip {
    background: #2a2a3e; border: 1px solid #444; color: #999;
    padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer;
    font-family: monospace; font-size: 0.8rem;
  }
  .btn-skip:hover { background: #3a3a5a; }
  .btn-install {
    background: #3a3a6a; border: 1px solid #5a5a8a; color: #e0e0f0;
    padding: 0.4rem 1rem; border-radius: 4px; cursor: pointer;
    font-family: monospace; font-size: 0.8rem;
  }
  .btn-install:hover:not(:disabled) { background: #4a4a8a; }
  .btn-install:disabled { opacity: 0.5; cursor: not-allowed; }
</style>

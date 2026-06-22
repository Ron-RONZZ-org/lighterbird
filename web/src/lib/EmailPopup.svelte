<script>
  let { data = {} } = $props();
  let msg = $derived(data);
</script>

<div class="email">
  <div class="field">
    <span class="label">From</span>
    <span class="value">{msg.de || ""}</span>
  </div>
  <div class="field">
    <span class="label">To</span>
    <span class="value">
      {Array.isArray(msg.al) ? msg.al.join(", ") : msg.al || ""}
    </span>
  </div>
  <div class="field">
    <span class="label">Subject</span>
    <span class="value subject">{msg.subjekto || "(no subject)"}</span>
  </div>
  <div class="field">
    <span class="label">Date</span>
    <span class="value">{msg.ricevita_je || ""}</span>
  </div>
  <div class="field">
    <span class="label">Read</span>
    <span class="value">{msg.legita ? "yes" : "no"}</span>
  </div>
  <hr />
  <div class="body-text">{msg.korpo || "(no body)"}</div>
</div>

<style>
  .email {
    font-family: system-ui, monospace;
    font-size: 0.9rem;
  }
  .field {
    display: flex;
    gap: 0.5rem;
    padding: 0.2rem 0;
  }
  .label {
    color: #7c7c9a;
    min-width: 5rem;
    flex-shrink: 0;
  }
  .value {
    color: #e0e0e0;
  }
  .subject {
    font-weight: 600;
  }
  hr {
    border: none;
    border-top: 1px solid #333;
    margin: 0.75rem 0;
  }
  .body-text {
    color: #ccc;
    white-space: pre-wrap;
    line-height: 1.5;
    max-height: 40vh;
    overflow-y: auto;
  }
</style>

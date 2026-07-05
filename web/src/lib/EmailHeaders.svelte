<script>
  let { msg = {} } = $props();
</script>

<div class="headers">
  <div class="field">
    <span class="label">From</span>
    <span class="value">{msg.from_addr || ""}</span>
  </div>
  <div class="field">
    <span class="label">To</span>
    <span class="value">
      {Array.isArray(msg.to_recipients) ? msg.to_recipients.join(", ") : (msg.to_recipients || "")}
    </span>
  </div>
  <div class="field">
    <span class="label">Subject</span>
    <span class="value subject">{msg.subject || "(no subject)"}</span>
  </div>
  <div class="field">
    <span class="label">Date</span>
    <span class="value">{msg.received_at || ""}</span>
  </div>
</div>

<style>
  .headers {
    padding: 8px 12px;
    flex-shrink: 0;
  }
  .field {
    display: flex;
    gap: 0.5rem;
    padding: 0.15rem 0;
  }
  .label {
    color: var(--clr-sub);
    min-width: 5rem;
    flex-shrink: 0;
  }
  .value {
    color: #e0e0e0;
    word-break: break-all;
  }
  .subject {
    font-weight: 600;
  }
</style>

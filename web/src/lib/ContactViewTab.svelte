<script>
  /** Contact detail view — structured field layout. */

  import { formatListItemDate } from "./listTabShared.svelte.js";
  import { renderMarkdown } from "./markdown.js";

  let { data = {} } = $props();
</script>

<div class="contact-view">
  <h1 class="name">{data.given_name || data.full_name || "(unnamed)"}</h1>

  {#if data.family_name}
    <div class="subtitle">{data.family_name}</div>
  {/if}

  <div class="meta-row">
    {#if data.created_at}
      <span class="meta-date">Added {formatListItemDate(data.created_at)}</span>
    {/if}
    {#if data.uuid}
      <span class="meta-uuid">{data.uuid.slice(0, 8)}…</span>
    {/if}
  </div>

  <div class="fields">
    {#if data.email}
      <div class="field">
        <span class="label">Email</span>
        <span class="value">{data.email}</span>
      </div>
    {/if}
    {#if data.phone}
      <div class="field">
        <span class="label">Phone</span>
        <span class="value">{data.phone}</span>
      </div>
    {/if}
    {#if data.organization}
      <div class="field">
        <span class="label">Organization</span>
        <span class="value">{data.organization}</span>
      </div>
    {/if}
    {#if data.role}
      <div class="field">
        <span class="label">Role</span>
        <span class="value">{data.role}</span>
      </div>
    {/if}
    {#if data.address}
      <div class="field">
        <span class="label">Address</span>
        <span class="value">{data.address}</span>
      </div>
    {/if}
    {#if data.note}
      <div class="field note-field">
        <span class="label">Notes</span>
        <div class="value note-value">{@html renderMarkdown(data.note)}</div>
      </div>
    {/if}
  </div>
</div>

<style>
  .contact-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
    padding: 1rem 1.5rem;
    font-size: 0.92rem;
  }
  .name {
    font-size: 1.4rem;
    font-weight: 700;
    color: #e0e0e0;
    margin: 0 0 0.15rem;
    line-height: 1.3;
  }
  .subtitle {
    color: var(--clr-sub);
    font-size: 0.9rem;
    margin-bottom: 0.3rem;
  }
  .meta-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.2rem;
    flex-wrap: wrap;
  }
  .meta-date {
    color: var(--clr-muted);
    font-size: 0.78rem;
    font-family: monospace;
  }
  .meta-uuid {
    color: #5a5a7a;
    font-size: 0.72rem;
    font-family: monospace;
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .field:last-child { border-bottom: none; }
  .label {
    font-size: 0.72rem;
    color: var(--clr-sub);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }
  .value {
    color: #e0e0e0;
    font-size: 0.92rem;
    font-family: monospace;
  }
  .note-value {
    font-family: inherit;
    line-height: 1.6;
  }
  .note-value :global(p) { margin: 0 0 0.4rem; }
  .note-value :global(p:last-child) { margin-bottom: 0; }
  .note-value :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.84rem;
  }
  .note-value :global(pre) {
    background: #111; padding: 0.5rem; border-radius: 4px;
    overflow-x: auto; font-size: 0.82rem; margin: 0.4rem 0;
  }
  .note-value :global(a) { color: #8a8acc; text-decoration: underline; }
</style>

<script>
  /** Journal entry detail view — renders title + markdown body. */

  import { renderMarkdown } from "./markdown.js";
  import { formatListItemDate } from "./listTabShared.svelte.js";

  let { data = {} } = $props();

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "p") {
      e.preventDefault();
      window.print();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="journal-view">
  <div class="print-toolbar">
    <button class="print-btn" onclick={() => window.print()} title="Print / Export PDF (Ctrl+P)">
      <kbd>Ctrl+P</kbd> Print / PDF
    </button>
  </div>

  <h1 class="title">{data.title || "(untitled)"}</h1>

  <div class="meta-row">
    <span class="meta-date">{formatListItemDate(data.date || data.created_at)}</span>
    {#if data.uuid}
      <span class="meta-uuid">{data.uuid.slice(0, 8)}…</span>
    {/if}
  </div>

  {#if data.text}
    <div class="content">{@html renderMarkdown(data.text)}</div>
  {:else}
    <p class="empty">No content.</p>
  {/if}
</div>

<style>
  .journal-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
    padding: 1rem 1.5rem;
    font-size: 0.92rem;
    line-height: 1.7;
  }
  .title {
    font-size: 1.4rem;
    font-weight: 700;
    color: #e0e0e0;
    margin: 0 0 0.3rem;
    line-height: 1.3;
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
  .content {
    flex: 1;
    color: #d0d0e0;
    max-width: 100%;
  }
  .content :global(p) { margin: 0 0 0.6rem; }
  .content :global(p:last-child) { margin-bottom: 0; }
  .content :global(pre) {
    background: #111; padding: 0.6rem; border-radius: 6px;
    overflow-x: auto; font-size: 0.82rem; margin: 0.5rem 0;
  }
  .content :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.84rem;
  }
  .content :global(pre code) { background: none; padding: 0; }
  .content :global(a) { color: #8a8acc; text-decoration: underline; }
  .content :global(blockquote) {
    border-left: 2px solid #5a5a7a; padding-left: 0.6rem;
    margin: 0.4rem 0; color: #9a9ab0;
  }
  .content :global(ul), .content :global(ol) { padding-left: 1.2rem; margin: 0.3rem 0; }
  .content :global(li) { margin: 0.1rem 0; }
  .content :global(h1), .content :global(h2), .content :global(h3) {
    margin: 0.5rem 0 0.2rem; color: #e0e0e0;
  }
  .content :global(hr) { border: none; border-top: 1px solid #333; margin: 0.5rem 0; }
  .content :global(table) {
    border-collapse: collapse; margin: 0.5rem 0; font-size: 0.85rem;
  }
  .content :global(th), .content :global(td) {
    border: 1px solid #333; padding: 0.3rem 0.6rem; text-align: left;
  }
  .content :global(th) { background: #1e1e32; color: #b0b0c0; font-weight: 600; }
  .empty {
    color: var(--clr-muted);
    font-style: italic;
    padding: 1rem 0;
  }

  .print-toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 0.5rem;
  }
  .print-btn {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #e0e0e0;
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.78rem;
    transition: background 0.15s;
  }
  .print-btn:hover {
    background: #3a3a5a;
  }
  .print-btn kbd {
    display: inline-block;
    padding: 1px 4px;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    font-size: 0.7rem;
    margin-right: 0.3rem;
  }

  /* Print styles — hide non-essential UI */
  @media print {
    :global(.tab-bar),
    :global(.command-bar),
    :global(.home-content),
    :global(.top-progress),
    .print-toolbar {
      display: none !important;
    }
    .journal-view {
      padding: 0 !important;
      color: #000 !important;
    }
    .content {
      color: #000 !important;
    }
    .content :global(a) {
      color: #0000ee !important;
    }
  }
</style>

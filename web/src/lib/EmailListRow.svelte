<script>
  import { truncate, formatListItemDate } from "./listTabShared.svelte.js";

  let {
    msg,
    index = 0,
    isSelected = false,
    isFocused = false,
    selectionMode = false,
    uuidCopy = { copiedKey: "", copyToClipboard: () => {} },
    emailCopy = { copiedKey: "", copyToClipboard: () => {} },
    onRowClick = () => {},
  } = $props();
</script>

<div
  id="row-{msg.uuid}"
  class="row"
  class:selected={isSelected}
  class:focused={isFocused}
  class:selection-mode={selectionMode}
  role="option"
  aria-selected={isSelected}
  tabindex={selectionMode ? (isFocused ? 0 : -1) : 0}
  onclick={(e) => onRowClick(e, msg)}
  onkeydown={(e) => {
    if (e.key === "Enter") onRowClick(e, msg);
  }}
>
  <span class="checkbox-cell">
    {#if selectionMode}
      <span class="checkbox" class:checked={isSelected}>
        {isSelected ? "\u2713" : ""}
      </span>
    {/if}
  </span>

  <span class="msg-uuid" role="button" tabindex="-1"
        onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(msg.uuid); }}
        onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); uuidCopy.copyToClipboard(msg.uuid); } }}
        title="Click to copy UUID">
    {uuidCopy.copiedKey === msg.uuid ? "Copied!" : msg.uuid.slice(0, 8)}
  </span>
  <span class="from" class:unread={!msg.is_read} role="button" tabindex="-1"
        onclick={(e) => {
          if (!selectionMode) { e.stopPropagation(); emailCopy.copyToClipboard(msg.from_addr || ""); }
        }}
        onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (!selectionMode) { e.stopPropagation(); emailCopy.copyToClipboard(msg.from_addr || ""); } } }}
        title="Click to copy email address">
    {emailCopy.copiedKey === msg.from_addr ? "Copied!" : truncate(msg.from_addr || "", 24)}
  </span>
  {#if msg.priority === 1}
    <span class="priority high" title="Priority 1 — Highest">‼</span>
  {:else if msg.priority === 2}
    <span class="priority high" title="Priority 2 — High">❗</span>
  {:else if msg.priority === 5}
    <span class="priority low" title="Priority 5 — Lowest">⬇</span>
  {:else if msg.priority === 4}
    <span class="priority low" title="Priority 4 — Low">↓</span>
  {:else}
    <span class="priority normal" title="Priority 3 — Normal">–</span>
  {/if}
  {#if msg.matched_in?.length}
    <span class="match-indicator" title="Matched in: {msg.matched_in.join(', ')}">
      {#each msg.matched_in.slice(0, 2) as field}
        <span class="match-badge" class:match-subject={field === 'subject'} class:match-from={field === 'from'} class:match-body={field === 'body'}>{field}</span>
      {/each}
      {#if msg.matched_in.length > 2}
        <span class="match-badge match-more">+{msg.matched_in.length - 2}</span>
      {/if}
    </span>
  {/if}
  <span class="subject" class:unread={!msg.is_read}>{truncate(msg.subject || "(no subject)", 40)}</span>
  <span class="date">{formatListItemDate(msg.received_at)}</span>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    transition: background 0.08s;
    min-height: 2rem;
  }
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.selection-mode { cursor: pointer; }

  .checkbox-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.8rem;
    flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    height: 1.1rem;
    border: 1.5px solid #7c7c9a;
    border-radius: 3px;
    font-size: 0.7rem;
    color: #e0e0e0;
    background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }

  .msg-uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .msg-uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .from {
    color: #e0e0e0;
    min-width: 10rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .from:hover { color: #ccc; text-decoration: underline; }
  .from.unread { font-weight: 700; }

  .match-indicator {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-shrink: 0;
    margin-right: 0.25rem;
  }
  .match-badge {
    font-size: 0.6rem;
    font-weight: 600;
    padding: 1px 4px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    white-space: nowrap;
  }
  .match-badge.match-subject { background: #3a6a4a; color: #a0e0a0; }
  .match-badge.match-from { background: #4a5a8a; color: #a0c0e0; }
  .match-badge.match-body { background: #6a5a3a; color: #e0c0a0; }
  .match-badge.match-more { background: #4a4a5a; color: #a0a0c0; }

  .subject {
    color: #ccc;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subject.unread { font-weight: 600; color: #e0e0e0; }
  .priority { font-size: 0.75rem; flex-shrink: 0; margin-right: 0.2rem; opacity: 0.85; min-width: 0.8rem; text-align: center; }
  .priority.high { color: #e06060; opacity: 1; }
  .priority.low { color: #707090; opacity: 0.7; }
  .priority.normal { color: #5a5a7a; opacity: 0.5; }
  .date {
    color: var(--clr-muted);
    min-width: 6rem;
    text-align: right;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
</style>

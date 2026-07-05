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
    <span class="priority high" title="Highest priority">‼</span>
  {:else if msg.priority === 2}
    <span class="priority" title="High priority">❗</span>
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
  .subject {
    color: #ccc;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subject.unread { font-weight: 600; color: #e0e0e0; }
  .priority { font-size: 0.75rem; flex-shrink: 0; margin-right: 0.15rem; opacity: 0.85; }
  .priority.high { color: #e06060; opacity: 1; }
  .date {
    color: var(--clr-muted);
    min-width: 6rem;
    text-align: right;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
</style>

<script>
  import { truncate, formatListItemDate } from "./listTabShared.svelte.js";

  let {
    letter,
    index = 0,
    isSelected = false,
    isFocused = false,
    selectionMode = false,
    highlight = false,
    highlightActive = false,
    uuidCopy = { copiedKey: "", copyToClipboard: () => {} },
    onRowClick = () => {},
  } = $props();

  function directionIcon(dir) {
    return dir === "sent" ? "\u2191" : "\u2193";
  }

  function senderDisplay(l) {
    if (l.sender_manual) return l.sender_manual;
    if (l.sender_profile) return l.sender_profile.slice(0, 8);
    return "\u2014";
  }

  function recipientDisplay(l) {
    if (l.recipient_manual) return l.recipient_manual;
    if (l.recipient_contact) return l.recipient_contact.slice(0, 8);
    return "\u2014";
  }

  function tagList(tags) {
    if (!tags || tags.length === 0) return [];
    return tags.slice(0, 3);
  }

  function tagOverflow(tags) {
    if (!tags || tags.length <= 3) return 0;
    return tags.length - 3;
  }
</script>

<div
  id="row-{letter.uuid}"
  class="row"
  class:selected={isSelected}
  class:focused={isFocused}
  class:highlight={highlight && highlightActive}
  class:selection-mode={selectionMode}
  role="option"
  aria-selected={isSelected}
  tabindex={selectionMode ? (isFocused ? 0 : -1) : 0}
  onclick={(e) => onRowClick(e, letter.uuid)}
  onkeydown={(e) => {
    if (e.key === "Enter") onRowClick(e, letter.uuid);
  }}
>
  <span class="checkbox-cell">
    {#if selectionMode}
      <span class="checkbox" class:checked={isSelected}>
        {isSelected ? "\u2713" : ""}
      </span>
    {/if}
  </span>

  <span class="dir-icon" title={letter.direction}>{directionIcon(letter.direction)}</span>

  <span class="letter-uuid" role="button" tabindex="-1"
        onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(letter.uuid); }}
        onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); uuidCopy.copyToClipboard(letter.uuid); } }}
        title="Click to copy UUID">
    {uuidCopy.copiedKey === letter.uuid ? "Copied!" : letter.uuid.slice(0, 8)}
  </span>
  <span class="date">{formatListItemDate(letter.created_at)}</span>
  <span class="object">{truncate(letter.object || "(untitled)", 28)}</span>
  <span class="sender">{truncate(senderDisplay(letter), 16)}</span>
  <span class="recipient">{truncate(recipientDisplay(letter), 16)}</span>
  {#if letter.tags && letter.tags.length > 0}
    <span class="tags-cell">
      {#each tagList(letter.tags) as t}
        <span class="tag-pill">{t}</span>
      {/each}
      {#if tagOverflow(letter.tags) > 0}
        <span class="tag-overflow">+{tagOverflow(letter.tags)}</span>
      {/if}
    </span>
  {/if}
  {#if letter.respond_to_uuid}
    <span class="reply-badge" title="Reply to {letter.respond_to_uuid.slice(0, 8)}">\u21A9</span>
  {/if}
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    transition: background 0.08s;
    min-height: 2rem;
  }
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.highlight { animation: letter-highlight-fade 2s ease-out; }
  @keyframes letter-highlight-fade {
    0% { background: rgba(42, 90, 42, 0.6); }
    100% { background: transparent; }
  }
  .row.selection-mode { cursor: pointer; }

  .checkbox-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.8rem; flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem;
    border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }

  .dir-icon {
    min-width: 1.2rem;
    text-align: center;
    font-size: 0.85rem;
    flex-shrink: 0;
    color: var(--clr-sub);
  }

  .letter-uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 4.5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .letter-uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .date {
    color: var(--clr-muted);
    min-width: 5.5rem;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
  .object {
    color: #e0e0e0;
    min-width: 8rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sender, .recipient {
    color: #b0b0c0;
    min-width: 6rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8rem;
  }

  .tags-cell {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-shrink: 0;
    max-width: 8rem;
    overflow: hidden;
  }
  .tag-pill {
    display: inline-block;
    padding: 0.05rem 0.35rem;
    font-size: 0.68rem;
    background: #2a3a4a;
    color: #8ab4d0;
    border: 1px solid #3a4a5a;
    border-radius: 3px;
    white-space: nowrap;
  }
  .tag-overflow {
    font-size: 0.65rem;
    color: #6a7a8a;
    flex-shrink: 0;
  }

  .reply-badge {
    color: #6a9a6a;
    font-size: 0.8rem;
    flex-shrink: 0;
  }
</style>

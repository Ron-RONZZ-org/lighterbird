<script>
  import { truncate, formatListItemDate } from "./listTabShared.svelte.js";

  let {
    todo,
    index = 0,
    isSelected = false,
    isFocused = false,
    selectionMode = false,
    highlight = false,
    highlightActive = false,
    uuidCopy = { copiedKey: "", copyToClipboard: () => {} },
    isTree = false,
    expanded = new Set(),
    onToggleExpand = () => {},
    onRowClick = () => {},
    priorityClass = () => "",
  } = $props();
</script>

<div
  id="row-{todo.uuid}"
  class="row"
  class:selected={isSelected}
  class:focused={isFocused}
  class:highlight={highlight && highlightActive}
  class:selection-mode={selectionMode}
  class:done={todo.status === "done"}
  class:tree-mode={isTree}
  style={isTree ? `padding-left: ${0.5 + (todo._depth || 0) * 1.5}rem` : ""}
  role="option"
  aria-selected={isSelected}
  tabindex={selectionMode ? (isFocused ? 0 : -1) : 0}
  onclick={(e) => onRowClick(e, todo.uuid)}
  onkeydown={(e) => { if (e.key === "Enter") onRowClick(e, todo.uuid); }}
>
  <span class="checkbox-cell">
    {#if selectionMode}
      <span class="checkbox" class:checked={isSelected}>
        {isSelected ? "\u2713" : ""}
      </span>
    {/if}
  </span>

  {#if isTree}
    <span class="tree-toggle-cell">
      {#if todo._has_children}
        <button class="tree-toggle"
          onclick={(e) => { e.stopPropagation(); onToggleExpand(todo.uuid); }}
          aria-label={expanded.has(todo.uuid) ? "Collapse" : "Expand"}>
          {expanded.has(todo.uuid) ? "\u25BC" : "\u25B6"}
        </button>
      {:else}
        <span class="tree-toggle-placeholder"></span>
      {/if}
    </span>
  {/if}

  <span class="tuuid" role="button" tabindex="-1"
        onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(todo.uuid); }}
        onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); uuidCopy.copyToClipboard(todo.uuid); } }}
        title="Click to copy UUID">
    {uuidCopy.copiedKey === todo.uuid ? "Copied!" : todo.uuid.slice(0, 8)}
  </span>
  <span class="title">{truncate(todo.title || "(untitled)", 32)}</span>
  <span class="priority {priorityClass(todo.priority)}">{todo.priority || ""}</span>
  <span class="due">{formatListItemDate(todo.due)}</span>
  {#if todo.labels && todo.labels.length > 0}
    <span class="labels">
      {#each todo.labels as lbl}
        <span class="tag" style={lbl.color ? `border-color:${lbl.color};color:${lbl.color}` : ""}>{lbl.name}</span>
      {/each}
    </span>
  {/if}
  <span class="status">{todo.status === "done" ? "\u2713 done" : "\u25CB"}</span>
</div>

<style>
  .row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.4rem 0.5rem; border-bottom: 1px solid #2a2a3e;
    cursor: default; transition: background 0.08s; min-height: 2rem;
  }
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.highlight { animation: todo-highlight-fade 2s ease-out; }
  @keyframes todo-highlight-fade {
    0% { background: rgba(42, 90, 42, 0.6); }
    100% { background: transparent; }
  }
  .row.selection-mode { cursor: pointer; }
  .row.done .title { opacity: 0.5; text-decoration: line-through; }
  .checkbox-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.8rem; flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem; border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .tree-toggle-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.2rem; flex-shrink: 0;
  }
  .tree-toggle {
    background: none; border: 1px solid transparent; color: var(--clr-muted);
    cursor: pointer; padding: 0; font-size: 0.55rem; width: 1.2rem; height: 1.2rem;
    display: flex; align-items: center; justify-content: center;
    border-radius: 3px; transition: all 0.1s;
  }
  .tree-toggle:hover {
    color: #e0e0e0; border-color: #4a4a6a; background: #2a2a3e;
  }
  .tree-toggle-placeholder { width: 1.2rem; }
  .tuuid {
    color: var(--clr-muted); font-size: 0.72rem; min-width: 5rem;
    flex-shrink: 0; cursor: pointer;
  }
  .tuuid:hover { color: #7c7c9a; text-decoration: underline; }
  .title { color: #e0e0e0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .priority { font-size: 0.75rem; min-width: 2rem; text-align: center; flex-shrink: 0; }
  .priority.high { color: #e07070; }
  .priority.mid { color: #d0b060; }
  .priority.low { color: var(--clr-muted); }
  .due { color: var(--clr-muted); min-width: 6rem; flex-shrink: 0; font-size: 0.78rem; }
  .labels { display: flex; gap: 0.25rem; flex-shrink: 0; min-width: 4rem; flex-wrap: wrap; }
  .tag { font-size: 0.65rem; padding: 0.05rem 0.3rem; border: 1px solid #4a4a6a; border-radius: 3px; color: #7c7c9a; white-space: nowrap; }
  .status { color: var(--clr-muted); min-width: 3rem; flex-shrink: 0; text-align: right; }
</style>

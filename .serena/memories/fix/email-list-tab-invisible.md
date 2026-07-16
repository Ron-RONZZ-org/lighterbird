# Email List Tab Invisible Bug (July 8–11, 2026)

## The Bug

`!email list` opened a tab with the toolbar visible, but the email message list was **completely empty** — showing "No messages" even though the backend returned 10+ messages.

## Root Cause

CSS `height: 100%` on `.email-list` (the toolbar wrapper div) stole **all** of the parent flex container's allocated height, leaving the sibling `.list` div with **0px** of visible space.

### How it happened

1. **Commit `322663d`** (PR #173, July 8) — "feat: advanced search UX overhaul" — accidentally deleted the email list template blocks (EmailFolderPanel, EmailSortOverlay, DropdownPanel, **and the entire message list with EmailListRow**).

2. **Commit `6742833`** (July 8) — fixed Svelte compile errors by moving the `</div>` closing tag up to right after the toolbar (the `<div class="email-list">` now wrapped **only** the toolbar).

3. **Commit `d72bd5d`** (PR #179/#180, July 10) — restored the deleted template blocks, but **kept them outside** `<div class="email-list">` because that's where the `</div>` had been moved to. The `.email-list` div still had `height: 100%` from the original design, but the `.list` was no longer inside it.

### The mechanics

```
.tab-content (display: flex; flex-direction: column; flex: 1; height: 627px)
  ├── .email-list (height: 100%)  ← flex: 0 1 auto, takes 627px → 627px
  ├── (conditional overlays — flex-out-of-flow via absolute/fixed)
  └── .list (flex: 1)             ← tries flex-grow, but 0px remaining → 0px
```

`.email-list`'s `height: 100%` resolved to 100% of `.tab-content`'s **final** flex-allocated height (627px), not the content height. Since `.email-list` had `flex-grow: 0` but an explicit `height: 100%`, the browser gave it the full 627px and left nothing for `.list`.

### The Fix

**Commit `5db0769`**: Removed `height: 100%` from `.email-list` CSS (`web/src/lib/EmailListTab.svelte`). Without it, the toolbar naturally shrinks to content height (~38px), and `.list` with `flex: 1` fills the remaining space (~590px).

## Lesson Learned

**When restructuring template layout (moving elements in/out of containers), always verify with `getBoundingClientRect()` that every element gets a non-zero visible area.**

Checklist for future template restructures:
- [ ] All elements have non-zero `getBoundingClientRect().height` after the change
- [ ] Flex parents don't have children with `height: 100%` that over-allocate space
- [ ] When moving elements out of a container, check if the container's CSS properties (`height`, `flex`, `position`) still make sense
- [ ] Viewport-aware: test at 720p and 1080p viewport heights

## Verification Method

Use browser devtools JavaScript to measure:
```js
document.querySelector('.list')?.getBoundingClientRect().height
// Should be > 0
```

The snapshot browser tool alone is insufficient — elements may exist in the DOM but have zero visible area.

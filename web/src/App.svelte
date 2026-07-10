<script>
  import PopupOverlay from "./lib/PopupOverlay.svelte";
  import BannerContainer from "./lib/BannerContainer.svelte";
  import { popup } from "./lib/popupStore.svelte.js";
  import { tabStore } from "./lib/tabStore.svelte.js";
  import { dirtyFormStore } from "./lib/dirtyFormStore.svelte.js";
  import { banner } from "./lib/bannerStore.svelte.js";
  import { execute } from "./lib/commandExecutor.js";
  import { shouldIntercept } from "./lib/commandRouter.js";
  import { findNode } from "./lib/commandTree.js";
  import { parseCommand } from "./lib/parser.js";
  import { detectPersistentType } from "./lib/persistentTypes.js";
  import { email, calendar, contacts, todo, journal, letters } from "./lib/api.js";
  import { isMutationCommand, extractHighlightUuid, persistentIdKey, LIST_REFRESHERS } from "./lib/mutationToTab.js";
  import ComposeEmail from "./lib/ComposeEmail.svelte";
  import EventForm from "./lib/EventForm.svelte";
  import ConfirmDialog from "./lib/ConfirmDialog.svelte";

  let isLoading = $state(false);
  let activeForm = $state(null);
  let resetConfirm = $state(null); // {tokens, flags} or null

  // ── Notice banner (fetched on page load, dismissible per session) ────
  let noticeMessage = $state("");
  let noticeDismissed = $state(false);
  let noticeOffline = $state(false);

  async function fetchNotice() {
    try {
      const resp = await fetch("/api/v1/chat/notice");
      if (!resp.ok) return;
      const data = await resp.json();
      if (data?.notice?.message) {
        noticeMessage = data.notice.message;
        noticeOffline = false;
      }
    } catch {
      noticeOffline = true;
      // Retry once after 5s in case the server was still starting up
      setTimeout(async () => {
        try {
          const resp = await fetch("/api/v1/chat/notice");
          if (!resp.ok) return;
          const data = await resp.json();
          if (data?.notice?.message) {
            noticeMessage = data.notice.message;
          }
          noticeOffline = false;
        } catch { /* still offline — no banner is better than a stale error */ }
      }, 5000);
    }
  }
  fetchNotice();

  // Live-update read status in all email list tabs when a message is viewed.
  // Must be here (always-mounted root), not in EmailListTab (unmounted when
  // EmailViewTab is active).
  $effect(() => {
    function handler(e) {
      const { uuid, is_read } = e.detail || {};
      if (!uuid) return;
      for (const t of tabStore.tabs) {
        if (t.data?.messages && Array.isArray(t.data.messages)) {
          const updatedMessages = t.data.messages.map((m) =>
            m.uuid === uuid ? { ...m, is_read } : m,
          );
          if (updatedMessages.some((m, i) => m !== t.data.messages[i])) {
            tabStore.update(t.id, { ...t.data, messages: updatedMessages });
          }
        }
      }
    }
    window.addEventListener("email-read-status-changed", handler);
    return () => window.removeEventListener("email-read-status-changed", handler);
  });

  /** Global keyboard shortcuts. */
  function handleGlobalKeydown(e) {
    // Alt+1/2/3/4 — switch to numbered tab
    if (e.altKey && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        tabStore.setActiveIndex(num - 1);
        return;
      }
    }

    // Alt+N / Alt+P — next / previous tab
    if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        const idx = tabStore.activeIndex;
        if (idx < tabStore.count - 1) {
          tabStore.setActiveIndex(idx + 1);
        } else {
          tabStore.setActiveIndex(0); // wrap to first tab
        }
        return;
      }
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        const idx = tabStore.activeIndex;
        if (idx > 0) {
          tabStore.setActiveIndex(idx - 1);
        } else {
          tabStore.setActiveIndex(tabStore.count - 1); // wrap to last tab
        }
        return;
      }
    }

    // Ctrl+R / Ctrl+Shift+R / Ctrl+L — email actions (dispatched to EmailViewTab)
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "r") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "reply" } }));
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "R") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "reply-all" } }));
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "l") {
      const active = tabStore.active;
      if (active && active.type === "email") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("email-action", { detail: { action: "forward" } }));
        return;
      }
    }
  }

  function loadingLabel(input) {
    const t = input.trim();
    if (t.startsWith("/*")) {
      const parts = t.slice(2).trimStart().split(/\s+/);
      const cmd = parts[0] || "";
      return cmd ? `/*${cmd}…` : "Prompt command…";
    }
    if (!t.startsWith("!")) return "Thinking…";
    const parts = t.slice(1).split(/\s+/);
    const cmd = parts.slice(0, 2).join(" ");
    if (!cmd) return "Working…";
    return `${cmd}…`;
  }

  async function handleCommand(input) {
    const trimmed = input.trim();
    if (!trimmed) return;

    isLoading = true;

    try {
      // ── Smart add-command routing (frontend interception) ──────────
      // Detects "add"/"write"/interactive commands with missing required
      // params and opens interactive form instead of sending to backend.
      if (trimmed.startsWith("!")) {
        const routing = shouldIntercept(trimmed);
        if (routing.intercept) {
          // Execute the list command to get current data
          const listInput = "!" + routing.listTokens.join(" ");
          const listResult = await execute(listInput);
          if (listResult.type === "error") {
            popup.show("error", "Error", listResult.data);
          } else {
            // Open the persistent list tab
            popup.showPersistent(
              listResult.type,
              listResult.title,
              listResult.data || {},
              routing.listIdKey,
            );
            popup.updateCache(listResult.data || {});
            // Then open the add form directly (not via autoAdd in list data)
            const enrichedInitial = {
              ...(routing.initialData || {}),
              _returnIdKey: routing.listIdKey ? `persistent-${routing.listIdKey}` : undefined,
            };
            tabStore.open("form", routing.addTitle || "Add", {
              form: routing.addFormType,
              initialData: enrichedInitial,
            }, { idKey: `form-${routing.addFormType}` });
          }
          isLoading = false;
          return;
        }
      }

      // ── Normal command execution ──────────────────────────────────
      popup.showLoading(loadingLabel(input));

      const result = await execute(input);

      // Handle form-required response type (backend fallback for
      // saved-commands/aliases that can't be expanded frontend-side)
      if (result.type === "form-required") {
        const { form, initialData, message } = result.data || {};
        if (form) {
          // Special case: reset-no-backup shows a ConfirmDialog overlay
          if (form === "reset-no-backup") {
            resetConfirm = {
              tokens: parseCommand(input).tokens,
              flags: { "no-backup": "", "confirmed": "true" },
              message: message || "This will permanently delete ALL your data.",
            };
            isLoading = false;
            return;
          }
          // Close loading, open form
          const activeId = tabStore.active?.id;
          if (activeId) tabStore.close(activeId);
          tabStore.open("form", result.title || "Complete Form", {
            form,
            initialData: initialData || {},
          }, { idKey: `form-${form}` });
          isLoading = false;
          return;
        }
      }

      // ── Mutation redirect: navigate to list tab with highlight ─────
      // After a successful add/modify/delete, redirect to the corresponding
      // list tab instead of showing a transient popup. The affected entry
      // is briefly highlighted (except on delete, where it's gone).
      if (result.type !== "error" && trimmed.startsWith("!")) {
        const { tokens } = parseCommand(trimmed);
        const mutationCfg = isMutationCommand(tokens);
        if (mutationCfg) {
          const isDelete = mutationCfg.isDelete;
          const highlightUuid = extractHighlightUuid(result, isDelete);
          const idKey = persistentIdKey(mutationCfg.listIdKey);
          const existingTab = tabStore.tabs.find(t => t.idKey === idKey && t.id !== "home");

          if (existingTab && !isDelete && highlightUuid) {
            // Tab exists and we have a highlight — inject into existing data
            // to avoid a loading flicker. The highlight auto-clears after 2s.
            tabStore.update(existingTab.id, { ...existingTab.data, highlight: highlightUuid });
            tabStore.setActive(existingTab.id);
          } else {
            // Tab doesn't exist, or it's a delete — re-fetch list data
            try {
              const listInput = "!" + mutationCfg.listTokens.join(" ");
              const listResult = await execute(listInput);
              const listData = { ...(listResult.data || {}) };
              if (!isDelete && highlightUuid) {
                listData.highlight = highlightUuid;
              }
              popup.showPersistent(
                listResult.type,
                listResult.title,
                listData,
                mutationCfg.listIdKey,
              );
            } catch {
              // Fallback to normal status display if list refresh fails
              popup.show(result.type, result.title, result.data);
            }
          }

          // Email send: show success banner
          if (result.title === "Sent" && tokens[0] === "email" && tokens[1] === "send") {
            banner.show("Message sent.", "success");
          }

          // Delete mutations: show confirmation banner so the user knows
          // the operation succeeded (the deleted entry is no longer visible).
          if (isDelete && result.title) {
            banner.show(result.title, "success");
          }

          isLoading = false;
          return;
        }
      }

      const dataType = detectPersistentType(input);
      if (dataType) {
        popup.showPersistent(result.type, result.title, result.data, dataType);
      } else {
        popup.show(result.type, result.title, result.data);
      }
    } catch (err) {
      popup.show("error", "Error", {
        message: err.message || String(err),
        suggestion: err.suggestion || "",
      });
    } finally {
      isLoading = false;
    }
  }

</script>

<svelte:window onkeydown={handleGlobalKeydown} onbeforeunload={(e) => {
    if (dirtyFormStore.hasAnyDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  }} />

<main>
  {#if noticeOffline && !noticeDismissed}
    <div class="notice-banner notice-warning" role="alert">
      <span class="notice-text">⚠ Server appears offline — some features may be unavailable</span>
      <button class="notice-close" onclick={() => { noticeDismissed = true; }} aria-label="Dismiss notice">✕</button>
    </div>
  {:else if noticeMessage && !noticeDismissed}
    <div class="notice-banner" role="alert">
      <span class="notice-text">{noticeMessage}</span>
      <button class="notice-close" onclick={() => { noticeDismissed = true; }} aria-label="Dismiss notice">✕</button>
    </div>
  {/if}
  <BannerContainer />
  {#if isLoading}
    <div class="loading-bar" aria-label="Loading"></div>
  {/if}
  <PopupOverlay />
  {#if resetConfirm}
    <div class="global-confirm">
      <ConfirmDialog
        title="⚠ Reset Lighterbird"
        message={resetConfirm.message}
        confirmText="Yes, Delete Everything"
        variant="danger"
        onConfirm={async () => {
          const cmd = resetConfirm;
          resetConfirm = null;
          try {
            const resp = await fetch("/api/v1/command", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ tokens: cmd.tokens, flags: cmd.flags }),
            });
            const result = await resp.json();
            if (result.type === "form-required") {
              popup.show("error", "Reset Cancelled", { message: "Reset requires confirmation." });
            } else {
              const dataType = detectPersistentType("!reset");
              if (dataType) {
                popup.showPersistent(result.type, result.title, result.data, dataType);
              } else {
                popup.show(result.type, result.title, result.data);
              }
            }
          } catch (err) {
            popup.show("error", "Reset Failed", { message: err.message || String(err) });
          }
        }}
        onDismiss={() => { resetConfirm = null; }}
      />
    </div>
  {/if}
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(:root) {
    /* Greyscale chain — all pass WCAG AA 4.5:1 on #1a1a2e */
    --clr-muted: #82829a;   /* metadata, dates, hints, empty states */
    --clr-sub:   #9292aa;   /* labels, descriptions, secondary info */
    --clr-dim:   #888;       /* tab hints, tertiary text */
    --clr-kbd:   #999;       /* keyboard shortcut elements */
    --clr-accent:#7c7c9a;   /* accents, borders (non-text) */
  }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
  }
  .notice-banner {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 12px;
    background: #2a2a3e;
    border-bottom: 1px solid #4a4a6e;
    font-size: 0.82rem;
    color: #c0c0d0;
    line-height: 1.5;
  }
  .notice-text {
    flex: 1;
    white-space: pre-wrap;
  }
  .notice-close {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #888;
    font-size: 1rem;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .notice-close:hover {
    color: #e0e0e0;
    background: #3a3a4e;
  }
  .notice-warning {
    background: #3a2a1a;
    border-bottom-color: #6a4a2a;
  }
  .loading-bar {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, #7c7c9a 0%, #a4a4d0 50%, #7c7c9a 100%);
    background-size: 200% 100%;
    animation: bar-slide 1.5s ease-in-out infinite;
    z-index: 1000;
  }
  @keyframes bar-slide {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .global-confirm {
    position: fixed;
    inset: 0;
    z-index: 1000;
  }
</style>

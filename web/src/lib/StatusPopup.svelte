<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { calendar as calendarApi, llm as llmApi, email as emailApi, journal as journalApi, drafts as draftsApi } from "./api.js";
  import StatusContent from "./StatusContent.svelte";

  let { data = {} } = $props();
  // Normalize null to empty object (delete commands return 204 → null)
  let d = $derived(data || {});

  // ── Form overlay state ──────────────────────────────────────────────

  let activeForm = $state(null); // null | "llm" | "email" | "calendar" | "backup-strategy" | "contacts" | "todo" | "journal-write"
  let editingItem = $state(null); // existing item for edit, or initialData for new

  // Backup strategy testing state
  let testingStrategies = $state(new Set());
  let testResults = $state({});

  function openForm(type, item = null) {
    activeForm = type;
    editingItem = item;
  }

  function closeForm() {
    activeForm = null;
    editingItem = null;
  }

  /** Activate an LLM profile. */
  async function activateProfile(item) {
    try {
      await llmApi.loadProfile(item.name);
      await refetchCurrentTab();
    } catch (err) {
      alert(`Failed to activate: ${err.message}`);
    }
  }

  /** Remove an item with confirmation. */
  async function removeItem(type, item) {
    if (!confirm(`Remove this ${type} account/profile?`)) return;
    try {
      if (type === "email") {
        await emailApi.deleteAccount(item.uuid);
      } else if (type === "calendar") {
        await calendarApi.deleteCalendar(item.uuid);
      } else if (type === "llm") {
        await llmApi.deleteProfile(item.name);
      } else if (type === "backup-strategy") {
        await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["backup", "config", "remove", item.id], flags: {} }),
        });
      } else if (type === "journal") {
        await journalApi.delete(item.uuid);
      }
      closeForm();
      await refetchCurrentTab();
    } catch (err) {
      alert(`Failed to remove: ${err.message}`);
    }
  }

  /** Test a backup strategy's target. */
  async function testStrategy(item) {
    const sid = item.id;
    testingStrategies = new Set([...testingStrategies, sid]);
    testResults = { ...testResults, [sid]: null };
    try {
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: ["backup", "config", "test", sid], flags: {} }),
      });
      const result = await resp.json();
      if (resp.ok) {
        testResults = { ...testResults, [sid]: { success: true, message: result.data?.message || "Target is writable." } };
      } else {
        const detail = result.detail || {};
        const msg = typeof detail === "string" ? detail : detail.error || "Test failed";
        testResults = { ...testResults, [sid]: { success: false, message: msg } };
      }
    } catch (err) {
      testResults = { ...testResults, [sid]: { success: false, message: err.message || "Network error" } };
    } finally {
      const next = new Set(testingStrategies);
      next.delete(sid);
      testingStrategies = next;
    }
  }

  /** Re-fetch the data for the current tab by re-executing the command. */
  async function refetchCurrentTab() {
    const active = tabStore.active;
    if (!active) return;
    try {
      let result;
      if (d.accounts !== undefined) {
        result = await emailApi.listAccounts();
      } else if (d.calendars !== undefined) {
        result = await calendarApi.listCalendars();
      } else if (d.profiles !== undefined) {
        result = await llmApi.listProfiles();
      } else if (d.strategies !== undefined) {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["backup", "config", "list"], flags: {} }),
        });
        const cmdResult = await resp.json();
        if (resp.ok) {
          result = cmdResult.data;
          if (cmdResult.title) {
            tabStore.update(active.id, result, cmdResult.title);
            return;
          }
        }
      } else if (d.signatures !== undefined) {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["email", "signature", "list"], flags: {} }),
        });
        const cmdResult = await resp.json();
        if (resp.ok) {
          result = cmdResult.data;
        }
      } else if (d.entries !== undefined) {
        result = await journalApi.list({ limit: 50 });
      }
      if (result) {
        tabStore.update(active.id, result);
      }
    } catch { /* ignore */ }
  }

  /** Save a journal entry via the journal API. */
  async function saveJournal(data) {
    await journalApi.create(data);
    closeForm();
    await refetchCurrentTab();
  }
</script>

<StatusContent
  {data}
  {activeForm}
  {editingItem}
  {testingStrategies}
  {testResults}
  onOpenForm={openForm}
  onCloseForm={closeForm}
  onRemoveItem={removeItem}
  onActivateProfile={activateProfile}
  onTestStrategy={testStrategy}
  onRefetch={refetchCurrentTab}
  onSaveJournal={saveJournal}
  onOpenSignatureAdd={() =>
    tabStore.open("form", "Add Email Signature", {
      form: "email-signature-add",
      initialData: {},
    }, { idKey: "form-email-signature-add" })
  }
  onOpenSignatureModify={(sig) =>
    tabStore.open("form", "Modify Signature: " + (sig.name || "default"), {
      form: "email-signature-modify",
      initialData: { uuid: sig.uuid, name: sig.name || "default", signature_text: sig.signature_text || sig.signature || "" },
    }, { idKey: "form-email-signature-modify" })
  }
  onDeleteSignature={async (sig) => {
    if (!confirm(`Delete signature "${sig.name || 'default'}" for ${sig.account_email || sig.email}?`)) return;
    try {
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: ["email", "signature", "delete", sig.uuid], flags: {} }),
      });
      if (resp.ok) await refetchCurrentTab();
    } catch { /* ignore */ }
  }}
  onOpenJournalWrite={() =>
    tabStore.open("form", "Write Journal Entry", { form: "journal-write", initialData: {} }, { idKey: "journal-write" })
  }
  onOpenUserProfileAdd={() =>
    tabStore.open("form", "Add User Profile", {
      form: "user-info-add",
      initialData: {},
    }, { idKey: "form-user-info-add" })
  }
  onRecallDraft={async (draft) => {
    try {
      const full = await draftsApi.get(draft.uuid);
      const domain = full.domain || "";
      const formType = domain === "email" ? "email-send"
        : domain === "journal" ? "journal-write"
        : domain === "todo" ? "todo-add"
        : domain === "calendar-event" ? "calendar-event-add"
        : domain === "letter" ? "letter-send"
        : null;
      if (formType) {
        tabStore.open("form", "Recall: " + (full.title || ""), {
          form: formType,
          initialData: { ...full.data, _draft_uuid: full.uuid },
        }, { idKey: `form-${formType}` });
      }
    } catch { /* ignore */ }
  }}
  onDeleteDraft={async (draft) => {
    if (!confirm("Delete this draft?")) return;
    try {
      await draftsApi.delete(draft.uuid);
      const active = tabStore.active;
      if (active) {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: active.idKey ? active.idKey.split("-") : [], flags: {} }),
        });
        if (resp.ok) {
          const result = await resp.json();
          tabStore.update(active.id, result.data || {});
        }
      }
    } catch { /* ignore */ }
  }}
/>

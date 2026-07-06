/**
 * emailMessageOps.svelte.js
 *
 * Extracted message operations used by EmailListTab.
 * Keeps EmailListTab.svelte under the 500-line limit.
 */
import { tabStore } from "./tabStore.svelte.js";
import { email as emailApi } from "./api.js";

/**
 * Open a message in a new tab by UUID.
 */
export async function openMessage(uuid) {
  if (!uuid) return;
  try {
    const msg = await emailApi.getMessage(uuid);
    tabStore.open("email", msg.subject || "(no subject)", msg, {
      idKey: `email-${uuid}`,
      replaceable: false,
    });
  } catch (err) {
    tabStore.open("error", "Error", { message: err.message || "Failed to load message" });
  }
}

/**
 * Open a message in a new browser tab.
 */
export function openMessageInNewTab(e, uuid) {
  if (!uuid) return;
  e.preventDefault();
  window.open(`/api/v1/email/messages/${uuid}/view`, "_blank");
}

/**
 * Handle row click — selection mode, ctrl+click, or normal open.
 */
export function handleRowClick(e, msg, sel) {
  if (sel.selectionMode) {
    sel.handleRowClick(e, msg.uuid);
  } else if (e.ctrlKey || e.metaKey || e.button === 1) {
    openMessageInNewTab(e, msg.uuid);
  } else {
    openMessage(msg.uuid);
  }
}

/**
 * Batch-delete messages and refresh the list.
 * @param {string[]} uuids - UUIDs to delete
 * @param {Function} refreshList - callback to refresh after deletion
 */
export async function deleteSelected(uuids, refreshList) {
  if (uuids.length === 0) return;
  try {
    await emailApi.batchDelete(uuids);
    await refreshList();
  } catch (err) {
    tabStore.open("error", "Delete Failed", {
      message: err.message || "Failed to delete messages",
    });
  }
}

/**
 * Batch-move messages to a destination folder and refresh the list.
 * @param {string[]} uuids - UUIDs to move
 * @param {string} destinationFolderUuid
 * @param {Function} refreshList - callback to refresh after move
 */
export async function moveSelected(uuids, destinationFolderUuid, refreshList) {
  if (uuids.length === 0) return;
  try {
    await emailApi.batchMove(uuids, destinationFolderUuid);
    await refreshList();
  } catch (err) {
    tabStore.open("error", "Move Failed", {
      message: err.message || "Failed to move messages",
    });
  }
}

/**
 * Action banner store — shows dismissable/undoable banners with optional action callback.
 *
 * Unlike the simple bannerStore (message + type), this supports an "Undo" button
 * that invokes the provided callback.
 *
 * Usage:
 *   import { actionBanner } from "./actionBannerStore.svelte.js";
 *
 *   actionBanner.show("Message trashed", () => undoTrash());
 *   actionBanner.hide();
 */

let _state = $state({
  visible: false,
  message: "",
  actionLabel: "Undo",
  onAction: null,
  timeout: null,
});

const DEFAULT_DURATION = 5000; // 5 seconds

/**
 * Show an action banner with an optional undo button.
 *
 * @param {string} message - The message to display
 * @param {Function|null} onAction - Callback for the undo button (or null for dismiss-only)
 * @param {string} actionLabel - Label for the action button (default "Undo")
 * @param {number} duration - Auto-dismiss timeout in ms (default 5000)
 */
function show(message, onAction = null, actionLabel = "Undo", duration = DEFAULT_DURATION) {
  hide(); // clear any previous banner
  _state.visible = true;
  _state.message = message;
  _state.actionLabel = actionLabel;
  _state.onAction = onAction;

  if (duration > 0) {
    _state.timeout = setTimeout(() => {
      hide();
    }, duration);
  }
}

function hide() {
  if (_state.timeout) {
    clearTimeout(_state.timeout);
    _state.timeout = null;
  }
  _state.visible = false;
  _state.message = "";
  _state.actionLabel = "Undo";
  _state.onAction = null;
}

function triggerAction() {
  if (_state.onAction) {
    _state.onAction();
  }
  hide();
}

export const actionBanner = {
  get visible() { return _state.visible; },
  get message() { return _state.message; },
  get actionLabel() { return _state.actionLabel; },
  get onAction() { return _state.onAction; },
  show,
  hide,
  triggerAction,
};

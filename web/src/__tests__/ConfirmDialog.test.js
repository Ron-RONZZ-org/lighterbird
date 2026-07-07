/**
 * ConfirmDialog component tests — modal dialog with confirm/cancel.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import ConfirmDialog from "../lib/ConfirmDialog.svelte";

describe("ConfirmDialog", () => {
  it("renders title and message", () => {
    render(ConfirmDialog, {
      title: "Delete?",
      message: "Are you sure you want to delete this?",
    });
    expect(screen.getByText("Delete?")).toBeTruthy();
    expect(screen.getByText("Are you sure you want to delete this?")).toBeTruthy();
  });

  it("renders confirm and cancel buttons with defaults", () => {
    render(ConfirmDialog, { title: "Test" });
    expect(screen.getByText("Confirm")).toBeTruthy();
    expect(screen.getByText("Cancel")).toBeTruthy();
  });

  it("renders custom confirm text", () => {
    render(ConfirmDialog, {
      title: "Delete",
      confirmText: "Delete Anyway",
    });
    expect(screen.getByText("Delete Anyway")).toBeTruthy();
  });

  it("calls onConfirm when confirm button is clicked", async () => {
    const onConfirm = vi.fn();
    render(ConfirmDialog, { title: "Test", onConfirm });
    await fireEvent.click(screen.getByText("Confirm"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("calls onDismiss when Cancel is clicked", async () => {
    const onDismiss = vi.fn();
    render(ConfirmDialog, { title: "Test", onDismiss });
    await fireEvent.click(screen.getByText("Cancel"));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("calls onDismiss when overlay is clicked", async () => {
    const onDismiss = vi.fn();
    render(ConfirmDialog, { title: "Test", onDismiss });
    // Click the overlay (first child of body after render)
    const overlay = document.querySelector('[role="alertdialog"]');
    expect(overlay).toBeTruthy();
    if (overlay) {
      await fireEvent.click(overlay);
      expect(onDismiss).toHaveBeenCalledOnce();
    }
  });

  it("applies variant class to confirm button", () => {
    render(ConfirmDialog, {
      title: "Test",
      variant: "danger",
    });
    const confirmBtn = screen.getByText("Confirm");
    expect(confirmBtn.classList.contains("danger")).toBe(true);
  });

  it("has role alertdialog and aria-modal", () => {
    render(ConfirmDialog, { title: "Warning", message: "Something" });
    const dialog = document.querySelector('[role="alertdialog"]');
    expect(dialog).toBeTruthy();
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
    expect(dialog?.getAttribute("aria-label")).toBe("Warning");
  });
});

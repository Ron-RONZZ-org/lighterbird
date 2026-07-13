/**
 * SyncOverlay component tests — full-page blocking sync progress overlay.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import { flushSync } from "svelte";
import SyncOverlay from "../lib/SyncOverlay.svelte";

function flushEffects() {
  flushSync();
}

describe("SyncOverlay", () => {
  it("renders title and waiting state when no progress", () => {
    render(SyncOverlay, { title: "Syncing email…" });
    flushEffects();
    expect(screen.getByText("Syncing email…")).toBeTruthy();
    expect(screen.getByText("Starting sync…")).toBeTruthy();
  });

  it("renders progress bar when syncProgress provided", () => {
    render(SyncOverlay, {
      title: "Syncing…",
      syncProgress: {
        current_folder: 1,
        total_folders: 5,
        folder_name: "INBOX",
        total: 120,
        status: "running",
      },
    });
    flushEffects();
    expect(screen.getByText((content) => content.includes("INBOX"))).toBeTruthy();
  });

  it("renders cancel button when onCancel provided", () => {
    const onCancel = vi.fn();
    render(SyncOverlay, { title: "Test", onCancel });
    flushEffects();
    expect(screen.getByText("Cancel")).toBeTruthy();
  });

  it("renders error message", () => {
    render(SyncOverlay, { title: "Test", error: "Connection failed" });
    flushEffects();
    expect(screen.getByText("Connection failed")).toBeTruthy();
  });

  it("has role status and sync aria-label", () => {
    render(SyncOverlay, { title: "Syncing…" });
    flushEffects();
    const overlay = document.querySelector('[role="status"]');
    expect(overlay).toBeTruthy();
    expect(overlay?.getAttribute("aria-label")).toBe("Synchronizing");
  });
});

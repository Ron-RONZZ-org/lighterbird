/**
 * Tests for the action banner store.
 *
 * Because the store uses Svelte 5 module-level $state, we must isolate
 * each test by resetting modules.  Vitest handles this with
 * ``beforeEach(() => vi.resetModules())`` and fresh dynamic imports.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

// Module-level store — fresh import per test
let actionBanner;

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("../lib/actionBannerStore.svelte.js");
  actionBanner = mod.actionBanner;
});

describe("actionBannerStore", () => {
  it("starts hidden", () => {
    expect(actionBanner.visible).toBe(false);
  });

  it("show() makes it visible", () => {
    actionBanner.show("Test message");
    expect(actionBanner.visible).toBe(true);
    expect(actionBanner.message).toBe("Test message");
    expect(actionBanner.actionLabel).toBe("Undo");
  });

  it("show() with custom action label", () => {
    actionBanner.show("Test message", null, "Custom", 3000);
    expect(actionBanner.visible).toBe(true);
    expect(actionBanner.actionLabel).toBe("Custom");
  });

  it("hide() hides it", () => {
    actionBanner.show("Test");
    expect(actionBanner.visible).toBe(true);
    actionBanner.hide();
    expect(actionBanner.visible).toBe(false);
    expect(actionBanner.message).toBe("");
  });

  it("triggerAction() invokes callback and hides", () => {
    const callback = vi.fn();
    actionBanner.show("Test", callback);
    expect(actionBanner.visible).toBe(true);

    actionBanner.triggerAction();
    expect(callback).toHaveBeenCalledOnce();
    expect(actionBanner.visible).toBe(false);
  });

  it("triggerAction() without callback still hides", () => {
    actionBanner.show("Test", null);
    actionBanner.triggerAction();
    expect(actionBanner.visible).toBe(false);
  });

  it("auto-dismisses after duration", async () => {
    vi.useFakeTimers();
    actionBanner.show("Test", null, "Undo", 100);
    expect(actionBanner.visible).toBe(true);

    vi.advanceTimersByTime(150);
    expect(actionBanner.visible).toBe(false);
    vi.useRealTimers();
  });

  it("show() during visible banner replaces it", () => {
    actionBanner.show("First");
    actionBanner.show("Second");
    expect(actionBanner.message).toBe("Second");
  });

  it("show() with no duration never auto-dismisses", () => {
    actionBanner.show("Test", null, "Undo", 0);
    expect(actionBanner.visible).toBe(true);
    // No timer set — state persists until hide() is called
    actionBanner.hide();
    expect(actionBanner.visible).toBe(false);
  });
});

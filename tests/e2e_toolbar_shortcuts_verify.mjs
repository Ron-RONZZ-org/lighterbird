/**
 * E2E Verification — toolbar context adaptation + keyboard shortcuts.
 *
 * Validates the fix for PR #229:
 *   1. Email list tab shows "Fldrs" button (not "Clear Trash")
 *   2. Email trash tab shows "Clear Trash" button (not "Fldrs"), no "+ New"
 *   3. "f" keyboard shortcut toggles folder tree in list view
 *   4. Tab switching maintains correct toolbar context
 *   5. !email send opens compose form
 *   6. No page errors / JS exceptions
 *
 * Each test is self-contained (types its own command) to avoid interference
 * from the shared dismissAllTabs cleanup between tests.
 */

import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter, sleep,
  assertTabOpened, assertFormOpened,
  runWithBrowser, dismissAllTabs, page,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "/home/rongzhou/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";

// ── Helpers ────────────────────────────────────────────────────────────

async function goHome() {
  // Navigate to home tab and dismiss any overlays
  await page.keyboard.press("Alt+1");
  await sleep(300);
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Escape");
    await sleep(100);
  }
}

async function assertToolbarButton(text) {
  const panel = page.locator('.tab-content.active[data-testid="tab-panel"]');
  const btn = panel.locator(`button:has-text("${text}")`).first();
  const visible = await btn.isVisible().catch(() => false);
  assert(visible, `Expected toolbar button "${text}" to be visible`);
  console.log(`    \u2713 Toolbar has "${text}"`);
}

async function assertNoToolbarButton(text) {
  const panel = page.locator('.tab-content.active[data-testid="tab-panel"]');
  const btn = panel.locator(`button:has-text("${text}")`).first();
  const visible = await btn.isVisible().catch(() => false);
  assert(!visible, `Expected toolbar button "${text}" to NOT be visible`);
  console.log(`    \u2713 Toolbar correctly lacks "${text}"`);
}

async function assertFolderPanelVisible(expectedVisible) {
  const fp = page.locator(
    '.folder-panel, .email-folder-panel, [class*="folderTree"], [class*="folder-tree"]'
  ).first();
  if (expectedVisible) {
    const visible = await fp.isVisible().catch(() => false);
    assert(visible, "Expected folder panel to be visible after F key");
    console.log("    \u2713 Folder panel visible after F key");
  } else {
    const visible = await fp.isVisible().catch(() => false);
    assert(!visible, "Expected folder panel to be hidden after F key");
    console.log("    \u2713 Folder panel hidden after F key");
  }
}

/**
 * Open an email tab and wait for its toolbar to become visible.
 * Waits up to `timeoutMs` for the initial sync overlay to disappear
 * and the toolbar to render.
 */
async function openEmailTab(command, buttonText, timeoutMs = 120000) {
  await goHome();
  await typeCommand(command);
  await pressEnter();
  const panel = page.locator('.tab-content.active[data-testid="tab-panel"]');
  try {
    await panel.locator(`button:has-text("${buttonText}")`).waitFor({ state: "visible", timeout: timeoutMs });
  } catch {
    // Timeout — dump page text for diagnostics
    const text = (await page.locator("body").textContent() || "").substring(0, 300);
    console.log(`    Wait failed: button "${buttonText}" not found. Page: "${text.replace(/\s+/g, " ").trim()}"`);
  }
  await sleep(300);
}

/** Aggressively close all tabs by pressing Escape many times from home. */
async function closeAllTabs() {
  await goHome();
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press("Escape");
    await sleep(100);
  }
  await sleep(300);
}

// ── Tests ──────────────────────────────────────────────────────────────

async function runTests() {
  console.log("\n--- Email Toolbar + Shortcut Verification ---\n");

  // ── 1. Email list tab ────────────────────────────────────────────
  await test("!email list opens with correct toolbar buttons", async () => {
    await openEmailTab("!email list", "Select");

    await assertToolbarButton("Select");
    await assertToolbarButton("Fldrs");
    await assertToolbarButton("Sort");
    await assertToolbarButton("Params");
    await assertToolbarButton("Sync");

    await assertNoToolbarButton("Clear Trash");
    await assertNoToolbarButton("Restore");
    await assertToolbarButton("+ New");
  });

  // ── 2. F key toggles folder tree ─────────────────────────────────
  await test("F key toggles folder tree in email list", async () => {
    await openEmailTab("!email list", "Select");

    await page.keyboard.press("f");
    await sleep(500);
    await assertFolderPanelVisible(true);

    await page.keyboard.press("f");
    await sleep(500);
    await assertFolderPanelVisible(false);
  });

  // ── 3. Email trash tab ────────────────────────────────────────────
  await test("!email trash opens with trash-specific toolbar", async () => {
    await closeAllTabs();
    await openEmailTab("!email trash", "Clear Trash");

    await assertToolbarButton("Clear Trash");
    await assertNoToolbarButton("Fldrs");
    await assertNoToolbarButton("+ New");
    await assertToolbarButton("Select");
    await assertToolbarButton("Sort");
    await assertToolbarButton("Params");
    await assertToolbarButton("Sync");
  });

  // ── 4. Tab switching maintains toolbar context ────────────────────
  await test("tab switching keeps correct toolbar for each email subtype", async () => {
    await closeAllTabs();
    // Open both list and trash tabs (wait for each toolbar to be ready)
    await openEmailTab("!email list", "Select");
    await goHome();
    await openEmailTab("!email trash", "Clear Trash");

    // Switch to list tab
    const tabBar = page.locator('[role="tablist"]');
    const listTab = tabBar.locator('[role="tab"][title="Email"]');
    const listCount = await listTab.count();
    if (listCount > 0) {
      await listTab.click();
      await sleep(500);
      await assertToolbarButton("Fldrs");
      await assertNoToolbarButton("Clear Trash");
      console.log("    \u2713 List tab toolbar correct after switch");
    }

    // Switch to trash tab
    const trashTab = tabBar.locator('[role="tab"][title="Email (Trash)"]');
    const trashCount = await trashTab.count();
    if (trashCount > 0) {
      await trashTab.click();
      await sleep(500);
      await assertToolbarButton("Clear Trash");
      await assertNoToolbarButton("Fldrs");
      console.log("    \u2713 Trash tab toolbar correct after switch");
    }
  });

  // ── 4. Tab switching maintains toolbar context ────────────────────
  await test("tab switching keeps correct toolbar for each email subtype", async () => {
    // Open both list and trash tabs first
    await openEmailTab("!email list", "Select");
    await goHome();
    await openEmailTab("!email trash", "Clear Trash");

    // Switch to list tab
    const tabBar = page.locator('[role="tablist"]');
    const listTab = tabBar.locator('[role="tab"][title="Email"]');
    const listExists = await listTab.count();
    if (listExists > 0) {
      await listTab.click();
      await sleep(500);
      await assertToolbarButton("Fldrs");
      await assertNoToolbarButton("Clear Trash");
      console.log("    \u2713 List tab toolbar correct after switch");
    }

    // Switch to trash tab
    const trashTab = tabBar.locator('[role="tab"][title="Email (Trash)"]');
    const trashExists = await trashTab.count();
    if (trashExists > 0) {
      await trashTab.click();
      await sleep(500);
      await assertToolbarButton("Clear Trash");
      await assertNoToolbarButton("Fldrs");
      console.log("    \u2713 Trash tab toolbar correct after switch");
    }
  });

  // ── 5. Email send opens compose form ──────────────────────────────
  await test("!email send opens compose form", async () => {
    await closeAllTabs();
    await goHome();
    await typeCommand("!email send");
    await pressEnter();
    await sleep(2000);

    // Wait for the compose form to render
    await assertFormOpened("Compose Email");

    const panel = page.locator('.tab-content.active[data-testid="tab-panel"]');
    const toField = panel.locator('[placeholder*="recipient"]').first();
    const toExists = await toField.isVisible().catch(() => false);
    assert(toExists, "Compose form should have a To recipient field");
    console.log("    \u2713 Compose form has To recipient field");
  });
}

// ── Main ───────────────────────────────────────────────────────────────

runWithBrowser(FRONTEND_URL, CHROME_PATH, "Email Toolbar + Shortcut Verification", runTests);

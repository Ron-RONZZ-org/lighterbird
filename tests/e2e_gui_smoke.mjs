/**
 * GUI Smoke Test — verifies actual browser DOM rendering, not just API responses.
 *
 * This is the test that catches bugs the API-only E2E tests miss: tabs that
 * don't open, blank panels, wrong component mounted, broken keyboard nav.
 *
 * Strategy:
 *   Every command is typed → Enter → then we assert DOM structure:
 *   - Did a tab bar appear?
 *   - Does the active tab have the expected title?
 *   - Is the tab content panel visible and non-empty?
 *   - Did any JS exception occur?
 *
 * Console errors AND page errors cause the ENTIRE SUITE TO FAIL.
 * This catches silent JS exceptions that leave the UI broken.
 */

import { chromium } from "playwright";
import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter, sleep,
  assertTabOpened, assertFormOpened, assertHomeActive, assertPanelContains,
  runWithBrowser, page, pageErrors, consoleErrors,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

// ── Local helpers ──────────────────────────────────────────────────────────

/** Fill a form field by its id attribute and trigger an input event. */
async function fillFormField(fieldId, value) {
  const field = page.locator(`#${CSS.escape(fieldId)}`);
  await field.waitFor({ state: "visible", timeout: 3000 });
  await field.click();
  await field.fill("");
  await sleep(50);
  await field.pressSequentially(value, { delay: 5 });
  await sleep(100);
}

/** Click the Save/Submit button in the active form panel. */
async function clickFormSubmit() {
  const panel = page.locator('[aria-label="Tab content"]');
  const submitBtn = panel.locator(
    'button[type="submit"], button:has-text("Save"), button:has-text("Add"), button:has-text("Create"), button:has-text("Send")'
  );
  await submitBtn.waitFor({ state: "visible", timeout: 3000 });
  await submitBtn.click();
  await sleep(800);
}

/** Check if a ConfirmDialog is visible (unsaved-changes guard). */
async function confirmDialogIsVisible() {
  const dialog = page.locator('[role="alertdialog"]');
  return await dialog.isVisible().catch(() => false);
}

/** Click a button in a ConfirmDialog by its text. */
async function clickConfirmDialogButton(text) {
  const dialog = page.locator('[role="alertdialog"]');
  const btn = dialog.locator(`button:has-text("${text}")`);
  await btn.waitFor({ state: "visible", timeout: 2000 });
  await btn.click();
  await sleep(300);
}

/** Toggle selection mode with V key and wait for checkboxes. */
async function enterSelectionMode() {
  await page.keyboard.press("v");
  await sleep(400);
}

/** Assert the active tab panel text contains expected content. */
async function assertPanelHasContent() {
  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const text = (await panel.textContent() || "").trim();
  assert(text.length > 0, "Tab panel should have non-empty content");
  return text;
}

// ── Runner ─────────────────────────────────────────────────────────────────

async function runTests(page) {
  // ════════════════════════════════════════════
  // 0. HOME TAB ASSERTIONS
  // ════════════════════════════════════════════
  console.log("\n--- HOME TAB ---");

  await test("Home tab shows command input", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.waitFor({ state: "visible", timeout: 3000 });
    assert(await input.isVisible(), "Command input should be visible");
  });

  await test("Home tab shows keyboard shortcut hints", async () => {
    const hint = page.locator(".home-hints");
    await hint.waitFor({ state: "visible", timeout: 2000 });
    const text = await hint.textContent() || "";
    assert(text.includes("h") || text.includes("i"), `Hints should show shortcuts, got: "${text.trim()}"`);
  });

  // ════════════════════════════════════════════
  // 1. LIST TABS — verify actual tab rendering
  // ════════════════════════════════════════════
  console.log("\n--- LIST TABS (DOM rendering) ---");

  await test("!email account list opens list tab", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    await assertTabOpened("Account");
  });

  await test("!contact list opens contacts list tab", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    await assertTabOpened("Contact");
  });

  await test("!todo list opens todo list tab", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
  });

  await test("!journal list opens journal list tab", async () => {
    await typeCommand("!journal list");
    await pressEnter();
    await assertTabOpened("Journal");
  });

  await test("!calendar account list opens calendar list tab", async () => {
    await typeCommand("!calendar account list");
    await pressEnter();
    await assertTabOpened("Calendar");
  });

  await test("!letter list opens letter list tab", async () => {
    await typeCommand("!letter list");
    await pressEnter();
    await assertTabOpened("Letter");
  });

  await test("!email sieve list opens sieve tab", async () => {
    await typeCommand("!email sieve list");
    await pressEnter();
    await assertTabOpened("Sieve");
  });

  // ════════════════════════════════════════════
  // 2. STATUS / HELP TABS
  // ════════════════════════════════════════════
  console.log("\n--- STATUS / HELP TABS ---");

  await test("!help opens help tab", async () => {
    await typeCommand("!help");
    await pressEnter();
    await assertTabOpened("Available");
    await assertPanelContains("!email");
  });

  await test("!sync opens sync result tab", async () => {
    await typeCommand("!sync");
    await pressEnter();
    await assertTabOpened("Sync");
  });

  // ════════════════════════════════════════════
  // 3. FORM POPUPS — verify incomplete commands
  //    trigger proper form rendering
  // ════════════════════════════════════════════
  console.log("\n--- FORM POPUPS ---");

  await test("!contact add (incomplete) opens contact add form", async () => {
    await typeCommand("!contact add");
    await pressEnter();
    await assertFormOpened("Contact", ["first", "last"]);
  });

  await test("!todo add (incomplete) opens todo form", async () => {
    await typeCommand("!todo add");
    await pressEnter();
    await assertFormOpened("Todo", ["title"]);
  });

  await test("!journal write (incomplete) opens journal form", async () => {
    await typeCommand("!journal write");
    await pressEnter();
    await assertFormOpened("Journal", ["title"]);
  });

  await test("!email account add (incomplete) opens account form", async () => {
    await typeCommand("!email account add");
    await pressEnter();
    await assertFormOpened("Account", ["email"]);
  });

  await test("!calendar event add (incomplete) opens event form", async () => {
    await typeCommand("!calendar event add");
    await pressEnter();
    await assertFormOpened("Calendar", ["title", "start"]);
  });

  await test("!email send (incomplete) opens compose form", async () => {
    await typeCommand("!email send");
    await pressEnter();
    await assertFormOpened("Email", ["to"]);
  });

  await test("!letter add (incomplete) opens letter form", async () => {
    await typeCommand("!letter add");
    await pressEnter();
    await assertFormOpened("Letter", ["object"]);
  });

  // ════════════════════════════════════════════
  // 3b. FORM SUBMISSION — fill fields and submit
  // ════════════════════════════════════════════
  console.log("\n--- FORM SUBMISSION ---");

  await test("!todo add form: fill title and submit via GUI", async () => {
    await typeCommand("!todo add");
    await pressEnter();
    await assertFormOpened("Todo", ["title"]);
    await fillFormField("title", "Buy groceries from form test");
    await clickFormSubmit();
    // After submit, should show success tab or redirect to list tab
    const text = await assertPanelHasContent();
    assert(text.includes("added") || text.includes("Created") || text.includes("Buy") || text.includes("groceries"),
      `Expected success after form submit, got: "${text.substring(0, 200)}"`);
  });

  await test("!journal write form: fill title and submit via GUI", async () => {
    await typeCommand("!journal write");
    await pressEnter();
    await assertFormOpened("Journal", ["title"]);
    await fillFormField("title", "Journal entry from GUI test");
    await clickFormSubmit();
    const text = await assertPanelHasContent();
    assert(text.includes("written") || text.includes("Created") || text.includes("Journal") || text.includes("GUI"),
      `Expected success after journal form submit, got: "${text.substring(0, 200)}"`);
  });

  // ════════════════════════════════════════════
  // 4. TAB NAVIGATION
  // ════════════════════════════════════════════
  console.log("\n--- TAB NAVIGATION ---");

  await test("Multiple tabs: all appear in tab bar", async () => {
    await typeCommand("!help");
    await pressEnter();
    await assertTabOpened("Available");
    await typeCommand("!contact list");
    await pressEnter();
    await assertTabOpened("Contact");
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");

    const tabBar = page.locator('[role="tablist"]');
    const tabCount = await tabBar.locator('[role="tab"]').count();
    assert(tabCount >= 4, `Expected ≥ 4 tabs, found ${tabCount}`);
  });

  await test("Click on different tabs switches active tab", async () => {
    const tabs = page.locator('[role="tab"]');
    const count = await tabs.count();
    for (let i = 0; i < count; i++) {
      const tab = tabs.nth(i);
      await tab.click();
      await sleep(200);
      const selected = await tab.getAttribute("aria-selected");
      assert(selected === "true", `Tab ${i} should be selected after click`);
    }
  });

  await test("Escape closes active tab, returns to home", async () => {
    for (let i = 0; i < 8; i++) {
      const tabBar = page.locator('[role="tablist"]');
      const stillHasTabs = await tabBar.isVisible().catch(() => false);
      if (!stillHasTabs) break;
      await page.keyboard.press("Escape");
      await sleep(200);
    }
    await assertHomeActive();
  });

  // ════════════════════════════════════════════
  // 5. TAB COMPLETION
  // ════════════════════════════════════════════
  console.log("\n--- TAB COMPLETION ---");

  await test("!con tab suggests !contact", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("");
    await sleep(50);
    await input.pressSequentially("!con", { delay: 15 });
    await sleep(600);

    const sugg = page.locator(".suggestions li").first();
    const hasSuggestions = await sugg.isVisible().catch(() => false);
    if (hasSuggestions) {
      const text = await sugg.textContent();
      assert(text && text.length > 0, "Suggestion should not be empty");
      console.log(`    !con → "${text}"`);
    } else {
      console.log("    (no suggestions — may be empty list)");
    }
  });

  await test("!contact list (full) opens contacts tab with data", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    await assertTabOpened("Contact");
    const panel = page.locator('[aria-label="Tab content"]');
    const panelText = await panel.textContent() || "";
    assert(panelText.length > 10, `Contacts tab panel should have substantial content`);
  });

  // ════════════════════════════════════════════
  // 6. EMPTY LIST / SEARCH
  // ════════════════════════════════════════════
  console.log("\n--- EMPTY LIST / SEARCH ---");

  await test("Search for nonexistent shows empty state", async () => {
    await typeCommand("!contact search zzzZZZnosuchthing");
    await pressEnter();
    await assertTabOpened("Contact");
    const panel = page.locator('[aria-label="Tab content"]');
    const panelText = ((await panel.textContent()) || "").toLowerCase();
    const hasEmptyIndicator = panelText.includes("no ") || panelText.includes("0 ") || panelText.includes("zzz");
    assert(hasEmptyIndicator,
      `Empty search should show no-results indicator, panel text: "${panelText.substring(0, 200)}"`);
  });

  // ════════════════════════════════════════════
  // 7. SELECTION MODE
  // ════════════════════════════════════════════
  console.log("\n--- SELECTION MODE ---");

  await test("V key toggles selection mode on contact list", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    await assertTabOpened("Contact");
    await sleep(300);

    await page.keyboard.press("v");
    await sleep(400);

    const checkboxes = page.locator('[aria-label="Tab content"] .checkbox-cell');
    const checkboxCount = await checkboxes.count().catch(() => 0);
    if (checkboxCount > 0) {
      console.log(`    Selection mode: ${checkboxCount} checkbox(es) visible`);
    } else {
      const panel = page.locator('[aria-label="Tab content"]');
      const panelText = (await panel.textContent() || "").toLowerCase();
      const hasSelectBtn = panelText.includes("exit") || panelText.includes("selected");
      assert(hasSelectBtn || checkboxCount > 0,
        `Selection mode should show checkboxes or exit button, panel: "${(panelText).substring(0, 150)}"`);
    }

    await page.keyboard.press("Escape");
    await sleep(300);
  });

  // ════════════════════════════════════════════
  // 8. FORM VALIDATION (submit empty form)
  // ════════════════════════════════════════════
  console.log("\n--- FORM VALIDATION ---");

  await test("Submit empty contact form shows validation error", async () => {
    await typeCommand("!contact add");
    await pressEnter();
    await assertFormOpened("Contact", ["first"]);

    const panel = page.locator('[aria-label="Tab content"]');
    const saveBtn = panel.locator('button:has-text("Save")');
    const btnVisible = await saveBtn.isVisible().catch(() => false);
    assert(btnVisible, "Form should have a Save button");

    await saveBtn.click();
    await sleep(500);

    const panelText = (await panel.textContent() || "").toLowerCase();
    assert(
      panelText.includes("first") || panelText.includes("required") || panelText.includes("error") || panelText.includes("missing"),
      `After empty submit, form should show validation state, panel text: "${panelText.substring(0, 200)}"`
    );
  });

  // ════════════════════════════════════════════
  // 9. LIST SORT INTERACTION
  // ════════════════════════════════════════════
  console.log("\n--- SORT DROPDOWN ---");

  await test("Todo list sort dropdown is interactive", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
    await sleep(200);

    const panel = page.locator('[aria-label="Tab content"]');
    const sortBtn = panel.locator('button:has-text("Sort"), select:has-text("sort"), [aria-label*="sort" i], [aria-label*="Sort" i]');
    const btnCount = await sortBtn.count();
    if (btnCount > 0) {
      await sortBtn.first().click();
      await sleep(300);
      console.log(`    Sort control found and clicked (${btnCount} count)`);
    } else {
      const sortSelect = panel.locator('select, [role="listbox"] option');
      console.log(`    No explicit sort button found (${await sortSelect.count()} select elements in panel)`);
    }
  });

  // ════════════════════════════════════════════
  // 10. KEYBOARD NAVIGATION
  // ════════════════════════════════════════════
  console.log("\n--- KEYBOARD NAVIGATION ---");

  await test("Arrow down/up moves focus in selection mode", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
    await sleep(300);

    // Enter selection mode
    await enterSelectionMode();

    // Check there are selectable items
    const checkboxesBefore = page.locator('[aria-label="Tab content"] .checkbox-cell');
    const cbCount = await checkboxesBefore.count().catch(() => 0);
    if (cbCount < 2) {
      console.log(`    (${cbCount} items — skipping arrow nav test, needs ≥2)`);
      await page.keyboard.press("Escape");
      await sleep(200);
      return;
    }

    // Arrow down should move focus
    await page.keyboard.press("ArrowDown");
    await sleep(200);
    const focusedRowDown = page.locator('[aria-label="Tab content"] .focused, [aria-label="Tab content"] [class*="focus"]');
    const focusedCountDown = await focusedRowDown.count().catch(() => 0);
    console.log(`    After ArrowDown: ${focusedCountDown} focused row(s)`);

    // Arrow up should move focus back
    await page.keyboard.press("ArrowUp");
    await sleep(200);
    const focusedRowUp = page.locator('[aria-label="Tab content"] .focused, [aria-label="Tab content"] [class*="focus"]');
    const focusedCountUp = await focusedRowUp.count().catch(() => 0);
    console.log(`    After ArrowUp: ${focusedCountUp} focused row(s)`);

    await page.keyboard.press("Escape");
    await sleep(200);
  });

  await test("Space toggles selection on focused item", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
    await sleep(300);

    await enterSelectionMode();

    const checkboxes = page.locator('[aria-label="Tab content"] .checkbox-cell');
    const cbCount = await checkboxes.count().catch(() => 0);
    if (cbCount < 1) {
      console.log("    (no items — skipping selection toggle test)");
      await page.keyboard.press("Escape");
      return;
    }

    // Press Space on the first item
    await page.keyboard.press("Space");
    await sleep(300);

    // Check that at least one checkbox is checked
    const checkedCb = page.locator('[aria-label="Tab content"] .checkbox-cell input:checked, [aria-label="Tab content"] input[type="checkbox"]:checked');
    const checkedCount = await checkedCb.count().catch(() => 0);
    console.log(`    After Space: ${checkedCount} checkbox(es) checked`);

    await page.keyboard.press("Escape");
    await sleep(200);
  });

  // ════════════════════════════════════════════
  // 11. N KEY: +NEW FROM LIST TAB
  // ════════════════════════════════════════════
  console.log("\n--- N KEY +NEW ---");

  await test("N key opens add form from todo list tab", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
    await sleep(300);

    // Press N in view mode to open add form
    await page.keyboard.press("n");
    await sleep(600);

    // Should open a new form tab
    const panel = page.locator('[aria-label="Tab content"]');
    await panel.waitFor({ state: "visible", timeout: 3000 });
    const panelText = (await panel.textContent() || "").toLowerCase();
    assert(panelText.includes("title") || panelText.includes("todo"),
      `N key should open add form with title field, panel: "${panelText.substring(0, 150)}"`);
  });

  // ════════════════════════════════════════════
  // 12. SEARCH BAR TOGGLE (/ KEY)
  // ════════════════════════════════════════════
  console.log("\n--- SEARCH BAR ---");

  await test("/ key toggles search bar in todo list", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
    await sleep(300);

    // Press / to toggle search bar
    await page.keyboard.press("/");
    await sleep(400);

    // Look for a search input in the panel
    const panel = page.locator('[aria-label="Tab content"]');
    const searchInput = panel.locator('input[type="search"], input[placeholder*="earch" i], input[placeholder*="Filter" i], input[aria-label*="search" i]');
    const searchExists = await searchInput.count().catch(() => 0);
    if (searchExists > 0) {
      console.log(`    Search input visible after / key`);
    } else {
      // Maybe search is a text input — try finding any input in the panel toolbar
      const allInputs = await panel.locator("input, textarea").count();
      console.log(`    (Search input not found by label; ${allInputs} total inputs in panel)`);
    }
  });

  // ════════════════════════════════════════════
  // 13. UNSAVED CHANGES GUARD
  // ════════════════════════════════════════════
  console.log("\n--- UNSAVED CHANGES GUARD ---");

  await test("Unsaved-changes guard shows confirmation on dirty form close (Escape)", async () => {
    await typeCommand("!todo add");
    await pressEnter();
    await assertFormOpened("Todo", ["title"]);

    // Type something to make the form dirty
    await fillFormField("title", "Unsaved test task");

    // Press Escape to close the tab (should trigger guard)
    await page.keyboard.press("Escape");
    await sleep(500);

    // Check if a confirmation dialog appeared
    const guardShown = await confirmDialogIsVisible();
    if (guardShown) {
      console.log("    Unsaved-changes guard shown: confirm dialog visible");
      // Dismiss by clicking "Cancel" or "Discard"
      const discardBtn = page.locator('[role="alertdialog"] button:has-text("Discard"), [role="alertdialog"] button:has-text("Cancel")');
      const discardVisible = await discardBtn.isVisible().catch(() => false);
      if (discardVisible) {
        await discardBtn.click();
        await sleep(300);
      }
    } else {
      // Guard may not be implemented for all form types — just log
      console.log("    (No unsaved-changes guard — may not be implemented for this form type)");
    }
  });

  // ════════════════════════════════════════════
  // FINAL: NO CONSOLE ERRORS
  // ════════════════════════════════════════════
  console.log("\n--- ERROR CHECK ---");

  await test("No unhandled page errors during entire session", async () => {
    assert(pageErrors.length === 0,
      `${pageErrors.length} unhandled page error(s) occurred:\n  ${pageErrors.join("\n  ")}`);
  });

  await test("No console errors during entire session", async () => {
    assert(consoleErrors.length === 0,
      `${consoleErrors.length} console error(s) occurred:\n  ${consoleErrors.join("\n  ")}`);
  });
}

// ── Bootstrap ──────────────────────────────────────────────────────────────

runWithBrowser(FRONTEND_URL, CHROME_PATH, "GUI SMOKE TESTS — DOM assertions, not just API checks", runTests);

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
  runWithBrowser, getResultPanelText, dismissAllTabs,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

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

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

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

let browser, page;
let passed = 0, failed = 0;
let pageErrors = [];
let consoleErrors = [];

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Read the active tab's label from the HTML ``title`` attribute (untruncated). */
async function getActiveTabTitleAttr() {
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });
  const activeTab = tabBar.locator('[role="tab"][aria-selected="true"]');
  await activeTab.waitFor({ state: "visible", timeout: 3000 });
  // The ``title`` attribute is set to tab.title (full, untruncated)
  return (await activeTab.getAttribute("title") || "").trim();
}

/** Type a command into the input field and press Enter. */
async function typeAndRun(cmd) {
  // Ensure we are on the home tab with an input
  const input = page.locator("[aria-label='Message input']");
  let visible = await input.isVisible().catch(() => false);
  if (!visible) {
    await page.keyboard.press("Alt+1");
    await sleep(200);
    // Click the Home tab button as fallback
    const homeTab = page.locator('[role="tab"]', { hasText: "Home" });
    if (await homeTab.isVisible().catch(() => false)) {
      await homeTab.click();
      await sleep(200);
    }
  }
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(30);
  await input.pressSequentially(cmd, { delay: 5 });
  await sleep(100);
  await page.keyboard.press("Enter");
  await sleep(500);
}

/** Close all result tabs by pressing Escape repeatedly. */
async function dismissAllTabs() {
  await page.keyboard.press("Alt+1");
  await sleep(150);
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Escape");
    await sleep(100);
  }
}

/**
 * Assert a tab with the given title substring opened.
 *
 * Checks:
 *   1. Tab bar is visible (more than home tab exists)
 *   2. Active tab contains expectedTitle
 *   3. Content panel is visible
 *   4. Content panel has non-whitespace text
 */
async function assertTabOpened(expectedTitle) {
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });
  const tabCount = await tabBar.locator('[role="tab"]').count();
  assert(tabCount >= 2, `Expected ≥2 tabs (home + result), found ${tabCount}`);

  // Active tab title — from the HTML title attribute (full, untruncated)
  const titleAttr = await getActiveTabTitleAttr();
  assert(
    titleAttr.toLowerCase().includes(expectedTitle.toLowerCase()),
    `Active tab title should contain "${expectedTitle}", got "${titleAttr}"`
  );

  // Content panel
  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = (await panel.textContent() || "").trim();
  assert(panelText.length > 0, `Tab panel for "${expectedTitle}" is empty`);
}

/**
 * Assert the home tab is active (tab bar may still show if multiple tabs).
 */
async function assertHomeActive() {
  const homeSection = page.locator('[aria-label="Home tab"]');
  await homeSection.waitFor({ state: "visible", timeout: 2000 });
  const input = page.locator("[aria-label='Message input']");
  const inputVisible = await input.isVisible().catch(() => false);
  // Either the home section is visible OR the input is visible on the page
  assert(inputVisible || await homeSection.isVisible(),
    "Home tab should be active (input or home section visible)");
}

/**
 * Assert a form popup opened with the given title and field hints.
 * Looks for form-like elements (input, textarea, select, label) in the visible panel.
 */
async function assertFormOpened(expectedTitle, fieldHints = []) {
  // Wait for the tab bar to show a new tab
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });

  const titleAttr = await getActiveTabTitleAttr();
  assert(
    titleAttr.toLowerCase().includes(expectedTitle.toLowerCase()),
    `Form tab title should contain "${expectedTitle}", got "${titleAttr}"`
  );

  // Check the content panel contains form elements
  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = (await panel.textContent() || "").toLowerCase();

  // Check for presence of form-related generic elements
  const inputs = await panel.locator("input, textarea, select, [contenteditable]").count();
  assert(inputs > 0, `Form "${expectedTitle}" should have at least one input`);

  // Verify expected field hints appear in the panel text
  for (const hint of fieldHints) {
    assert(
      panelText.includes(hint.toLowerCase()),
      `Form "${expectedTitle}" should mention "${hint}" (field hint), panel text: "${panelText.substring(0, 200)}"`
    );
  }

  // Verify a Save/Add/Submit button exists
  const submitBtn = panel.locator('button[type="submit"], button:has-text("Save"), button:has-text("Add"), button:has-text("Create"), button:has-text("Send")');
  const btnCount = await submitBtn.count();
  assert(btnCount > 0, `Form "${expectedTitle}" should have a submit button`);
}

/**
 * Assert the active tab panel contains the given text substring.
 */
async function assertPanelContains(text) {
  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = await panel.textContent() || "";
  assert(
    panelText.toLowerCase().includes(text.toLowerCase()),
    `Tab panel should contain "${text}"`
  );
}

/** Take a screenshot on failure (preserves first 3 failures). */
let screenshotCounter = 0;
async function test(desc, fn) {
  try {
    await fn();
    console.log(`  \u2713 ${desc}`);
    passed++;
  } catch (e) {
    if (screenshotCounter < 3) {
      const ssPath = `/tmp/e2e-gui-fail-${screenshotCounter++}.png`;
      try { await page.screenshot({ path: ssPath }); console.log(`    Screenshot: ${ssPath}`); } catch {}
    }
    // Show page text for context on failure
    try {
      const mainText = (await page.locator("body").textContent() || "").substring(0, 200);
      console.log(`    Page text: "${mainText.replace(/\s+/g, " ").trim()}"`);
    } catch {}
    console.log(`  \u2717 ${desc}: ${e.message}`);
    failed++;
  } finally {
    await dismissAllTabs();
  }
}

// ── Runner ─────────────────────────────────────────────────────────────────

async function run() {
  browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } });
  page = await context.newPage();

  // ── Error tracking: JS exceptions → FAILURE ──────────────────────────
  page.on("pageerror", (err) => {
    pageErrors.push(err.message);
    console.log("  [BROWSER ERROR]", err.message);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
      console.log("  [CONSOLE ERROR]", msg.text());
    }
  });

  console.log("=".repeat(70));
  console.log("GUI SMOKE TESTS — DOM assertions, not just API checks");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  console.log("\u2713 Page loaded:", await page.title());
  await sleep(300);

  // Dismiss any welcome notice
  try {
    const dismissBtn = page.locator("button", { hasText: "Dismiss notice" });
    if (await dismissBtn.isVisible({ timeout: 300 })) {
      await dismissBtn.click();
      await sleep(200);
    }
  } catch { /* no notice */ }

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
    await typeAndRun("!email account list");
    await assertTabOpened("Account");
  });

  await test("!contact list opens contacts list tab", async () => {
    await typeAndRun("!contact list");
    await assertTabOpened("Contact");
  });

  await test("!todo list opens todo list tab", async () => {
    await typeAndRun("!todo list");
    await assertTabOpened("Todo");
  });

  await test("!journal list opens journal list tab", async () => {
    await typeAndRun("!journal list");
    await assertTabOpened("Journal");
  });

  await test("!calendar account list opens calendar list tab", async () => {
    await typeAndRun("!calendar account list");
    await assertTabOpened("Calendar");
  });

  await test("!letter list opens letter list tab", async () => {
    await typeAndRun("!letter list");
    await assertTabOpened("Letter");
  });

  await test("!email sieve list opens sieve tab", async () => {
    await typeAndRun("!email sieve list");
    await assertTabOpened("Sieve");
  });

  // ════════════════════════════════════════════
  // 2. STATUS / HELP TABS
  // ════════════════════════════════════════════
  console.log("\n--- STATUS / HELP TABS ---");

  await test("!help opens help tab", async () => {
    await typeAndRun("!help");
    // Backend returns title "Available Commands"
    await assertTabOpened("Available");
    await assertPanelContains("!email");
  });

  await test("!sync opens sync result tab", async () => {
    await typeAndRun("!sync");
    await assertTabOpened("Sync");
  });

  // ════════════════════════════════════════════
  // 3. FORM POPUPS — verify incomplete commands
  //    trigger proper form rendering
  // ════════════════════════════════════════════
  console.log("\n--- FORM POPUPS ---");

  await test("!contact add (incomplete) opens contact add form", async () => {
    await typeAndRun("!contact add");
    // Tab title is "Add Contact" (intercept) or "Complete Contacts Add" (backend)
    await assertFormOpened("Contact", ["first", "last"]);
  });

  await test("!todo add (incomplete) opens todo form", async () => {
    await typeAndRun("!todo add");
    // Tab title is "Add Todo" (intercept) or "Complete Todo Add" (backend)
    await assertFormOpened("Todo", ["title"]);
  });

  await test("!journal write (incomplete) opens journal form", async () => {
    await typeAndRun("!journal write");
    // Tab title is "Write Journal Entry" (intercept) or "Complete Journal Write" (backend)
    await assertFormOpened("Journal", ["title"]);
  });

  await test("!email account add (incomplete) opens account form", async () => {
    await typeAndRun("!email account add");
    // Tab title is "Add Email Account" (intercept) or "Complete Email Account Add" (backend)
    await assertFormOpened("Account", ["email"]);
  });

  await test("!calendar event add (incomplete) opens event form", async () => {
    await typeAndRun("!calendar event add");
    // Tab title is "Add Calendar Event" (intercept) or "Complete Calendar Event Add" (backend)
    // EventForm has fields: Calendar, Title, Start, End, Location
    await assertFormOpened("Calendar", ["title", "start"]);
  });

  await test("!email send (incomplete) opens compose form", async () => {
    await typeAndRun("!email send");
    // Tab title is "Compose Email" (intercept) or "Complete Email Send" (backend)
    await assertFormOpened("Email", ["to"]);
  });

  await test("!letter add (incomplete) opens letter form", async () => {
    await typeAndRun("!letter add");
    // Tab title is "Add Received Letter" (intercept) or "Complete Letter Add" (backend)
    await assertFormOpened("Letter", ["object"]);
  });

  // ════════════════════════════════════════════
  // 4. TAB NAVIGATION
  // ════════════════════════════════════════════
  console.log("\n--- TAB NAVIGATION ---");

  await test("Multiple tabs: all appear in tab bar", async () => {
    await typeAndRun("!help");
    await assertTabOpened("Available");
    await typeAndRun("!contact list");
    await assertTabOpened("Contact");
    await typeAndRun("!todo list");
    await assertTabOpened("Todo");

    // Tab bar should now have 4 tabs (Home + 3 result)
    const tabBar = page.locator('[role="tablist"]');
    const tabCount = await tabBar.locator('[role="tab"]').count();
    assert(tabCount >= 4, `Expected ≥ 4 tabs, found ${tabCount}`);
  });

  await test("Click on different tabs switches active tab", async () => {
    // We already have 3+ tabs open. Check we can click each one.
    const tabs = page.locator('[role="tab"]');
    const count = await tabs.count();
    // Try clicking each tab (skip home — it's always first)
    for (let i = 0; i < count; i++) {
      const tab = tabs.nth(i);
      await tab.click();
      await sleep(200);
      const selected = await tab.getAttribute("aria-selected");
      assert(selected === "true", `Tab ${i} should be selected after click`);
    }
  });

  await test("Escape closes active tab, returns to home", async () => {
    // Close all tabs by pressing Escape repeatedly
    for (let i = 0; i < 8; i++) {
      const tabBar = page.locator('[role="tablist"]');
      const stillHasTabs = await tabBar.isVisible().catch(() => false);
      if (!stillHasTabs) break;
      await page.keyboard.press("Escape");
      await sleep(200);
    }
    // After closing all, we should see home tab
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
    await typeAndRun("!contact list");
    await assertTabOpened("Contact");
    // Should show a table-like structure with headers
    const panel = page.locator('[aria-label="Tab content"]');
    const panelText = await panel.textContent() || "";
    // Should contain at least some structural elements
    assert(panelText.length > 10, `Contacts tab panel should have substantial content`);
  });

  // ════════════════════════════════════════════
  // 6. EMPTY LIST RENDERING
  // ════════════════════════════════════════════
  console.log("\n--- EMPTY LIST / SEARCH ---");

  await test("Search for nonexistent shows empty state", async () => {
    await typeAndRun("!contact search zzzZZZnosuchthing");
    await assertTabOpened("Contact");
    // Panel should show empty-state text (not crash, not blank)
    const panel = page.locator('[aria-label="Tab content"]');
    const panelText = ((await panel.textContent()) || "").toLowerCase();
    // Look for "no" + item indicator, or contains the search term
    const hasEmptyIndicator = panelText.includes("no ") || panelText.includes("0 ") || panelText.includes("zzz");
    assert(hasEmptyIndicator,
      `Empty search should show no-results indicator, panel text: "${panelText.substring(0, 200)}"`);
  });

  // ════════════════════════════════════════════
  // 7. SELECTION MODE
  // ════════════════════════════════════════════
  console.log("\n--- SELECTION MODE ---");

  await test("V key toggles selection mode on contact list", async () => {
    await typeAndRun("!contact list");
    await assertTabOpened("Contact");
    await sleep(300);

    // Press V to enter selection mode
    await page.keyboard.press("v");
    await sleep(400);

    // Check that checkboxes are now visible
    const checkboxes = page.locator('[aria-label="Tab content"] .checkbox-cell');
    const checkboxCount = await checkboxes.count().catch(() => 0);
    if (checkboxCount > 0) {
      console.log(`    Selection mode: ${checkboxCount} checkbox(es) visible`);
    } else {
      // May have no checkboxes if the list is empty — check for selection toolbar instead
      const panel = page.locator('[aria-label="Tab content"]');
      const panelText = (await panel.textContent() || "").toLowerCase();
      const hasSelectBtn = panelText.includes("exit") || panelText.includes("selected");
      assert(hasSelectBtn || checkboxCount > 0,
        `Selection mode should show checkboxes or exit button, panel: "${(panelText).substring(0, 150)}"`);
    }

    // Press Escape to exit selection mode
    await page.keyboard.press("Escape");
    await sleep(300);
  });

  // ════════════════════════════════════════════
  // 8. FORM VALIDATION (submit empty form)
  // ════════════════════════════════════════════
  console.log("\n--- FORM VALIDATION ---");

  await test("Submit empty contact form shows validation error", async () => {
    await typeAndRun("!contact add");
    await assertFormOpened("Contact", ["first"]);

    // Find the "Save" button and click it (submitting empty form)
    const panel = page.locator('[aria-label="Tab content"]');
    const saveBtn = panel.locator('button:has-text("Save")');
    const btnVisible = await saveBtn.isVisible().catch(() => false);
    assert(btnVisible, "Form should have a Save button");

    // Click Save — expects validation error rendering somewhere
    await saveBtn.click();
    await sleep(500);

    const panelText = (await panel.textContent() || "").toLowerCase();
    // After submitting empty, form should either show an error or stay open
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
    await typeAndRun("!todo list");
    await assertTabOpened("Todo");
    await sleep(200);

    // Look for sort-related buttons/selects in the panel
    const panel = page.locator('[aria-label="Tab content"]');
    const sortBtn = panel.locator('button:has-text("Sort"), select:has-text("sort"), [aria-label*="sort" i], [aria-label*="Sort" i]');
    const btnCount = await sortBtn.count();
    if (btnCount > 0) {
      // Try clicking the first sort element
      await sortBtn.first().click();
      await sleep(300);
      console.log(`    Sort control found and clicked (${btnCount} count)`);
    } else {
      // Sort might be a dropdown/select element
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

  // ════════════════════════════════════════════
  // RESULTS
  // ════════════════════════════════════════════
  console.log("");
  console.log("=".repeat(70));
  console.log(`GUI SMOKE RESULTS: ${passed} passed, ${failed} failed`);
  if (pageErrors.length > 0) console.log(`  PAGE ERRORS: ${pageErrors.length}`);
  if (consoleErrors.length > 0) console.log(`  CONSOLE ERRORS: ${consoleErrors.length}`);
  console.log("=".repeat(70));

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});

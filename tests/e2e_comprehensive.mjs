/** Comprehensive Playwright E2E test for lighterbird. */

import { chromium } from "playwright";
import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter, getResultPanelText, getPopupText,
  assertTabOpened,
  runWithBrowser, sleep, getTabCount,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

// ── Runner ─────────────────────────────────────────────────────────────────

async function runTests(page) {
  // ═══════════════════════════════════════════
  console.log("\n--- HELP ---");
  await test("!help shows available commands", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("account") || text.includes("!email") || text.includes("!calendar"),
      `Help text should contain command names, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- LISTS ---");

  // Each list command is now tested with proper DOM assertions (tab opened + content)
  await test("!email account list shows account list", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    await assertTabOpened("Account");
  });

  await test("!contact list shows contacts", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    await assertTabOpened("Contact");
  });

  await test("!todo list shows todos", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    await assertTabOpened("Todo");
  });

  await test("!journal list shows journal entries", async () => {
    await typeCommand("!journal list");
    await pressEnter();
    await assertTabOpened("Journal");
  });

  await test("!calendar account list shows calendars", async () => {
    await typeCommand("!calendar account list");
    await pressEnter();
    await assertTabOpened("Calendar");
  });

  await test("!letter list shows letters", async () => {
    await typeCommand("!letter list");
    await pressEnter();
    await assertTabOpened("Letter");
  });

  await test("!user info list shows profiles", async () => {
    await typeCommand("!user info list");
    await pressEnter();
    try {
      await assertTabOpened("User Info");
    } catch {
      // Title might be "User Profiles" in some builds
      await assertTabOpened("Profile");
    }
  });

  // ═══════════════════════════════════════════
  console.log("\n--- EMAIL LIST GUI SEARCH ---");

  await test("!email list opens email message list", async () => {
    await typeCommand("!email list");
    await pressEnter();
    await assertTabOpened("Email");
  });

  await test("Search / opens search bar, hides action buttons (typing mode)", async () => {
    await typeCommand("!email list");
    await pressEnter();
    await sleep(300);
    // Ensure the command input is not focused (blur it so the EmailListTab
    // keyboard handler processes the / key instead of the input field)
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
    await sleep(100);

    // Press / to open search
    await page.keyboard.press('/');
    await sleep(400);

    // Search input should be visible
    const searchInput = page.locator('[aria-label="Search messages"]');
    assert(await searchInput.isVisible(), 'Search input should appear after pressing /');
    console.log('  Search input visible ✓');

    // In typing mode (full-width search), action buttons should NOT be visible
    const selectBtn = page.locator('.tool-btn', { hasText: 'Select' });
    const hasSelect = await selectBtn.isVisible().catch(() => false);
    assert(!hasSelect, 'Select button should NOT be visible during search typing mode');
    console.log('  Select button hidden during typing ✓');

    // Verify the search bar is full-width (has class "full")
    const searchBarFull = page.locator('.search-bar.full');
    assert(await searchBarFull.isVisible(), 'Search bar should have "full" width class during typing');
    console.log('  Search bar is full-width ✓');
  });

  await test("Search Enter confirms, shows action buttons alongside search bar", async () => {
    await typeCommand("!email list");
    await pressEnter();
    await sleep(300);
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
    await sleep(100);

    // Open search
    await page.keyboard.press('/');
    await sleep(300);
    const searchInput = page.locator('[aria-label="Search messages"]');
    assert(await searchInput.isVisible(), 'Search input should appear');

    // Type a query and press Enter
    await searchInput.fill('test');
    await page.keyboard.press('Enter');
    await sleep(500);

    // After Enter: search input should still be visible
    assert(await searchInput.isVisible(), 'Search input should remain visible after Enter');
    console.log('  Search input stays visible after Enter ✓');

    // After Enter: action buttons should now be visible (search confirmed mode)
    const selectBtn = page.locator('.tool-btn', { hasText: 'Select' });
    const syncBtn = page.locator('.tool-btn', { hasText: 'Sync' });
    assert(await selectBtn.isVisible(), 'Select button should be visible after Enter (confirmed search)');
    assert(await syncBtn.isVisible(), 'Sync button should be visible after Enter (confirmed search)');
    console.log('  Action buttons (Select, Sync) visible after Enter ✓');

    // The search bar should now be compact (not full-width)
    const searchBarFull = page.locator('.search-bar.full');
    const searchBarCompact = page.locator('.search-bar.compact');
    assert(!(await searchBarFull.isVisible().catch(() => false)), 'Search bar should NOT be full-width after Enter');
    assert(await searchBarCompact.isVisible(), 'Search bar should be compact after Enter');
    console.log('  Search bar is compact mode ✓');
  });

  await test("Search Escape closes search and returns to view mode", async () => {
    await typeCommand("!email list");
    await pressEnter();
    await sleep(300);
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
    await sleep(100);

    // Open search, type, confirm
    await page.keyboard.press('/');
    await sleep(300);
    const searchInput = page.locator('[aria-label="Search messages"]');
    await searchInput.fill('test');
    await page.keyboard.press('Enter');
    await sleep(300);

    // Now press Escape to close search
    await page.keyboard.press('Escape');
    await sleep(400);

    // Search input should be gone
    assert(!(await searchInput.isVisible().catch(() => false)),
      'Search input should be hidden after Escape');

    // View-mode hint should be visible again
    const searchHint = page.locator('.search-hint');
    assert(await searchHint.isVisible(), 'Search hint (/) should be visible again after Escape');
    console.log('  Search closes via Escape ✓');

    // The Select button should be visible in view mode
    const selectBtn = page.locator('.tool-btn', { hasText: 'Select' });
    assert(await selectBtn.isVisible(), 'Select button should be visible in view mode after search closes');
    console.log('  View mode restored after search closes ✓');
  });

  // ═══════════════════════════════════════════
  console.log("\n--- CREATE (via API completion) ---");

  await test("!contact add --first-name Jane --last-name Doe --email jane@test.com", async () => {
    await typeCommand("!contact add --first-name Jane --last-name Doe --email jane@test.com");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Created") || text.includes("added") || text.includes("Jane"),
      `Expected success, got: '${text.substring(0, 200)}'`);
  });

  await test("!todo add Buy milk", async () => {
    await typeCommand("!todo add Buy milk");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("added") || text.includes("Created") || text.includes("milk"),
      `Expected success, got: '${text.substring(0, 200)}'`);
  });

  await test("!journal write My first entry", async () => {
    await typeCommand("!journal write My first entry");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("written") || text.includes("Created") || text.includes("first"),
      `Expected success, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- INTERACTIVE FORM (missing required args) ---");

  await test("!contact add (missing args → form popup)", async () => {
    await typeCommand("!contact add");
    await pressEnter();
    await sleep(600);
    const text = await getPopupText();
    assert(text.includes("Required") || text.includes("form") || text.includes("first-name") || text.includes("Missing"),
      `Expected form-required, got: '${text.substring(0, 200)}'`);
  });

  await test("!email account add (missing args → form popup)", async () => {
    await typeCommand("!email account add");
    await pressEnter();
    await sleep(600);
    const text = await getPopupText();
    assert(text.includes("Required") || text.includes("form") || text.includes("email") || text.includes("Missing"),
      `Expected form-required, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- BACKUP ---");

  await test("!backup now creates backup", async () => {
    await typeCommand("!backup now");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Backup") || text.includes("Created") || text.includes("backup"),
      `Expected backup confirmation, got: '${text.substring(0, 200)}'`);
  });

  await test("!backup list shows backups", async () => {
    await typeCommand("!backup list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("backup") || text.includes("strategy") || text.includes(".7z"),
      `Expected backup list, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- SYNC ---");

  await test("!sync runs sync", async () => {
    await typeCommand("!sync");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Sync") || text.includes("Result") || !text.includes("Error"),
      `Expected sync result, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- TAB NAVIGATION ---");

  await test("Can navigate home with Escape", async () => {
    await page.keyboard.press("Escape");
    await sleep(300);
    const input = page.locator("[aria-label='Message input']");
    const visible = await input.isVisible().catch(() => false);
    assert(visible, "Message input should be visible after Escape");
  });

  // ═══════════════════════════════════════════
  console.log("\n--- LLM ---");

  await test("!llm prompt shows system prompt", async () => {
    await typeCommand("!llm prompt");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("lighterbird") || text.includes("prompt") || text.includes("command"),
      `Expected system prompt info, got: '${text.substring(0, 200)}'`);
  });

  await test("!llm profile list shows profiles", async () => {
    await typeCommand("!llm profile list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("profile") || text.includes("Deepseek") || text.includes("active"),
      `Expected profile list, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- VERIFY LIST AFTER CREATES ---");

  await test("!contact list shows created contacts", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Jane") || text.includes("jane@test.com"),
      `Expected Jane in list, got: '${text.substring(0, 200)}'`);
  });

  await test("!todo list shows created todos", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("milk") || text.includes("Buy"),
      `Expected 'Buy milk' in list, got: '${text.substring(0, 200)}'`);
  });

  await test("!journal list shows created entries", async () => {
    await typeCommand("!journal list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("first") || text.includes("entry"),
      `Expected 'first entry' in list, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- SEARCH ---");

  await test("!contact search Jane finds contacts", async () => {
    await typeCommand("!contact search Jane");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Jane") || !text.includes("Error"),
      `Expected search results, got: '${text.substring(0, 200)}'`);
  });

  await test("!todo search milk finds todos", async () => {
    await typeCommand("!todo search milk");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("mil") || text.includes("Buy") || !text.includes("Error"),
      `Expected search results, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- USER SAVED COMMANDS ---");

  await test("!user saved-commands list", async () => {
    await typeCommand("!user saved-commands list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- TODO TREE ---");

  await test("!todo tree shows tree view", async () => {
    await typeCommand("!todo tree");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("milk") || text.includes("Buy") || !text.includes("Error"),
      `Expected todo tree, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- LETTER ADD ---");

  await test("!letter add with object", async () => {
    await typeCommand("!letter add --object 'Test Letter' --body-text 'Hello World'");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("added") || text.includes("Created") || text.includes("Test Letter"),
      `Expected letter added, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- BACKUP CONFIG ---");

  await test("!backup config list", async () => {
    await typeCommand("!backup config list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("strategy") || text.includes("default") || !text.includes("Error"),
      `Expected backup config list, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log("");

  const tabCount = await getTabCount();
  console.log(`  Final tabs visible: ${tabCount}`);
}

// ── Bootstrap ──────────────────────────────────────────────────────────────

runWithBrowser(FRONTEND_URL, CHROME_PATH, "COMPREHENSIVE PLAYWRIGHT E2E TESTS", runTests);

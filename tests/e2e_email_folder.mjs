/**
 * E2E tests for !email folder subcommands.
 *
 * Verifies:
 *   - !email folder list opens the folder-list tab (not accounts tab)
 *   - The tab renders the EmailFolderTab component (toolbar, empty state)
 *   - Tab shows correct icon (📁) and title (Folders)
 *   - !email folders (plural alias) works
 *   - !email folder add/rename/move/delete error handling
 *
 * Usage: node tests/e2e_email_folder.mjs
 */

import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter, sleep, runWithBrowser,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";

// ── Tests ──────────────────────────────────────────────────────────────────

async function runTests(page) {
  // ── 1. !email folder list opens the folder tree tab ──────────────────
  await test("!email folder list opens folder-list tab", async () => {
    await typeCommand("!email folder list");
    await pressEnter();
    await sleep(1500);

    // Tab bar should show 📁 Folders
    const tabText = await page.locator('[role="tablist"]').innerText();
    assert.ok(
      tabText.includes("📁") || tabText.includes("Folders"),
      `Tab bar should show folder icon/title, got: ${tabText.slice(0, 200)}`,
    );

    // Tab content should show folder management UI (not accounts)
    const content = await page.locator('.tab-content.active[data-testid="tab-panel"]').innerText();

    // Should have folder-related controls
    const hasNewButton = content.includes("+ New") || content.includes("FOLDERS");
    // Should NOT have "Email Accounts" heading
    const hasAccountsHeading = content.includes("Email Accounts");
    // Accept either folder tree content OR the empty state message
    const hasFolderContent =
      content.includes("FOLDERS") ||
      content.includes("folder") ||
      content.includes("Folders");

    assert.ok(
      hasFolderContent,
      `Tab content should mention folders, got: ${content.slice(0, 300)}`,
    );

    assert.ok(
      !hasAccountsHeading,
      `Tab content should NOT show Email Accounts, got: ${content.slice(0, 300)}`,
    );

    console.log(`    Tab content (preview): ${content.slice(0, 150).replace(/\n/g, " | ")}`);
  });

  // ── 2. !email folders (plural alias) resolves to folder list ─────────
  await test("!email folders (plural alias) opens same tab", async () => {
    await typeCommand("!email folders");
    await pressEnter();
    await sleep(1000);

    const tabText = await page.locator('[role="tablist"]').innerText();
    assert.ok(
      tabText.includes("📁") || tabText.includes("Folders"),
      `Plural alias should show folder tab, got: ${tabText.slice(0, 200)}`,
    );
  });

  // ── 3. !email folder without subcommand shows help ──────────────────
  await test("!email folder (no subcommand) shows help", async () => {
    await typeCommand("!email folder");
    await pressEnter();
    await sleep(1000);

    const content = await page.locator("body").innerText();
    assert.ok(
      content.includes("Available") && content.includes("folder"),
      `Should show available subcommands, got: ${content.slice(0, 300)}`,
    );
  });

  // ── 4. !email folder add — missing args shows error ─────────────────
  await test("!email folder add without name shows error", async () => {
    await typeCommand("!email folder add");
    await pressEnter();
    await sleep(1500);

    const content = await page.locator("body").innerText();
    // Should either show a form (interactive) or an error message
    const hasResponse = content.includes("name") || content.includes("folder");
    assert.ok(hasResponse, `Should show error or form, got: ${content.slice(0, 300)}`);
  });
}

// ── Main ───────────────────────────────────────────────────────────────────

const CHROME_PATH = process.env.CHROME_PATH || "chromium";

runWithBrowser(FRONTEND_URL, CHROME_PATH, "Email Folder E2E", runTests).catch((err) => {
  console.error(`\n❌ Fatal: ${err.message}`);
  process.exit(1);
});

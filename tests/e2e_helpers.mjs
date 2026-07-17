/**
 * Shared E2E test helpers for lighterbird Playwright scripts.
 *
 * Provides common infrastructure: browser launch, typeCommand, assertTabOpened,
 * assertFormOpened, dismissAllTabs, getResultPanelText, screenshot-on-failure.
 */

import { chromium } from "playwright";
import { strict as assert } from "assert";

// ── Shared state (set by runWithBrowser) ───────────────────────────────
export let page = null;
export let pageErrors = [];
export let consoleErrors = [];
export let passed = 0;
export let failed = 0;
export let screenshotCounter = 0;

// ── Utility ────────────────────────────────────────────────────────────

export async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Browser interaction ────────────────────────────────────────────────

/**
 * Type a command into the centralized command bar.
 * First navigates to the home tab if needed.
 */
export async function typeCommand(cmd) {
  const input = page.locator("[aria-label='Message input']");
  let visible = await input.isVisible().catch(() => false);
  if (!visible) {
    await page.keyboard.press("Alt+1");
    await sleep(200);
    const stillHidden = !(await input.isVisible().catch(() => false));
    if (stillHidden) {
      const homeTab = page.locator('[role="tab"]', { hasText: "Home" });
      if (await homeTab.isVisible().catch(() => false)) {
        await homeTab.click();
        await sleep(200);
      }
    }
  }
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(30);
  await input.pressSequentially(cmd, { delay: 50 });
  await sleep(150);
}

/** Press Enter to submit a command, then wait for results. */
export async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(400);
}

/** Press Tab (for autocomplete), then wait. */
export async function pressTab() {
  await page.keyboard.press("Tab");
  await sleep(400);
}

/**
 * Read the body text from the page (fallback — use getResultPanelText when possible).
 */
export async function getPopupText() {
  try {
    // Wait a bit for rendering
    await sleep(200);
    const body = page.locator("body");
    let text = ((await body.textContent()) || "").trim();
    text = text.replace(/\s+/g, " ").trim();
    return text;
  } catch {
    return "(no result)";
  }
}

/**
 * Read the visible tab panel text.
 * Tries each tabpanel in order, returns text of the first visible one.
 * Falls back to body text if no tabpanel is visible.
 */
export async function getResultPanelText() {
  try {
    for (let attempt = 0; attempt < 3; attempt++) {
      await sleep(150);
      const panels = page.locator('[role="tabpanel"]');
      const count = await panels.count();
      for (let i = 0; i < count; i++) {
        if (await panels.nth(i).isVisible().catch(() => false)) {
          return ((await panels.nth(i).textContent()) || "").trim().replace(/\s+/g, " ");
        }
      }
    }
    const body = page.locator("body");
    return ((await body.textContent()) || "").trim().replace(/\s+/g, " ");
  } catch {
    return "(no result)";
  }
}

/** Get the active tab's HTML title attribute (full, untruncated). */
export async function getActiveTabTitleAttr() {
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });
  const activeTab = tabBar.locator('[role="tab"][aria-selected="true"]');
  await activeTab.waitFor({ state: "visible", timeout: 3000 });
  return (await activeTab.getAttribute("title") || "").trim();
}

/** Get how many tabs are currently in the tab bar. */
export async function getTabCount() {
  const tabs = page.locator('[role="tab"]');
  return await tabs.count();
}

// ── Tab and UI assertions ─────────────────────────────────────────────

/**
 * Assert a tab with the given title substring opened.
 * Checks: tab bar visible, active tab contains expectedTitle, content panel exists and has text.
 */
export async function assertTabOpened(expectedTitle) {
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });
  const tabCount = await tabBar.locator('[role="tab"]').count();
  if (tabCount < 2) {
    throw new Error(`Expected ≥2 tabs (home + result), found ${tabCount}`);
  }

  const titleAttr = await getActiveTabTitleAttr();
  if (!titleAttr.toLowerCase().includes(expectedTitle.toLowerCase())) {
    throw new Error(
      `Active tab title should contain "${expectedTitle}", got "${titleAttr}"`
    );
  }

  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = (await panel.textContent() || "").trim();
  if (panelText.length === 0) {
    throw new Error(`Tab panel for "${expectedTitle}" is empty`);
  }
}

/**
 * Assert a form popup opened with the given title and field hints.
 * Checks: tab bar shows form, content panel has inputs, field hints match, submit button exists.
 */
export async function assertFormOpened(expectedTitle, fieldHints = []) {
  const tabBar = page.locator('[role="tablist"]');
  await tabBar.waitFor({ state: "visible", timeout: 4000 });

  const titleAttr = await getActiveTabTitleAttr();
  if (!titleAttr.toLowerCase().includes(expectedTitle.toLowerCase())) {
    throw new Error(
      `Form tab title should contain "${expectedTitle}", got "${titleAttr}"`
    );
  }

  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = (await panel.textContent() || "").toLowerCase();

  const inputs = await panel.locator("input, textarea, select, [contenteditable]").count();
  if (inputs === 0) {
    throw new Error(`Form "${expectedTitle}" should have at least one input`);
  }

  for (const hint of fieldHints) {
    if (!panelText.includes(hint.toLowerCase())) {
      throw new Error(
        `Form "${expectedTitle}" should mention "${hint}" (field hint), panel text: "${panelText.substring(0, 200)}"`
      );
    }
  }

  const submitBtn = panel.locator(
    'button[type="submit"], button:has-text("Save"), button:has-text("Add"), button:has-text("Create"), button:has-text("Send")'
  );
  const btnCount = await submitBtn.count();
  if (btnCount === 0) {
    throw new Error(`Form "${expectedTitle}" should have a submit button`);
  }
}

/** Assert the home tab is active (input is visible). */
export async function assertHomeActive() {
  const homeSection = page.locator('[aria-label="Home tab"]');
  await homeSection.waitFor({ state: "visible", timeout: 2000 });
  const input = page.locator("[aria-label='Message input']");
  const inputVisible = await input.isVisible().catch(() => false);
  if (!inputVisible && !(await homeSection.isVisible())) {
    throw new Error("Home tab should be active (input or home section visible)");
  }
}

/**
 * Assert the active tab panel contains the given text substring.
 */
export async function assertPanelContains(text) {
  const panel = page.locator('[aria-label="Tab content"]');
  await panel.waitFor({ state: "visible", timeout: 3000 });
  const panelText = await panel.textContent() || "";
  if (!panelText.toLowerCase().includes(text.toLowerCase())) {
    throw new Error(`Tab panel should contain "${text}"`);
  }
}

// ── Tab cleanup ───────────────────────────────────────────────────────

/** Dismiss all result tabs: go home then press Escape multiple times. */
export async function dismissAllTabs() {
  await page.keyboard.press("Alt+1");
  await sleep(150);
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Escape");
    await sleep(100);
  }
  try {
    const dismissBtn = page.locator("button", { hasText: "Dismiss notice" });
    if (await dismissBtn.isVisible({ timeout: 300 })) {
      await dismissBtn.click();
      await sleep(200);
    }
  } catch { /* no notice */ }
}

// ── Test wrapper ──────────────────────────────────────────────────────

/**
 * Run a single test with screenshot-on-failure and cleanup.
 * Updates the shared passed/failed counters.
 * @param {string} desc — Test description
 * @param {function} fn — Async test function
 */
export async function test(desc, fn) {
  try {
    await fn();
    console.log(`  \u2713 ${desc}`);
    passed++;
  } catch (e) {
    if (screenshotCounter < 3) {
      const ssPath = `/tmp/e2e-fail-${screenshotCounter++}.png`;
      try {
        await page.screenshot({ path: ssPath });
        console.log(`    Screenshot: ${ssPath}`);
      } catch {}
    }
    // Log page text on failure for context
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

/**
 * Reset global counters (for re-use across test suites in the same script).
 */
export function resetCounters() {
  passed = 0;
  failed = 0;
  screenshotCounter = 0;
}

// ── Browser lifecycle ─────────────────────────────────────────────────

/**
 * Launch a headless Chromium browser, create a page with error tracking,
 * navigate to the frontend URL, dismiss any notice, and return the page.
 *
 * @param {string} frontendUrl
 * @param {string} chromePath — path to Chromium executable
 * @returns {Promise<{browser, page}>}
 */
export async function launchBrowser(frontendUrl, chromePath) {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } });
  const p = await context.newPage();

  // Error tracking
  p.on("pageerror", (err) => {
    pageErrors.push(err.message);
    console.log("  [BROWSER ERROR]", err.message);
  });
  p.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
      console.log("  [CONSOLE ERROR]", msg.text());
    }
  });

  await p.goto(frontendUrl, { waitUntil: "networkidle" });
  console.log("\u2713 Page loaded:", await p.title());
  await sleep(500);

  // Dismiss any welcome notice
  try {
    const dismissBtn = p.locator("button", { hasText: "Dismiss notice" });
    if (await dismissBtn.isVisible({ timeout: 300 })) {
      await dismissBtn.click();
      await sleep(200);
    }
  } catch { /* no notice */ }

  return { browser, page: p };
}

/**
 * Print results summary and exit with appropriate code.
 * @param {string} suiteName
 */
export function printResults(suiteName) {
  console.log();
  if (pageErrors.length > 0) {
    console.log(`  [ERROR] ${pageErrors.length} unhandled page error(s) during session`);
  }
  if (consoleErrors.length > 0) {
    console.log(`  [ERROR] ${consoleErrors.length} console error(s) during session`);
  }
  console.log(`RESULTS (${suiteName}): ${passed} passed, ${failed} failed`);
}

/**
 * Full test runner: launch browser, run tests, print results, close browser, exit.
 *
 * @param {string} frontendUrl
 * @param {string} chromePath
 * @param {string} suiteName
 * @param {function(page): Promise<void>} runTestsFn — async function that runs all tests
 */
export async function runWithBrowser(frontendUrl, chromePath, suiteName, runTestsFn) {
  let browser;
  try {
    const result = await launchBrowser(frontendUrl, chromePath);
    browser = result.browser;
    page = result.page;

    console.log();
    console.log("=".repeat(70));
    console.log(`${suiteName}`);
    console.log("=".repeat(70));
    console.log();

    await runTestsFn(page);

    printResults(suiteName);
    await browser.close();
    process.exit(failed > 0 ? 1 : 0);
  } catch (e) {
    console.error("FATAL:", e.message);
    if (browser) await browser.close().catch(() => {});
    process.exit(1);
  }
}

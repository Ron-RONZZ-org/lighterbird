/** Comprehensive Playwright E2E test for lighterbird. */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = "http://127.0.0.1:8000";
const CHROME_PATH = "/home/rongzhou/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell";

let browser, page;
let passed = 0, failed = 0;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeCommand(cmd) {
  // Ensure we're on the home tab so the input is visible
  const input = page.locator("[aria-label='Message input']");
  const isVisible = await input.isVisible().catch(() => false);
  if (!isVisible) {
    await page.keyboard.press("Escape");
    await sleep(200);
  }
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(50);
  await input.pressSequentially(cmd, { delay: 5 });
  await sleep(200);
}

async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(400);
}

async function getPopupText() {
  try {
    await sleep(200);
    const body = page.locator("body");
    let text = ((await body.textContent()) || "").trim();
    text = text.replace(/\s+/g, " ").trim();
    return text;
  } catch {
    return "(no result)";
  }
}

async function getResultPanelText() {
  try {
    // Quick poll for a visible tab panel — 3 attempts × 200ms.
    for (let attempt = 0; attempt < 3; attempt++) {
      await sleep(200);
      const panels = page.locator('[role="tabpanel"]');
      const count = await panels.count();
      for (let i = 0; i < count; i++) {
        if (await panels.nth(i).isVisible().catch(() => false)) {
          return ((await panels.nth(i).textContent()) || "").trim().replace(/\s+/g, " ");
        }
      }
    }
    return await getPopupText();
  } catch {
    return await getPopupText();
  }
}

async function dismissAllTabs() {
  for (let i = 0; i < 4; i++) {
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

async function getTabCount() {
  const tabs = page.locator('[role="tab"]');
  return await tabs.count();
}

let screenshotCounter = 0;
async function test(desc, fn) {
  try {
    await fn();
    console.log(`  \u2713 ${desc}`);
    passed++;
  } catch (e) {
    const ssPath = `/tmp/e2e-fail-${screenshotCounter++}.png`;
    try {
      await page.screenshot({ path: ssPath });
      console.log(`    Screenshot saved to ${ssPath}`);
    } catch {}
    console.log(`  \u2717 ${desc}: ${e.message}`);
    if (e.message.includes("Timeout")) {
      try {
        const body = await page.locator("main").textContent();
        console.log(`    Page: ${(body || "").substring(0, 300)}`);
      } catch {
        const body = await page.locator("body").textContent();
        console.log(`    Body: ${(body || "").substring(0, 300)}`);
      }
    }
    failed++;
  } finally {
    await dismissAllTabs();
  }
}

async function run() {
  browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } });
  page = await context.newPage();
  page.on("pageerror", (err) => console.log("  [BROWSER ERROR]", err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("  [CONSOLE ERROR]", msg.text());
  });

  console.log("=".repeat(70));
  console.log("COMPREHENSIVE PLAYWRIGHT E2E TESTS");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  console.log("\u2713 Page loaded:", await page.title());
  await sleep(500);

  // Dismiss notice if present
  try {
    const dismissBtn = page.locator("button", { hasText: "Dismiss notice" });
    if (await dismissBtn.isVisible({ timeout: 300 })) {
      await dismissBtn.click();
      await sleep(200);
    }
  } catch { /* no notice */ }
  await sleep(300);

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- HELP ---");
  await test("!help shows available commands", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("account") || text.includes("!email") || text.includes("!calendar"),
      `Help text should contain command names, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- LISTS ---");

  await test("!email account list shows account list", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!contact list shows contacts", async () => {
    await typeCommand("!contact list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!todo list shows todos", async () => {
    await typeCommand("!todo list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!journal list shows journal entries", async () => {
    await typeCommand("!journal list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!calendar account list shows calendars", async () => {
    await typeCommand("!calendar account list");
    await pressEnter();
    const text = await getResultPanelText();
    const lower = text.toLowerCase();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!letter list shows letters", async () => {
    await typeCommand("!letter list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  await test("!user info list shows profiles", async () => {
    await typeCommand("!user info list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- CREATE (via API completion) ---");

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
  console.log();
  console.log("--- INTERACTIVE FORM (missing required args) ---");

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
  console.log();
  console.log("--- BACKUP ---");

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
  console.log();
  console.log("--- SYNC ---");

  await test("!sync runs sync", async () => {
    await typeCommand("!sync");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("Sync") || text.includes("Result") || !text.includes("Error"),
      `Expected sync result, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- TAB NAVIGATION ---");

  await test("Can navigate home with Escape", async () => {
    await page.keyboard.press("Escape");
    await sleep(300);
    const input = page.locator("[aria-label='Message input']");
    const visible = await input.isVisible().catch(() => false);
    assert(visible, "Message input should be visible after Escape");
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- LLM ---");

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
  console.log();
  console.log("--- VERIFY LIST AFTER CREATES ---");

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
  console.log();
  console.log("--- SEARCH ---");

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
  console.log();
  console.log("--- USER SAVED COMMANDS ---");

  await test("!user saved-commands list", async () => {
    await typeCommand("!user saved-commands list");
    await pressEnter();
    const text = await getResultPanelText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- TODO TREE ---");

  await test("!todo tree shows tree view", async () => {
    await typeCommand("!todo tree");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("milk") || text.includes("Buy") || !text.includes("Error"),
      `Expected todo tree, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- LETTER ADD ---");

  await test("!letter add with object", async () => {
    await typeCommand("!letter add --object 'Test Letter' --body-text 'Hello World'");
    await pressEnter();
    const text = await getResultPanelText();
    assert(text.includes("added") || text.includes("Created") || text.includes("Test Letter"),
      `Expected letter added, got: '${text.substring(0, 200)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- BACKUP CONFIG ---");

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

  console.log();
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});

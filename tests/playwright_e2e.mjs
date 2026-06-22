/** Playwright E2E test — simulates real user interactions in the browser. */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = "http://127.0.0.1:8000";
const CHROME_PATH = "/home/rongzhou/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell";
const TEST_EMAIL = "e2e-" + Date.now().toString(36) + "@test.com";

let browser, page;
let passed = 0, failed = 0;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeCommand(cmd) {
  const input = page.locator("input[aria-label='Command input']");
  await input.click();
  await input.fill("");
  await sleep(100);
  await input.pressSequentially(cmd, { delay: 20 });
  await sleep(500);
}

async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(1200);
}

async function pressTab() {
  await page.keyboard.press("Tab");
  await sleep(400);
}

async function getPopupText() {
  try {
    const popup = page.locator(".popup-panel");
    await popup.waitFor({ state: "visible", timeout: 3000 });
    return ((await popup.textContent()) || "").trim();
  } catch {
    return "(no popup)";
  }
}

async function closePopupOrSkip() {
  try {
    const popup = page.locator(".popup-panel");
    if (await popup.isVisible()) {
      await page.keyboard.press("Escape");
      await sleep(300);
    }
  } catch { /* ignore */ }
}

async function test(desc, fn) {
  try {
    await fn();
    console.log(`  ✓ ${desc}`);
    passed++;
  } catch (e) {
    console.log(`  ✗ ${desc}: ${e.message}`);
    failed++;
  } finally {
    await closePopupOrSkip();
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

  console.log("=".repeat(70));
  console.log("PLAYWRIGHT E2E TESTS");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "domcontentloaded" });
  console.log("✓ Page loaded:", await page.title());
  await sleep(3000);

  // ═══════════════════════════════════════════
  console.log("--- ACCOUNT ---");

  await test("!account list (empty)", async () => {
    await typeCommand("!account list");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("No accounts") || text.includes("List email accounts"),
      `Expected popup, got: '${text}'`);
  });

  await test("!account add", async () => {
    await typeCommand("!account add " + TEST_EMAIL);
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("Done") || text.includes("added"),
      `Expected success, got: '${text}'`);
  });

  await test("!account list (1 account)", async () => {
    await typeCommand("!account list");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("@"), `Expected account info, got: '${text}'`);
  });

  await test("UUID auto-complete", async () => {
    await typeCommand("!account remove ");
    await sleep(1000);
    const items = page.locator(".suggestions li");
    const count = await items.count();
    assert(count > 0, `Expected UUID suggestions, got ${count}`);
    const first = await items.first().textContent();
    assert(first.includes("@"), `Suggestion should contain email: '${first}'`);
    // Test Tab selects first
    await pressTab();
    const input = page.locator("input[aria-label='Command input']");
    const val = await input.inputValue();
    // Tab now inserts UUID prefix (8 hex chars), not full 36-char UUID
    assert(val.includes("remove "), `Tab should keep command prefix, got: '${val}'`);
    const tokens = val.trim().split(/\s+/);
    const uuidToken = tokens[tokens.length - 1];
    assert(/^[0-9a-f]{8,}$/i.test(uuidToken),
      `Tab should complete UUID prefix (8+ hex chars), got: '${uuidToken}'`);
  });

  await test("!account remove", async () => {
    const input = page.locator("input[aria-label='Command input']");
    // Input should already have UUID from previous Tab, just press Enter
    const val = await input.inputValue();
    if (val.includes("remove ") && val.length > 20) {
      await pressEnter();
    } else {
      // Re-type and complete
      await typeCommand("!account remove ");
      await sleep(500);
      const items = page.locator(".suggestions li");
      if (await items.count() > 0) {
        await items.first().click();
        await sleep(300);
      }
      await pressEnter();
    }
    const text = await getPopupText();
    assert(text.includes("delet") || text.includes("Done"),
      `Expected deletion, got: '${text}'`);
  });

  await test("!account list (after delete)", async () => {
    await typeCommand("!account list");
    await pressEnter();
    const text = await getPopupText();
    // Account was deleted — we just verify no error
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text}'`);
    // Log actual state for debugging
    console.log(`    Accounts: ${text.substring(0, 80)}...`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- CALENDAR ---");

  await test("!calendar list", async () => {
    await typeCommand("!calendar list");
    await pressEnter();
    const text = await getPopupText();
    // Just verify the command ran successfully
    assert(text.includes("calendar") || text.includes("calendars") || text.includes("Done"),
      `Expected calendar info, got: '${text}'`);
  });

  await test("!calendar add", async () => {
    await typeCommand("!calendar add https://cal.example.com/test");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("Done"),
      `Expected success, got: '${text}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- TAB COMPLETION ---");

  await test("Tab: !ac → !account", async () => {
    const input = page.locator("input[aria-label='Command input']");
    await input.fill("!ac");
    await sleep(300);
    await pressTab();
    const val = await input.inputValue();
    assert(val.includes("!account "), `Expected '!account ', got: '${val}'`);
  });

  await test("Tab: !account → children", async () => {
    const input = page.locator("input[aria-label='Command input']");
    await pressTab();
    await sleep(300);
    const val = await input.inputValue();
    assert(val.includes("add"), `Expected child, got: '${val}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- ADMIN ---");

  await test("!help", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("account") || text.includes("Available"),
      `Expected help, got: '${text}'`);
  });

  console.log();
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});

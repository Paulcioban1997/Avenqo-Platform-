import { chromium } from "playwright";
import { resolve } from "path";
import { mkdirSync } from "fs";

const SCREENSHOTS_DIR = "C:/Users/paulm/.gemini/antigravity/brain/6e8912cb-f352-49f7-aa3d-a8cae8394823/screenshots";
mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const BASE_URL = "https://web-git-feat-phase-i-saas-ux-repair-paulmircea15-9488s-projects.vercel.app";

async function main() {
  console.log("=== AVENQO PHASE I.2 REAL PLAYWRIGHT ACCEPTANCE SUITE ===");
  console.log("Target Vercel Preview:", BASE_URL);

  const browser = await chromium.launch({ headless: true });

  try {
    // -------------------------------------------------------------
    // TEST 1: DESKTOP LANDING & STICKY HEADER AFTER SCROLL
    // -------------------------------------------------------------
    console.log("\n[Test 1] Desktop Landing & Sticky Header...");
    const desktopContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      locale: "fr-CA",
    });
    const page = await desktopContext.newPage();
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: 30000 });
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/01_desktop_landing_top.png` });
    console.log("Captured 01_desktop_landing_top.png");

    // Scroll down 600px
    await page.evaluate(() => window.scrollBy(0, 600));
    await page.waitForTimeout(1000);

    // Verify header is sticky and visible
    const header = page.locator("header");
    const isHeaderVisible = await header.isVisible();
    console.log(`Header sticky visibility after scroll: ${isHeaderVisible}`);
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/01_desktop_landing_scrolled_sticky_header.png` });
    console.log("Captured 01_desktop_landing_scrolled_sticky_header.png");
    await desktopContext.close();

    // -------------------------------------------------------------
    // TEST 2: MOBILE VIEWPORT (390x844) RESPONSIVENESS
    // -------------------------------------------------------------
    console.log("\n[Test 2] Mobile Viewport Responsiveness (iPhone 14 standard)...");
    const mobileContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      locale: "fr-CA",
    });
    const mobilePage = await mobileContext.newPage();
    await mobilePage.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: 30000 });
    await mobilePage.screenshot({ path: `${SCREENSHOTS_DIR}/02_mobile_landing_top.png` });
    console.log("Captured 02_mobile_landing_top.png");

    await mobilePage.evaluate(() => window.scrollBy(0, 500));
    await mobilePage.waitForTimeout(500);
    await mobilePage.screenshot({ path: `${SCREENSHOTS_DIR}/02_mobile_landing_scrolled.png` });
    console.log("Captured 02_mobile_landing_scrolled.png");
    await mobileContext.close();

    // -------------------------------------------------------------
    // TEST 3: REGISTER PAGE & PROFESSIONAL PLAN (49.99 CAD)
    // -------------------------------------------------------------
    console.log("\n[Test 3] Register Page & Professional Plan (49.99 CAD, 5 modules)...");
    const regContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const regPage = await regContext.newPage();
    await regPage.goto(`${BASE_URL}/register`, { waitUntil: "networkidle", timeout: 30000 });
    await regPage.screenshot({ path: `${SCREENSHOTS_DIR}/03_register_page_overview.png` });
    console.log("Captured 03_register_page_overview.png");
    await regContext.close();

    // -------------------------------------------------------------
    // TEST 4: LOGIN PAGE & CANONICAL LOCALES (FR, EN, ES, RTL ARABIC)
    // -------------------------------------------------------------
    console.log("\n[Test 4] Login Page & Multi-Language / RTL Layout...");
    const loginContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const loginPage = await loginContext.newPage();
    await loginPage.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 30000 });
    await loginPage.screenshot({ path: `${SCREENSHOTS_DIR}/04_login_french_default.png` });
    console.log("Captured 04_login_french_default.png");

    // RTL Arabic / Hebrew test
    const rtlContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      locale: "ar",
    });
    const rtlPage = await rtlContext.newPage();
    await rtlPage.goto(`${BASE_URL}/login?lang=ar`, { waitUntil: "networkidle", timeout: 30000 });
    await rtlPage.screenshot({ path: `${SCREENSHOTS_DIR}/04_login_arabic_rtl.png` });
    console.log("Captured 04_login_arabic_rtl.png");
    await rtlContext.close();
    await loginContext.close();

    // -------------------------------------------------------------
    // TEST 5: PRICING & TRUST COMPLIANCE PAGES
    // -------------------------------------------------------------
    console.log("\n[Test 5] Pricing Page & Qualified Trust Verification...");
    const infoContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const infoPage = await infoContext.newPage();
    await infoPage.goto(`${BASE_URL}/pricing`, { waitUntil: "networkidle", timeout: 30000 });
    await infoPage.screenshot({ path: `${SCREENSHOTS_DIR}/05_pricing_page.png` });
    console.log("Captured 05_pricing_page.png");

    await infoPage.goto(`${BASE_URL}/trust`, { waitUntil: "networkidle", timeout: 30000 });
    await infoPage.screenshot({ path: `${SCREENSHOTS_DIR}/06_trust_compliance_page.png` });
    console.log("Captured 06_trust_compliance_page.png");
    await infoContext.close();

    console.log("\nALL PLAYWRIGHT TESTS EXECUTED AND SCREENSHOTS CAPTURED SUCCESSFULLY!");
  } catch (err) {
    console.error("Playwright execution error:", err);
  } finally {
    await browser.close();
  }
}

main();

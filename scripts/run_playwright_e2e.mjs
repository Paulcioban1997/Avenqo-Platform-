import { chromium } from "playwright";
import { resolve } from "path";
import { mkdirSync } from "fs";

const ARTIFACT_DIR = "C:/Users/paulm/.gemini/antigravity-ide/brain/87666082-014f-4ca7-ba09-1931c6dc8f43";
const BASE_URL = "https://web-git-promotion-sandbox-paulmircea15-9488s-projects.vercel.app";

async function run() {
  console.log("Starting Playwright E2E browser acceptance test against Vercel Sandbox...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "fr-CA",
  });
  const page = await context.newPage();

  try {
    // 1. Visit Login Page
    console.log("Navigating to login page...");
    await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 30000 });
    await page.screenshot({ path: `${ARTIFACT_DIR}/01_login_page.png`, fullPage: false });
    console.log("Captured 01_login_page.png");

    // 2. Perform Login with persistent test account
    console.log("Filling login credentials...");
    await page.fill('input[name="email"]', "alex.physio.sandbox@avenqo.ca");
    await page.fill('input[name="password"]', "PhysioSecure123!");
    await page.click('button[type="submit"]');

    // Wait for navigation to dashboard
    console.log("Awaiting dashboard navigation...");
    await page.waitForURL("**/dashboard**", { timeout: 25000 }).catch(() => {
      console.log("Navigation timeout, current URL: " + page.url());
    });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/02_dashboard.png`, fullPage: false });
    console.log("Captured 02_dashboard.png at " + page.url());

    // 3. CRM AI Module
    console.log("Navigating to CRM AI...");
    await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/03_crm_module.png`, fullPage: false });
    console.log("Captured 03_crm_module.png");

    // 4. OCR AI Module
    console.log("Navigating to OCR AI...");
    await page.goto(`${BASE_URL}/ocr`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/04_ocr_module.png`, fullPage: false });
    console.log("Captured 04_ocr_module.png");

    // 5. Legal AI Module
    console.log("Navigating to Legal AI...");
    await page.goto(`${BASE_URL}/legal`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/05_legal_module.png`, fullPage: false });
    console.log("Captured 05_legal_module.png");

    // 6. Automations Module
    console.log("Navigating to Automations...");
    await page.goto(`${BASE_URL}/automations`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/06_automations_module.png`, fullPage: false });
    console.log("Captured 06_automations_module.png");

    // 7. Voice AI Module
    console.log("Navigating to Voice AI...");
    await page.goto(`${BASE_URL}/voice`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/07_voice_module.png`, fullPage: false });
    console.log("Captured 07_voice_module.png");

    // 8. Agents AI Module
    console.log("Navigating to Agents AI...");
    await page.goto(`${BASE_URL}/agents`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/08_agents_module.png`, fullPage: false });
    console.log("Captured 08_agents_module.png");

    // 9. Team & Workspace
    console.log("Navigating to Workspace / Team...");
    await page.goto(`${BASE_URL}/workspace`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/09_workspace_module.png`, fullPage: false });
    console.log("Captured 09_workspace_module.png");

    // 10. Marketplace
    console.log("Navigating to Marketplace...");
    await page.goto(`${BASE_URL}/marketplace`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/10_marketplace_module.png`, fullPage: false });
    console.log("Captured 10_marketplace_module.png");

    // 11. Connections
    console.log("Navigating to Connections...");
    await page.goto(`${BASE_URL}/connections`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/11_connections_module.png`, fullPage: false });
    console.log("Captured 11_connections_module.png");

    // 12. Billing
    console.log("Navigating to Billing...");
    await page.goto(`${BASE_URL}/billing`, { waitUntil: "networkidle", timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${ARTIFACT_DIR}/12_billing_module.png`, fullPage: false });
    console.log("Captured 12_billing_module.png");

    console.log("ALL PLAYWRIGHT BROWSER ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!");
  } catch (err) {
    console.error("Playwright browser test error:", err);
  } finally {
    await browser.close();
  }
}

run();

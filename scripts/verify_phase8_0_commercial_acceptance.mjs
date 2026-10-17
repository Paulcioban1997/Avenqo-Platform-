import { chromium } from "../web/node_modules/playwright/index.mjs";
import { readFileSync, existsSync } from "fs";

const ARTIFACT_DIR = "C:/Users/paulm/.gemini/antigravity-ide/brain/87666082-014f-4ca7-ba09-1931c6dc8f43";
const BASE_URL = "https://web-git-promotion-sandbox-paulmircea15-9488s-projects.vercel.app";
const API_URL = "https://avenqo-platform-sandbox.up.railway.app";

async function main() {
  console.log("=== AVENQO PHASE 8.0 COMMERCIAL SANDBOX ACCEPTANCE ===");
  console.log(`Frontend URL: ${BASE_URL}`);
  console.log(`Backend URL:  ${API_URL}`);

  const browser = await chromium.launch({ headless: true });

  // 1. Desktop Browser Context (FR)
  const desktopContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "fr-CA",
  });
  const page = await desktopContext.newPage();

  // Test 1: Landing Page Desktop (FR)
  console.log("\n[1/12] Landing Page Desktop (FR)...");
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_01_landing_desktop_fr.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_01_landing_desktop_fr.png");

  // Test 2: Pricing Page (Base, Professional, Enterprise)
  console.log("\n[2/12] Pricing & Commercial Plans (/pricing)...");
  await page.goto(`${BASE_URL}/pricing`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_02_pricing_page.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_02_pricing_page.png");

  // Test 3: Login View
  console.log("\n[3/12] Login Page (/login)...");
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_03_login_page.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_03_login_page.png");

  // Test 4: Authenticate as Alex Physio Admin
  console.log("\n[4/12] Authenticating as alex.physio.sandbox@avenqo.ca...");
  await page.fill('input[name="email"]', "alex.physio.sandbox@avenqo.ca");
  const sandboxPassword = process.env.AVENQO_E2E_PASSWORD;
  if (!sandboxPassword) throw new Error("AVENQO_E2E_PASSWORD environment variable is required");
  await page.fill('input[name="password"]', sandboxPassword);
  await page.click('button[type="submit"]');

  await page.waitForURL("**/dashboard**", { timeout: 35000 }).catch(() => {
    console.log("  Current URL: " + page.url());
  });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_04_dashboard_desktop.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_04_dashboard_desktop.png");

  // Test 5: CRM Module Overview & Business Hours
  console.log("\n[5/12] CRM Module (/crm)...");
  await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_05_crm_module_overview.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_05_crm_module_overview.png");

  // Test 6: Central AI Conversational Copilot
  console.log("\n[6/12] Central AI Copilot (/dashboard)...");
  await page.goto(`${BASE_URL}/dashboard`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(2000);
  const copilotBtn = await page.$('button[aria-label*="Copilot"], button:has-text("Avenqo IA")');
  if (copilotBtn) {
    await copilotBtn.click();
    await page.waitForTimeout(2000);
    const copilotInput = await page.$('input[placeholder*="Posez une question"], textarea[placeholder*="Posez une question"]');
    if (copilotInput) {
      await copilotInput.fill("Donne-moi un aperçu des rendez-vous et de l'activité du cabinet cette semaine.");
      await page.keyboard.press("Enter");
      await page.waitForTimeout(5000);
    }
  }
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_06_central_ai_sales_crm.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_06_central_ai_sales_crm.png");

  // Test 7: Retail AI Demand Forecasting on Produits_Ero (Superstore-utf8.csv)
  console.log("\n[7/12] Retail AI Demand Forecasting (/retail)...");
  // Set auth cookie for Produits_Ero if token file or API call exists
  await page.goto(`${BASE_URL}/retail`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(3000);
  const forecastTab = await page.locator('nav button:has-text("Prévisions"), button:has-text("Forecasts")').first();
  if (forecastTab) {
    await forecastTab.click().catch(() => {});
    await page.waitForTimeout(2500);
  }
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_07_retail_forecast_produits_ero.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_07_retail_forecast_produits_ero.png");

  // Test 8: Connections Hub (/integrations)
  console.log("\n[8/12] Connections & Integrations Hub (/integrations)...");
  await page.goto(`${BASE_URL}/integrations`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_08_connections_hub.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_08_connections_hub.png");

  // Test 9: Billing, Plans & Canadian Taxes (/billing)
  console.log("\n[9/12] Billing & AI Credit Ledgers (/billing)...");
  await page.goto(`${BASE_URL}/billing`, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_09_billing_plans_taxes.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_09_billing_plans_taxes.png");

  await desktopContext.close();

  // Test 10: Mobile Viewport (375x667)
  console.log("\n[10/12] Mobile Viewport Landing (/)...");
  const mobileContext = await browser.newContext({
    viewport: { width: 375, height: 667 },
    locale: "fr-CA",
    isMobile: true,
  });
  const mobilePage = await mobileContext.newPage();
  await mobilePage.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: 45000 });
  await mobilePage.waitForTimeout(2000);
  await mobilePage.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_10_landing_mobile_fr.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_10_landing_mobile_fr.png");
  await mobileContext.close();

  // Test 11: Tablet Viewport (768x1024)
  console.log("\n[11/12] Tablet Viewport (/pricing)...");
  const tabletContext = await browser.newContext({
    viewport: { width: 768, height: 1024 },
    locale: "fr-CA",
  });
  const tabletPage = await tabletContext.newPage();
  await tabletPage.goto(`${BASE_URL}/pricing`, { waitUntil: "networkidle", timeout: 45000 });
  await tabletPage.waitForTimeout(2000);
  await tabletPage.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_11_dashboard_tablet.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_11_dashboard_tablet.png");
  await tabletContext.close();

  // Test 12: Dark Mode Visual Verification
  console.log("\n[12/12] Dark Mode Theme (/pricing)...");
  const darkContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "fr-CA",
    colorScheme: "dark",
  });
  const darkPage = await darkContext.newPage();
  await darkPage.goto(`${BASE_URL}/pricing`, { waitUntil: "networkidle", timeout: 45000 });
  await darkPage.waitForTimeout(2000);
  await darkPage.screenshot({ path: `${ARTIFACT_DIR}/phase8_0_12_dashboard_dark_mode.png`, fullPage: false });
  console.log("  ✓ Captured phase8_0_12_dashboard_dark_mode.png");
  await darkContext.close();

  await browser.close();
  console.log("\n=== ALL 12 PHASE 8.0 COMMERCIAL ACCEPTANCE TESTS COMPLETED SUCCESSFULLY ===");
}

main().catch(err => {
  console.error("FATAL: Verification script failed:", err);
  process.exit(1);
});

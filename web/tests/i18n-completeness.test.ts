import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { LOCALES } from "../src/lib/i18n/locales";
import { TRANSLATIONS } from "../src/lib/i18n/dictionary";
import { getAppTranslations } from "../src/lib/i18n/app-dictionary";
import { APP_LOCALE_WORDS } from "../src/lib/i18n/app-locale-overrides";
import { APPLICATION_CATALOGS } from "../src/lib/i18n/generated-app-catalogs";
import { CANONICAL_LOCALES } from "../src/lib/i18n/canonical-locales.generated";
import { VOICE_AUTH_MESSAGES } from "../src/lib/i18n/voice-auth-messages.generated";
import { MARKETING_SURFACE_COPY } from "../src/lib/i18n/marketing-surface-copy";
import {
  VOICE_PERMISSIONS_COPY,
  VOICE_PERMISSION_ACTION_CODES,
  VOICE_PERMISSION_MODULE_CODES,
} from "../src/lib/i18n/voice-permissions-copy";
import { MODULE_PREVIEW_COPY } from "../src/lib/i18n/module-preview-copy";
import { COPILOT_CHIPS_COPY } from "../src/lib/i18n/copilot-chips-copy";
import { reconcileLoginLocale } from "../src/lib/i18n/locale-persistence";

const requiredAppPaths = [
  "navigation.dashboard",
  "navigation.crmAi",
  "navigation.accountingAi",
  "navigation.integrations",
  "navigation.settings",
  "crm.title",
  "crm.tabs.overview",
  "crm.tabs.clients",
  "crm.tabs.appointments",
  "crm.kpis.activeClients",
  "crm.kpis.appointmentsThisMonth",
  "crm.kpis.revenueGenerated",
] as const;

function readPath(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => {
    if (!current || typeof current !== "object") return undefined;
    return (current as Record<string, unknown>)[key];
  }, value);
}

function stringLeaves(value: unknown, prefix = ""): Map<string, string> {
  const leaves = new Map<string, string>();
  if (typeof value === "string") {
    leaves.set(prefix, value);
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => {
      for (const [path, text] of stringLeaves(item, `${prefix}[${index}]`)) leaves.set(path, text);
    });
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      const path = prefix ? `${prefix}.${key}` : key;
      for (const [leafPath, text] of stringLeaves(item, path)) leaves.set(leafPath, text);
    }
  }
  return leaves;
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{[A-Za-z0-9_]+\}/g)].map((match) => match[0]).sort();
}

describe("Avenqo canonical localization", () => {
  it("keeps all 44 supported locales and public catalogs aligned", () => {
    expect(LOCALES).toHaveLength(44);
    expect(Object.keys(TRANSLATIONS)).toHaveLength(44);
    expect(Object.keys(APP_LOCALE_WORDS)).toHaveLength(44);
    for (const locale of LOCALES) {
      expect(TRANSLATIONS[locale.code], locale.code).toBeDefined();
      expect(APP_LOCALE_WORDS[locale.code], locale.code).toBeDefined();
    }
    expect(CANONICAL_LOCALES).toHaveLength(44);
    expect(Object.keys(VOICE_AUTH_MESSAGES).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.values(VOICE_AUTH_MESSAGES).every(messages => messages.length === 7 && messages.every(message => message.trim()))).toBe(true);
    expect(CANONICAL_LOCALES.every(item => item.bcp47 && item.currency.length === 3 && item.timezone)).toBe(true);
  });

  it("reports 44/44 complete application catalogs with valid placeholders", () => {
    const catalogRoot = resolve(process.cwd(), "../frontend/assets/i18n");
    const english = JSON.parse(readFileSync(resolve(catalogRoot, "en.json"), "utf8"));
    const requiredSections = ["common", "auth", "company", "dashboardHome", "assistant", "admin"];
    const requiredLeaves = stringLeaves(
      Object.fromEntries(requiredSections.map((section) => [section, english[section]])),
    );

    let passed = 0;
    const errors: string[] = [];
    for (const locale of LOCALES) {
      const path = resolve(catalogRoot, `${locale.code}.json`);
      if (!existsSync(path)) {
        errors.push(`${locale.code}:catalog_missing`);
        continue;
      }
      const catalog = JSON.parse(readFileSync(path, "utf8"));
      const leaves = stringLeaves(
        Object.fromEntries(requiredSections.map((section) => [section, catalog[section]])),
      );
      for (const [leafPath, englishValue] of requiredLeaves) {
        const localized = leaves.get(leafPath);
        if (!localized?.trim()) {
          errors.push(`${locale.code}:${leafPath}:missing`);
        } else if (JSON.stringify(placeholders(localized)) !== JSON.stringify(placeholders(englishValue))) {
          errors.push(`${locale.code}:${leafPath}:invalid_placeholders`);
        }
      }
      if (!errors.some((error) => error.startsWith(`${locale.code}:`))) passed += 1;
    }
    expect(errors, errors.slice(0, 100).join("\n")).toEqual([]);
    expect(`${passed}/44 PASS`).toBe("44/44 PASS");
    console.log("44/44 PASS");
  });

  it("keeps generated Web application catalogs synchronized with all canonical JSON sources", () => {
    const catalogRoot = resolve(process.cwd(), "../frontend/assets/i18n");
    const generatedSections = ["auth", "company", "dashboardHome", "assistant", "admin", "phase4e"];
    expect(Object.keys(APPLICATION_CATALOGS)).toHaveLength(44);
    for (const locale of LOCALES) {
      const source = JSON.parse(readFileSync(resolve(catalogRoot, `${locale.code}.json`), "utf8"));
      const expected = Object.fromEntries(
        generatedSections.map((section) => [section, source[section]]),
      );
      expect(APPLICATION_CATALOGS[locale.code], locale.code).toEqual(expected);
    }
  });

  it("provides visible application values for every locale", () => {
    for (const locale of LOCALES) {
      const app = getAppTranslations(locale.code);
      for (const path of requiredAppPaths) {
        const value = readPath(app, path);
        expect(typeof value, `${locale.code}:${path}`).toBe("string");
        expect(String(value).trim(), `${locale.code}:${path}`).not.toBe("");
      }
    }
  });

  it("keeps the Romanian CRM calendar surface fully localized", () => {
    const app = getAppTranslations("ro");
    expect(app.crm.newAppointment).toBe("Programare nouă");
    expect(app.crm.kpis.attendanceRate).toBe("Rata de prezență");
    expect(app.crm.calendar).toMatchObject({
      today: "Astăzi",
      week: "Săptămână",
      month: "Lună",
      list: "Listă",
      allServices: "Toate serviciile",
      allEmployees: "Toți angajații",
      allStatuses: "Toate stările",
      noAppointments: "Nicio programare",
    });
  });

  it("uses canonical backend state for Google integrations and dashboard trends", () => {
    const integrations = readFileSync(
      resolve(process.cwd(), "src/components/integrations/integrations-hub-view.tsx"),
      "utf8",
    );
    const dashboard = readFileSync(
      resolve(process.cwd(), "src/components/dashboard/dashboard-view.tsx"),
      "utf8",
    );
    expect(integrations).toContain('/api/v1/crm/calendar/connection');
    expect(dashboard).toContain("data.trend?.points");
    expect(dashboard).not.toContain("/api/v1/sales/summary");
  });

  it("keeps voicePermissions and marketing surface strings for all 44 locales", () => {
    const voiceRequired = ["title", "description", "locked", "moduleOff"] as const;
    const marketingRequired = [
      "kpiAudience", "kpiCampaigns", "kpiConversion", "kpiRoi",
      "draftTitle", "draftSubject", "draftChannel", "draftSegment", "draftContent",
      "activate", "activationHint",
    ] as const;
    expect(Object.keys(VOICE_PERMISSIONS_COPY)).toHaveLength(44);
    expect(Object.keys(MARKETING_SURFACE_COPY)).toHaveLength(44);
    expect(Object.keys(MODULE_PREVIEW_COPY)).toHaveLength(44);
    expect(Object.keys(COPILOT_CHIPS_COPY)).toHaveLength(44);
    for (const locale of LOCALES) {
      for (const key of voiceRequired) {
        expect(VOICE_PERMISSIONS_COPY[locale.code][key].trim(), `${locale.code}:voice.${key}`).not.toBe("");
      }
      for (const key of marketingRequired) {
        expect(MARKETING_SURFACE_COPY[locale.code][key].trim(), `${locale.code}:marketing.${key}`).not.toBe("");
      }
    }
  });

  it("keeps Voice permission action_code and module_code enums unchanged", () => {
    const permissionsUi = readFileSync(
      resolve(process.cwd(), "src/components/settings/voice-module-permissions.tsx"),
      "utf8",
    );
    expect(VOICE_PERMISSION_ACTION_CODES).toEqual([
      "read_availability", "list_slots", "create_appointment", "update_appointment",
      "cancel_appointment", "read_client_self", "read_crm_metrics", "read_sales_summary",
      "read_products", "read_inventory", "read_unpaid_invoices", "read_cashflow",
      "read_documents", "read", "read_business_health",
    ]);
    expect(VOICE_PERMISSION_MODULE_CODES).toEqual([
      "crm", "retail", "accounting", "ocr", "marketing", "appointments",
      "hr", "media", "legal", "workflow", "ai_agents", "cross_agent",
    ]);
    expect(permissionsUi).toContain("value={action.action_code}");
    expect(permissionsUi).toContain("module.module_code");
    expect(permissionsUi).toContain("action.action_code");
    expect(permissionsUi).not.toMatch(/value=\{copy\./);
  });

  it("reconciles login locale with company preferred_language unless the client changed it this session", () => {
    expect(reconcileLoginLocale("ro", "fr", false)).toEqual({ locale: "ro", persistCompany: false });
    expect(reconcileLoginLocale("en", "ja", true)).toEqual({ locale: "ja", persistCompany: true });
    expect(reconcileLoginLocale(null, "fr", false)).toEqual({ locale: "fr", persistCompany: false });
    expect(reconcileLoginLocale("pt-BR", "fr", false)).toEqual({ locale: "pt", persistCompany: false });
  });
});

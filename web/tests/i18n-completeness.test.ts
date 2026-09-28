import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { LOCALES } from "../src/lib/i18n/locales";
import { TRANSLATIONS } from "../src/lib/i18n/dictionary";
import { getAppTranslations } from "../src/lib/i18n/app-dictionary";
import { APP_LOCALE_WORDS } from "../src/lib/i18n/app-locale-overrides";
import { APPLICATION_CATALOGS } from "../src/lib/i18n/generated-app-catalogs";

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
});

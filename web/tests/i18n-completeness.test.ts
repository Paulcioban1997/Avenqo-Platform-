import { describe, expect, it } from "vitest";
import { LOCALES } from "../src/lib/i18n/locales";
import { TRANSLATIONS } from "../src/lib/i18n/dictionary";
import { getAppTranslations } from "../src/lib/i18n/app-dictionary";
import { APP_LOCALE_WORDS } from "../src/lib/i18n/app-locale-overrides";

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
});

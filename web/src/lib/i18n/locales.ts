import type { LocaleCode, RegionCode } from "./types";
import { CANONICAL_LOCALES } from "./canonical-locales.generated";

/** Régions affichées dans le sélecteur, façon Salesforce : région puis langues disponibles. */
export const REGIONS: { code: RegionCode; label: Record<"fr" | "en", string> }[] = [
  { code: "americas", label: { fr: "Amériques", en: "Americas" } },
  { code: "europe", label: { fr: "Europe", en: "Europe" } },
  { code: "middle-east-africa", label: { fr: "Moyen-Orient et Afrique", en: "Middle East & Africa" } },
  { code: "asia-pacific", label: { fr: "Asie-Pacifique", en: "Asia-Pacific" } },
];
export const LOCALES = CANONICAL_LOCALES;
export const DEFAULT_LOCALE = "fr" as const;

const LOCALE_ALIASES: Record<string, string> = {
  "fr-ca": "fr",
  "en-us": "en",
  "es-es": "es",
  "es-419": "es",
  "es-latam": "es",
  "pt-pt": "pt",
  "pt-br": "pt",
};

export function resolveLocaleCode(raw: string | null | undefined): LocaleCode {
  const normalized = (raw ?? "").trim().replaceAll("_", "-").toLowerCase();
  const candidate = LOCALE_ALIASES[normalized] ?? normalized;
  return (LOCALES.find((locale) => locale.code.toLowerCase() === candidate)?.code ?? DEFAULT_LOCALE) as LocaleCode;
}

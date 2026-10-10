import { CANONICAL_LOCALES } from "./canonical-locales.generated";
import type { LocaleCode } from "./types";

/**
 * Tarification de référence Avenqo (PMC Solutions AI).
 * L'entreprise étant établie au Canada (Québec), les tarifs de référence officiels sont en CAD :
 * - Offre Base : 29,99 $ CAD / mois
 * - Offre Professional : 49,99 $ CAD / mois
 * - Offre Enterprise : Sur devis (Custom)
 *
 * Pour chaque entreprise internationale, le prix affiché est converti et formaté
 * dans sa devise locale (38 devises pour les 44 langues/régions de la plateforme)
 * avec rappel de la facturation de référence en CAD.
 */

export const CANONICAL_CAD_PRICES = {
  base: 29.99,
  professional: 49.99,
} as const;

/**
 * Taux de conversion indicatifs pivots par rapport au CAD (1 CAD = X devise).
 */
export const CAD_EXCHANGE_RATES: Record<string, number> = {
  CAD: 1.0,
  USD: 0.733,
  EUR: 0.672,
  GBP: 0.581,
  CHF: 0.648,
  JPY: 112.5,
  AUD: 1.132,
  BRL: 4.15,
  CNY: 5.32,
  INR: 61.8,
  MXN: 14.65,
  SEK: 7.72,
  PLN: 2.89,
  RON: 3.34,
  CZK: 16.95,
  TRY: 25.1,
  RUB: 68.2,
  UAH: 30.5,
  ILS: 2.76,
  SAR: 2.75,
  AED: 2.69,
  EGP: 35.8,
  NGN: 1180.0,
  ZAR: 13.2,
  KES: 95.0,
  ETB: 88.5,
  AMD: 285.0,
  BDT: 87.5,
  GEL: 1.98,
  IDR: 11500.0,
  IRR: 31000.0,
  KHR: 2980.0,
  KRW: 1015.0,
  LKR: 222.0,
  MMK: 1540.0,
  MNT: 2520.0,
  MYR: 3.25,
  NPR: 98.2,
  PHP: 42.1,
  PKR: 204.0,
  THB: 24.8,
  VND: 18500.0,
};

export interface LocalizedPlanPrice {
  plan: "base" | "professional";
  cadAmount: number;
  localAmount: number;
  currencyCode: string;
  formatted: string;
  cadFormatted: string;
  isCad: boolean;
  conversionNote: string;
}

export function getLocalizedPlanPrice(
  plan: "base" | "professional",
  localeCode: LocaleCode
): LocalizedPlanPrice {
  const localeDef =
    CANONICAL_LOCALES.find((loc) => loc.code === localeCode) ??
    CANONICAL_LOCALES[0];

  const currencyCode = localeDef.currency || "CAD";
  const cadAmount = CANONICAL_CAD_PRICES[plan];
  const rate = CAD_EXCHANGE_RATES[currencyCode] ?? 1.0;
  const isCad = currencyCode === "CAD";

  // Arrondi commercial harmonieux selon la devise
  let localAmount: number;
  if (isCad) {
    localAmount = cadAmount;
  } else if (currencyCode === "USD") {
    localAmount = plan === "base" ? 21.99 : 36.99;
  } else if (currencyCode === "EUR") {
    localAmount = plan === "base" ? 19.99 : 33.99;
  } else if (currencyCode === "GBP") {
    localAmount = plan === "base" ? 17.49 : 28.99;
  } else if (rate >= 100) {
    // Devises sans décimales ou à grand volume (ex: JPY, KRW, VND)
    localAmount = Math.round((cadAmount * rate) / 10) * 10;
  } else {
    // Calcul standard avec 2 décimales
    localAmount = Math.round(cadAmount * rate * 100) / 100;
  }

  // Formatage monétaire selon la locale de l'utilisateur
  const fractions = rate >= 100 ? 0 : 2;
  const formatter = new Intl.NumberFormat(localeDef.bcp47, {
    style: "currency",
    currency: currencyCode,
    minimumFractionDigits: fractions,
    maximumFractionDigits: fractions,
  });

  const cadFormatter = new Intl.NumberFormat(
    localeCode === "en" ? "en-CA" : "fr-CA",
    {
      style: "currency",
      currency: "CAD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }
  );

  const formatted = formatter.format(localAmount);
  const cadFormatted = cadFormatter.format(cadAmount);

  const isFrench = localeCode === "fr" || localeCode === "fr-FR";
  const conversionNote = isCad
    ? isFrench
      ? "Tarif officiel canadien"
      : "Official Canadian pricing"
    : isFrench
    ? `≈ réf. ${cadFormatted} (PMC Solutions AI)`
    : `≈ ref. ${cadFormatted} (PMC Solutions AI)`;

  return {
    plan,
    cadAmount,
    localAmount,
    currencyCode,
    formatted,
    cadFormatted,
    isCad,
    conversionNote,
  };
}

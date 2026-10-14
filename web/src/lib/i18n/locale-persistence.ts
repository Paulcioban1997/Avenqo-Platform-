import type { LocaleCode } from "./types";
import { resolveLocaleCode } from "./locales";

export const LOCALE_STORAGE_KEY = "avenqo-locale";
export const LOCALE_EXPLICIT_SESSION_KEY = "avenqo-locale-explicit";

export function hasExplicitLocaleThisSession(): boolean {
  try {
    return window.sessionStorage.getItem(LOCALE_EXPLICIT_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markExplicitLocaleThisSession(): void {
  try {
    window.sessionStorage.setItem(LOCALE_EXPLICIT_SESSION_KEY, "1");
  } catch {
    // sessionStorage can be unavailable in restricted test environments
  }
}

export function persistBrowserLocale(locale: LocaleCode): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // localStorage can be unavailable in restricted test environments
  }
}

export function readStoredLocale(): string | null {
  try {
    return window.localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** After login: an explicit change this session wins; otherwise use company preferred_language. */
export function reconcileLoginLocale(
  companyPreferred: string | null | undefined,
  currentLocale: LocaleCode,
  explicitThisSession = hasExplicitLocaleThisSession(),
): { locale: LocaleCode; persistCompany: boolean } {
  if (explicitThisSession) {
    return { locale: currentLocale, persistCompany: true };
  }
  if (companyPreferred?.trim()) {
    return { locale: resolveLocaleCode(companyPreferred), persistCompany: false };
  }
  return { locale: currentLocale, persistCompany: false };
}

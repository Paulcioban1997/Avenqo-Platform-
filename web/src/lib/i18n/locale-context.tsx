"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { LocaleCode } from "./types";
import { DEFAULT_LOCALE, LOCALES, resolveLocaleCode } from "./locales";
import { getTranslations } from "./dictionary";
import {
  LOCALE_STORAGE_KEY,
  hasExplicitLocaleThisSession,
  markExplicitLocaleThisSession,
  persistBrowserLocale,
  readStoredLocale,
} from "./locale-persistence";

type LocaleContextValue = {
  locale: LocaleCode;
  setLocale: (locale: LocaleCode, options?: { explicit?: boolean }) => void;
  applyCompanyLocale: (preferred: string | null | undefined) => void;
  t: ReturnType<typeof getTranslations>;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function applyDocumentAttributes(locale: LocaleCode) {
  const definition = LOCALES.find((entry) => entry.code === locale);
  if (!definition) return;
  document.documentElement.lang = locale;
  document.documentElement.dir = definition.direction;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${LOCALE_STORAGE_KEY}=${encodeURIComponent(locale)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(DEFAULT_LOCALE);

  const commitLocale = useCallback((next: LocaleCode) => {
    const resolved = resolveLocaleCode(next);
    setLocaleState(resolved);
    persistBrowserLocale(resolved);
    applyDocumentAttributes(resolved);
    return resolved;
  }, []);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const queryParam = params.get("lang") || params.get("locale");
      if (queryParam) {
        markExplicitLocaleThisSession();
        commitLocale(resolveLocaleCode(queryParam));
        return;
      }
    } catch {
      // Ignored in environments where window/URLSearchParams is restricted
    }

    const stored = readStoredLocale();
    if (stored) {
      commitLocale(resolveLocaleCode(stored));
    } else {
      applyDocumentAttributes(DEFAULT_LOCALE);
    }
  }, [commitLocale]);

  useEffect(() => {
    function onCompanyPreferred(event: Event) {
      const preferred = (event as CustomEvent<string>).detail;
      if (hasExplicitLocaleThisSession() || !preferred?.trim()) return;
      commitLocale(resolveLocaleCode(preferred));
    }
    window.addEventListener("avenqo:company-preferred-language", onCompanyPreferred);
    return () => window.removeEventListener("avenqo:company-preferred-language", onCompanyPreferred);
  }, [commitLocale]);

  const setLocale = useCallback((next: LocaleCode, options?: { explicit?: boolean }) => {
    if (options?.explicit !== false) markExplicitLocaleThisSession();
    commitLocale(next);
  }, [commitLocale]);

  const applyCompanyLocale = useCallback((preferred: string | null | undefined) => {
    if (hasExplicitLocaleThisSession() || !preferred?.trim()) return;
    commitLocale(resolveLocaleCode(preferred));
  }, [commitLocale]);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, applyCompanyLocale, t: getTranslations(locale) }),
    [locale, setLocale, applyCompanyLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

function useLocaleContext(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale/useTranslations must be used within a LocaleProvider");
  }
  return context;
}

/** Locale active + setter pour la changer instantanément (persistée en localStorage). */
export function useLocale() {
  const { locale, setLocale, applyCompanyLocale } = useLocaleContext();
  return { locale, setLocale, applyCompanyLocale };
}

/** Objet de traductions complet pour la locale active. */
export function useTranslations(): ReturnType<typeof getTranslations> {
  return useLocaleContext().t;
}

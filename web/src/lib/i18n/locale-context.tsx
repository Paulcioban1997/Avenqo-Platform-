"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { LocaleCode, Translations } from "./types";
import { DEFAULT_LOCALE, LOCALES, resolveLocaleCode } from "./locales";
import { getTranslations } from "./dictionary";

const STORAGE_KEY = "avenqo-locale";

type LocaleContextValue = {
  locale: LocaleCode;
  setLocale: (locale: LocaleCode) => void;
  t: Translations;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function applyDocumentAttributes(locale: LocaleCode) {
  const definition = LOCALES.find((entry) => entry.code === locale);
  if (!definition) return;
  document.documentElement.lang = locale;
  document.documentElement.dir = definition.direction;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${STORAGE_KEY}=${encodeURIComponent(locale)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(DEFAULT_LOCALE);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const queryParam = params.get("lang") || params.get("locale");
      if (queryParam) {
        const resolved = resolveLocaleCode(queryParam);
        setLocaleState(resolved);
        window.localStorage.setItem(STORAGE_KEY, resolved);
        applyDocumentAttributes(resolved);
        return;
      }
    } catch {
      // Ignored in environments where window/URLSearchParams is restricted
    }

    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const resolved = resolveLocaleCode(stored);
      setLocaleState(resolved);
      applyDocumentAttributes(resolved);
    } else {
      applyDocumentAttributes(DEFAULT_LOCALE);
    }
  }, []);

  const setLocale = useCallback((next: LocaleCode) => {
    const resolved = resolveLocaleCode(next);
    setLocaleState(resolved);
    window.localStorage.setItem(STORAGE_KEY, resolved);
    applyDocumentAttributes(resolved);
  }, []);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t: getTranslations(locale) }),
    [locale, setLocale],
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
  const { locale, setLocale } = useLocaleContext();
  return { locale, setLocale };
}

/** Objet de traductions complet pour la locale active. */
export function useTranslations(): Translations {
  return useLocaleContext().t;
}

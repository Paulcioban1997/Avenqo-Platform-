"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { LocaleCode, Translations } from "./types";
import { DEFAULT_LOCALE, LOCALES } from "./locales";
import { getTranslations } from "./dictionary";

const STORAGE_KEY = "avenqo-locale";

type LocaleContextValue = {
  locale: LocaleCode;
  setLocale: (locale: LocaleCode) => void;
  t: Translations;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function isLocaleCode(value: string | null): value is LocaleCode {
  return !!value && LOCALES.some((entry) => entry.code === value);
}

function applyDocumentAttributes(locale: LocaleCode) {
  const definition = LOCALES.find((entry) => entry.code === locale);
  if (!definition) return;
  document.documentElement.lang = locale;
  document.documentElement.dir = definition.direction;
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(DEFAULT_LOCALE);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocaleCode(stored)) {
      setLocaleState(stored);
      applyDocumentAttributes(stored);
    } else {
      applyDocumentAttributes(DEFAULT_LOCALE);
    }
  }, []);

  const setLocale = useCallback((next: LocaleCode) => {
    setLocaleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyDocumentAttributes(next);
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

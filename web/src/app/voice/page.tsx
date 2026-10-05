"use client";

import { AppShell } from "@/components/shell/app-shell";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

export default function VoicePage() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  return (
    <AppShell>
      <main className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">
          {t.navigation.voiceAi}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
          {t.copilot.subtitle}
        </p>
      </main>
    </AppShell>
  );
}

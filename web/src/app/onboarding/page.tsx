"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { AppShell } from "@/components/shell/app-shell";

interface Entitlements {
  plan_code: string;
  subscription_status: string;
  module_limit: number | null;
  active_modules: string[];
  modules: { key: string; display_name: string; state: string }[];
}

export default function OnboardingPage() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const [data, setData] = useState<Entitlements | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(async () => {
      try {
        const response = await fetch("/api/v1/modules/entitlements", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("entitlements_unavailable");
        const result = await response.json();
        if (!controller.signal.aborted) setData(result);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    });
    return () => controller.abort();
  }, []);

  const voiceActive = data?.active_modules.includes("voice") ?? false;

  return <AppShell><main className="mx-auto w-full max-w-4xl space-y-6 px-5 py-8 sm:px-8">
    <header className="border-b border-slate-200 pb-5 dark:border-white/10">
      <h1 className="text-xl font-bold">{t.shell.workspace}</h1>
      {data && <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{data.plan_code} · {data.subscription_status} · {data.module_limit ?? "∞"}</p>}
    </header>
    {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{t.integrations.statusNeedsAttention}</p>}
    {!data && !error && <p role="status" className="text-sm">{t.common.retry}</p>}
    {data && <>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">{t.navigation.agentsAi}</h2>
        <ul className="divide-y divide-slate-200 dark:divide-white/10">
          {data.modules.map(module => <li key={module.key} className="flex justify-between gap-4 py-3 text-sm">
            <span>{module.display_name}</span><span className="text-slate-500">{module.state}</span>
          </li>)}
        </ul>
      </section>
      <nav className="flex flex-wrap gap-4 border-t border-slate-200 pt-5 dark:border-white/10">
        <Link className="inline-flex items-center rounded border border-slate-300 px-4 py-2 text-sm font-semibold dark:border-white/20" href={voiceActive ? "/voice" : "/dashboard"}>
          {voiceActive ? t.navigation.voiceAi : t.navigation.dashboard}
        </Link>
        <Link className="inline-flex items-center px-2 py-2 text-sm underline" href="/settings">{t.navigation.settings}</Link>
      </nav>
    </>}
  </main></AppShell>;
}
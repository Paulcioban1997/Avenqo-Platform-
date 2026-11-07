"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";

export type ModuleEntitlement = { key: string; display_name: string; active: boolean; state: string; availability: string };
export type Entitlements = { modules: ModuleEntitlement[]; module_limit: number | null; active_modules: string[]; plan_code: string };
const names: Record<string, string> = { crm: "CRM IA", voice: "Voice IA", retail: "Retail IA", accounting: "Comptabilité IA", marketing: "Marketing IA", ocr: "OCR IA" };

export function ModulesView() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const company = useSession().identity?.company.id;
  const [data, setData] = useState<Entitlements | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    apiFetch("/api/v1/modules/entitlements").then(r => r.json()).then(d => { if (active) { setData(d); setError(false); } }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [company, attempt]);
  return <div className="mx-auto max-w-6xl space-y-6">
    <div><p className="text-xs font-semibold uppercase tracking-widest text-cyan-600 dark:text-cyan-300">Avenqo</p>
      <h1 className="mt-2 text-3xl font-bold">{fr ? "Mes modules" : "My modules"}</h1>
      <p className="mt-3 text-sm text-slate-500">{fr ? "Six modules sélectionnables. IA Central est inclus comme orchestrateur transversal." : "Six selectable modules. Central AI is included as your cross-module orchestrator."}</p></div>
    {error ? <div role="alert" className="rounded-xl border border-rose-400 p-4">{fr ? "Les autorisations n’ont pas pu être chargées." : "Permissions could not be loaded."}<button className="ml-3 underline" onClick={() => setAttempt(a => a + 1)}>{fr ? "Réessayer" : "Retry"}</button></div>
      : !data ? <p role="status">{fr ? "Chargement…" : "Loading…"}</p> : <>
        <p className="text-sm">{data.active_modules.length} / {data.module_limit ?? (fr ? "selon contrat" : "per contract")} {fr ? "modules sélectionnés" : "selected modules"} · <span className="capitalize">{data.plan_code}</span></p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.modules.filter(m => m.key in names).map(m => <section key={m.key} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-[#0B132B]">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">{fr ? names[m.key] ?? m.display_name : m.display_name}</h2>
            <span className={`rounded-full px-3 py-1 text-xs ${m.active ? "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300" : "bg-slate-500/10 text-slate-500"}`}>{m.active ? (fr ? "Actif" : "Active") : m.state === "available" ? (fr ? "Disponible" : "Available") : (fr ? "Non inclus" : "Not included")}</span></div>
          <p className="my-4 flex-1 text-sm text-slate-500">{m.active ? (fr ? "L’accès dépend aussi de votre rôle et de l’état de votre abonnement." : "Access also depends on your role and subscription status.") : (fr ? "Ce module est visible à titre informatif. Son utilisation nécessite une sélection autorisée." : "This module is shown for information. Using it requires an authorized selection.")}</p>
          <Link href={m.active ? `/${m.key}` : "/settings"} className="rounded-xl border border-blue-500/30 px-4 py-2 text-center text-sm font-semibold text-blue-600 dark:text-cyan-300">{m.active ? (fr ? "Ouvrir le module" : "Open module") : (fr ? "Gérer ma sélection" : "Manage selection")}</Link>
        </section>)}</div>
        <p className="text-sm text-slate-500">{fr ? "Base inclut exactement 2 modules ; Professional en inclut exactement 5. Les capacités Enterprise sont définies par contrat." : "Base includes exactly 2 modules; Professional includes exactly 5. Enterprise capacity is defined by contract."}</p>
      </>}
  </div>;
}

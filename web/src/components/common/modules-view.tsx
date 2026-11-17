"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";

type ModuleRow = {
  key: string;
  display_name: string;
  description: string;
  active: boolean;
  state: string;
  availability: string;
  category: string;
};
type Entitlements = {
  modules: ModuleRow[];
  module_limit: number | null;
  active_modules: string[];
  plan_code: string;
};

const PATHS: Record<string, string> = {
  retail: "/retail",
  crm: "/crm",
  accounting: "/accounting",
  marketing: "/marketing",
  voice: "/voice",
  ocr: "/ocr",
  legal: "/legal",
  trading: "/trading",
  workflow: "/automations",
  media: "/marketing",
  ai_agents: "/workspace/modules",
};

const DISPLAY_CURRENCIES = ["CAD", "USD", "EUR", "GBP", "CHF", "AUD", "JPY", "MXN", "NZD", "SEK", "NOK", "DKK"];

function plainName(value: string) {
  return value.replace(/\s+(AI|IA|KI)$/i, "").replace(/^(AI|IA)\s+/i, "").trim();
}

export function ModulesView() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const identity = useSession().identity;
  const permissions = identity?.user.permissions ?? [];
  const canManage = permissions.includes("modules:manage");
  const canSetCurrency = permissions.includes("company:manage") || permissions.includes("billing:manage");
  const [data, setData] = useState<Entitlements | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [displayCurrency, setDisplayCurrency] = useState("");

  const load = async () => {
    const response = await apiFetch("/api/v1/modules/entitlements");
    if (!response.ok) {
      setError(fr ? "Les modules n'ont pas pu être chargés." : "Modules could not be loaded.");
      return;
    }
    setData(await response.json());
    setError("");
    const account = await apiFetch("/api/v1/auth/me");
    if (account.ok) {
      const body = await account.json();
      setDisplayCurrency(body.company?.display_currency || "");
    }
  };

  useEffect(() => { void load(); }, [identity?.company.id]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.modules ?? []).filter((item) => item.availability === "available").filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (status === "active" && !item.active) return false;
      if (status === "available" && item.active) return false;
      if (!needle) return true;
      return plainName(item.display_name).toLowerCase().includes(needle) || item.key.includes(needle);
    });
  }, [data, query, category, status]);

  const categories = useMemo(() => Array.from(new Set((data?.modules ?? []).filter((item) => item.availability === "available").map((item) => item.category))), [data]);

  const toggle = async (key: string, active: boolean) => {
    setBusy(key);
    setError("");
    const response = await apiFetch(`/api/v1/modules/${key}/${active ? "deactivate" : "activate"}`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    setBusy("");
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : (fr ? "La limite du forfait est atteinte. Bloquez d'abord un module." : "Plan limit reached. Block a module first."));
      return;
    }
    setData(body);
  };

  const saveCurrency = async (next: string) => {
    setDisplayCurrency(next);
    const response = await apiFetch("/api/v1/auth/display-currency", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_currency: next || null }),
    });
    if (!response.ok) setError(fr ? "La devise d'affichage n'a pas été enregistrée." : "Display currency was not saved.");
  };

  return <div className="mx-auto max-w-6xl space-y-6">
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-cyan-600 dark:text-cyan-300">Avenqo Central</p>
      <h1 className="mt-2 text-3xl font-bold">{fr ? "Modules" : "Modules"}</h1>
      <p className="mt-3 max-w-3xl text-sm text-slate-500">
        {fr
          ? "Base : 2 modules maximum. Professional : 5 modules maximum. Avenqo Central est inclus et ne prend pas de place. Trading compte pour une place."
          : "Base: 2 modules maximum. Professional: 5 modules maximum. Avenqo Central is included and does not use a slot. Trading uses one slot."}
      </p>
    </div>
    {data && <p className="text-sm">{data.active_modules.length} / {data.module_limit ?? (fr ? "selon contrat" : "per contract")} · <span className="capitalize">{data.plan_code}</span></p>}
    {error && <p role="alert" className="rounded-xl border border-rose-400 p-4 text-sm text-rose-600">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={fr ? "Rechercher un module" : "Search a module"} className="rounded-xl border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-white/10" />
      <select value={category} onChange={(event) => setCategory(event.target.value)} className="rounded-xl border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-white/10">
        <option value="all">{fr ? "Toutes les catégories" : "All categories"}</option>
        {categories.map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
      <select value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-xl border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-white/10">
        <option value="all">{fr ? "Tous les états" : "All statuses"}</option>
        <option value="active">{fr ? "Actifs" : "Active"}</option>
        <option value="available">{fr ? "Disponibles" : "Available"}</option>
      </select>
      {canSetCurrency && <label className="flex items-center gap-2 text-sm">
        <span>{fr ? "Devise d'affichage" : "Display currency"}</span>
        <select value={displayCurrency} onChange={(event) => { void saveCurrency(event.target.value); }} className="rounded-xl border border-slate-200 bg-transparent px-3 py-2 dark:border-white/10">
          <option value="">{fr ? "Aucune conversion" : "No conversion"}</option>
          {DISPLAY_CURRENCIES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>}
    </div>
    {!data ? <p role="status">{fr ? "Chargement…" : "Loading…"}</p> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {visible.map((item) => <section key={item.key} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-[#0B132B]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{plainName(item.display_name)}</h2>
          <span className={`rounded-full px-3 py-1 text-xs ${item.active ? "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300" : "bg-slate-500/10 text-slate-500"}`}>{item.active ? (fr ? "Actif" : "Active") : (fr ? "Disponible" : "Available")}</span>
        </div>
        <p className="mt-1 text-xs uppercase text-slate-400">{item.category}</p>
        <p className="my-4 flex-1 text-sm text-slate-500">{item.description}</p>
        <div className="flex flex-wrap gap-2">
          {item.active && PATHS[item.key] && <Link href={PATHS[item.key]} className="rounded-xl border border-blue-500/30 px-4 py-2 text-sm font-semibold text-blue-600 dark:text-cyan-300">{fr ? "Ouvrir" : "Open"}</Link>}
          {canManage && <button type="button" disabled={busy === item.key} onClick={() => void toggle(item.key, item.active)} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white dark:bg-white dark:text-slate-900">
            {item.active ? (fr ? "Bloquer" : "Block") : (fr ? "Activer" : "Activate")}
          </button>}
        </div>
      </section>)}
    </div>}
  </div>;
}

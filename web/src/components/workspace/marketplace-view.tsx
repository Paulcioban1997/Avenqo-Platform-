"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

type Item = { key: string; name?: string; display_name?: string; availability: string; category: string; installable?: boolean; route?: string | null };

export function MarketplaceView() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [catalog, setCatalog] = useState<{ modules: Item[]; connectors: Item[] } | null>(null);

  useEffect(() => {
    void apiFetch("/api/v1/marketplace").then(async (response) => {
      if (response.ok) setCatalog(await response.json());
    });
  }, []);

  if (!catalog) return <p className="p-6 text-sm">{fr ? "Chargement du catalogue…" : "Loading catalog…"}</p>;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <h1 className="text-3xl font-bold">{fr ? "Marketplace Avenqo" : "Avenqo Marketplace"}</h1>
      <p className="text-sm text-slate-500">{fr ? "Seules les intégrations réellement opérationnelles sont marquées disponibles." : "Only integrations that actually work are marked available."}</p>
      <section>
        <h2 className="mb-3 text-lg font-semibold">{fr ? "Modules" : "Modules"}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {catalog.modules.map((item) => (
            <article key={item.key} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
              <p className="font-semibold">{item.name || item.key}</p>
              <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{item.availability === "available" ? (fr ? "Disponible" : "Available") : (fr ? "Bientôt" : "Coming soon")}</p>
              {item.installable && <Link href="/settings" className="mt-3 inline-block text-sm text-blue-600 underline">{fr ? "Gérer l’activation" : "Manage activation"}</Link>}
            </article>
          ))}
        </div>
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">{fr ? "Connecteurs" : "Connectors"}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {catalog.connectors.map((item) => (
            <article key={item.key} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-[#0B132B]">
              <p className="font-semibold">{item.name}</p>
              <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{item.availability === "available" ? (fr ? "Disponible" : "Available") : (fr ? "Bientôt" : "Coming soon")}</p>
              {item.route && <Link href={item.route} className="mt-3 inline-block text-sm text-blue-600 underline">{fr ? "Configurer" : "Configure"}</Link>}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

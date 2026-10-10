"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

export default function AgentsPage() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [data, setData] = useState<{ agents: { slug: string; name_key: string }[]; unavailable_agents: { slug: string }[] } | null>(null);

  useEffect(() => {
    void apiFetch("/api/v1/agents").then(async (response) => {
      if (response.ok) setData(await response.json());
    });
  }, []);

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-3xl font-bold">{fr ? "Agents IA implémentés" : "Implemented AI agents"}</h1>
        <p className="text-sm text-slate-500">{fr ? "Catalogue réel des assistants enregistrés. Aucun agent fictif n’est annoncé comme disponible." : "Real catalog of registered assistants. No fictional agent is advertised as available."}</p>
        <ul className="space-y-3">
          {(data?.agents || []).map((agent) => (
            <li key={agent.slug} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-[#0B132B]">
              <p className="font-semibold">{agent.slug}</p>
              <p className="text-xs text-slate-500">{agent.name_key}</p>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  );
}

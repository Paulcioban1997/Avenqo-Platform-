"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { useSession } from "@/lib/session-context";

type Workflow = { id: string; name: string; trigger_type: string; action_type: string; last_status: string | null };

export default function AutomationsPage() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const { identity } = useSession();
  const [rows, setRows] = useState<Workflow[]>([]);
  const [name, setName] = useState("Suivi client");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const response = await apiFetch("/api/v1/automations");
    if (!response.ok) {
      setError(fr ? "Activez le module Workflow Automation pour utiliser ce moteur." : "Activate Workflow Automation to use this engine.");
      return;
    }
    setRows(await response.json());
    setError("");
  }, [fr]);

  useEffect(() => { void load(); }, [load]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    const response = await apiFetch("/api/v1/automations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        trigger_type: "manual",
        action_type: "create_task",
        action: { title: name, assignee_user_id: identity?.user.id },
      }),
    });
    if (!response.ok) setError(fr ? "Création refusée." : "Creation rejected.");
    else await load();
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-3xl font-bold">{fr ? "Automatisations" : "Automations"}</h1>
        {error && <p className="text-sm text-rose-500">{error}</p>}
        <form onSubmit={create} className="flex gap-2">
          <input className="flex-1 rounded-xl border bg-transparent px-3 py-2" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="rounded-xl bg-blue-600 px-4 text-sm text-white">{fr ? "Créer" : "Create"}</button>
        </form>
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.id} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 text-sm dark:border-white/10 dark:bg-[#0B132B]">
              <span>{row.name} · {row.trigger_type} → {row.action_type}</span>
              <button className="text-cyan-600" onClick={() => void apiFetch(`/api/v1/automations/${row.id}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idempotency_key: `${row.id}-${Date.now()}` }) }).then(load)}>
                {fr ? "Exécuter" : "Run"}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  );
}

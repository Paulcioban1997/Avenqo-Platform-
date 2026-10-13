"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/lib/i18n/locale-context";

type Policy = {
  max_call_seconds: number | null; idle_seconds: number; concurrent_calls: number;
  call_budget_usd: string; monthly_budget_usd: string; monthly_minutes: number;
  alert_percent: number; auth_seconds: number;
};
type Limits = { policy: Policy; enabled: boolean; plan_duration_seconds: number | null;
  plan_concurrent_calls: number | null; auth_max_seconds: number; cost_rate_configured: boolean };
const copy = {
  fr: { title: "Durée et dépenses des appels", minutes: "Durée maximale (minutes)", unlimited: "Sans durée fixe, dans les limites du budget", idle: "Arrêt après silence (secondes)", concurrent: "Appels simultanés", call: "Budget fournisseur par appel (USD)", month: "Budget fournisseur mensuel (USD)", monthlyMinutes: "Minutes réservables par mois", alert: "Alerte à (%)", auth: "Validité du NIP (minutes)", save: "Enregistrer", saved: "Limites enregistrées.", error: "Impossible de charger ou enregistrer les limites.", off: "Les appels longs ne sont pas encore activés.", costs: "Ces budgets fournisseur sont en USD. Ils ne constituent pas un prix facturé au client. Les réservations sont conservées tant que le coût final n’est pas confirmé. L’arrêt côté application ne garantit pas un plafond strict chez les fournisseurs.", missing: "Le tarif de sécurité doit être vérifié par Avenqo avant activation." },
  en: { title: "Call duration and spending", minutes: "Maximum duration (minutes)", unlimited: "No fixed duration, within spending allowance", idle: "Stop after silence (seconds)", concurrent: "Concurrent calls", call: "Provider budget per call (USD)", month: "Monthly provider budget (USD)", monthlyMinutes: "Reservable minutes per month", alert: "Alert at (%)", auth: "PIN validity (minutes)", save: "Save", saved: "Limits saved.", error: "Unable to load or save limits.", off: "Long calls are not enabled yet.", costs: "Provider budgets are in USD and are not a customer billing price. Reservations remain until final costs are confirmed. Application termination does not guarantee a strict provider spending cap.", missing: "Avenqo must verify the safety rate before activation." },
  es: { title: "Duración y gastos de llamadas", minutes: "Duración máxima (minutos)", unlimited: "Sin duración fija, dentro del presupuesto", idle: "Detener tras silencio (segundos)", concurrent: "Llamadas simultáneas", call: "Presupuesto del proveedor por llamada (USD)", month: "Presupuesto mensual del proveedor (USD)", monthlyMinutes: "Minutos reservables por mes", alert: "Alerta al (%)", auth: "Validez del PIN (minutos)", save: "Guardar", saved: "Límites guardados.", error: "No se pudieron cargar o guardar los límites.", off: "Las llamadas largas aún no están activadas.", costs: "Los presupuestos del proveedor son en USD, no un precio facturado al cliente. Las reservas permanecen hasta confirmar el coste final. La detención de la aplicación no garantiza un límite estricto del proveedor.", missing: "Avenqo debe verificar la tarifa de seguridad antes de activar." },
};

export function VoiceCallPolicy({ tenantId, canManage }: { tenantId?: string; canManage: boolean }) {
  const { locale } = useLocale();
  const t = copy[locale.startsWith("fr") ? "fr" : locale.startsWith("es") ? "es" : "en"];
  const [loaded, setLoaded] = useState<{ tenant: string; limits: Limits } | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const activeTenant = useRef(tenantId);
  useEffect(() => { activeTenant.current = tenantId; }, [tenantId]);
  useEffect(() => {
    const abort = new AbortController();
    if (tenantId && canManage) {
      const tenant = tenantId;
      void fetch("/api/v1/voice/call-policy", { signal: abort.signal, cache: "no-store" })
        .then(async response => { if (!response.ok) throw new Error("Unavailable"); return response.json() as Promise<Limits>; })
        .then(limits => { if (!abort.signal.aborted && activeTenant.current === tenant) { setLoaded({ tenant, limits }); setNotice(""); } })
        .catch(() => { if (!abort.signal.aborted) setNotice(t.error); });
    }
    return () => abort.abort();
  }, [tenantId, canManage, t.error]);
  if (!canManage || !tenantId) return null;
  if (!loaded || loaded.tenant !== tenantId) return notice ? <p role="alert">{notice}</p> : null;
  const { limits } = loaded;
  const policy = limits.policy;
  function change<K extends keyof Policy>(key: K, value: Policy[K]) {
    setLoaded(current => current && current.tenant === tenantId ? { ...current, limits: { ...current.limits, policy: { ...current.limits.policy, [key]: value } } } : current);
  }
  async function save() {
    const tenant = tenantId;
    setBusy(true); setNotice("");
    try {
      const response = await fetch("/api/v1/voice/call-policy", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policy) });
      if (!response.ok) throw new Error("Rejected");
      const next = await response.json() as Limits;
      if (activeTenant.current === tenant) { setLoaded({ tenant: tenant!, limits: next }); setNotice(t.saved); }
    } catch { if (activeTenant.current === tenant) setNotice(t.error); }
    finally { setBusy(false); }
  }
  const inputClass = "w-full rounded border border-slate-300 bg-transparent p-2 dark:border-white/20";
  return <section className="space-y-3 border-t border-slate-200 pt-4 text-sm dark:border-white/10">
    <h2 className="font-semibold">{t.title}</h2>
    {!limits.enabled && <p>{t.off}</p>}
    {!limits.cost_rate_configured && <p>{t.missing}</p>}
    <form onSubmit={event => { event.preventDefault(); void save(); }} className="grid gap-3 sm:grid-cols-2">
      <label>{t.minutes}<input className={inputClass} type="number" min={1} max={(limits.plan_duration_seconds ?? 86400) / 60} required={policy.max_call_seconds !== null} disabled={policy.max_call_seconds === null} value={policy.max_call_seconds === null ? "" : policy.max_call_seconds / 60} onChange={event => change("max_call_seconds", Number(event.target.value) * 60)} /></label>
      {limits.plan_duration_seconds === null && <label><input type="checkbox" checked={policy.max_call_seconds === null} onChange={event => change("max_call_seconds", event.target.checked ? null : 3600)} /> {t.unlimited}</label>}
      <label>{t.idle}<input className={inputClass} type="number" min={30} max={600} required value={policy.idle_seconds} onChange={event => change("idle_seconds", Number(event.target.value))} /></label>
      <label>{t.concurrent}<input className={inputClass} type="number" min={1} max={limits.plan_concurrent_calls ?? 100} required value={policy.concurrent_calls} onChange={event => change("concurrent_calls", Number(event.target.value))} /></label>
      <label>{t.call}<input className={inputClass} type="number" min={0.01} max={1000} step="0.01" required value={policy.call_budget_usd} onChange={event => change("call_budget_usd", event.target.value)} /></label>
      <label>{t.month}<input className={inputClass} type="number" min={0.01} max={100000} step="0.01" required value={policy.monthly_budget_usd} onChange={event => change("monthly_budget_usd", event.target.value)} /></label>
      <label>{t.monthlyMinutes}<input className={inputClass} type="number" min={1} max={1000000} required value={policy.monthly_minutes} onChange={event => change("monthly_minutes", Number(event.target.value))} /></label>
      <label>{t.alert}<input className={inputClass} type="number" min={1} max={99} required value={policy.alert_percent} onChange={event => change("alert_percent", Number(event.target.value))} /></label>
      <label>{t.auth}<input className={inputClass} type="number" min={1} max={limits.auth_max_seconds / 60} required value={policy.auth_seconds / 60} onChange={event => change("auth_seconds", Number(event.target.value) * 60)} /></label>
      <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={busy} type="submit">{t.save}</button>
    </form>
    <p className="text-xs text-slate-500">{t.costs}</p>
    {notice && <p role="status">{notice}</p>}
  </section>;
}

"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Search, Settings, ShieldAlert } from "lucide-react";
import { useSession } from "@/lib/session-context";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { VOICE_HEALTH_COPY } from "@/lib/i18n/voice-health-copy";
import { VOICE_NUMBER_COPY, VOICE_SELECTION_COPY, VOICE_NUMBER_TYPE_COPY } from "@/lib/i18n/voice-number-copy";
import { VOICE_AUTH_MESSAGES } from "@/lib/i18n/voice-auth-messages.generated";
import { VoiceCustomizationSection } from "@/components/voice/voice-customization-section";

interface Capabilities {
  tenant_id: string;
  subscription_plan: string;
  subscription_status: string;
  enabled_modules: string[];
  plan_compatible_modules: string[];
  available_agents: string[];
  permissions: string[];
  locale: string;
  timezone: string;
  authorized_sources: { sources?: { source_id: string; display_name?: string; name?: string }[] };
  language_matrix: { locale: string; UI_TRANSLATION_SUPPORTED: boolean; STT_SUPPORTED: boolean | null; LLM_LANGUAGE_SUPPORTED: boolean | null; TTS_SUPPORTED: boolean | null; LIVE_AUDIO_VALIDATED: boolean; FULLY_SUPPORTED: boolean }[];
}
interface VoiceStatus {
  voice_status: string;
  number_id: string | null;
  configuration_status: string;
  business_number: string | null;
  country: string | null;
  region: string | null;
  locality: string | null;
  call_count: number;
  call_minutes: number;
  voice_ai_credits_charged: number;
  recent_calls?: { id: string; status: string; started_at: string | null }[];
  data_freshness?: { freshness_status: string };
}
interface Offer {
  phone_number: string;
  is_orderable: boolean;
  number_type: string;
  country_code: string | null;
  region: string | null;
  locality: string | null;
  capabilities: string[];
  cost_information: { upfront_cost?: string; monthly_cost?: string; currency?: string };
  regulatory_requirements: unknown[];
  regulatory_status: string;
}
interface NumberQuote { offer: Offer; quote_token: string; purchase_allowed: boolean; expires_in_seconds: number }

export function VoiceModuleView() {
  const { identity, sourceRevision, credits, creditError } = useSession();
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const company = getApplicationCatalog(locale).company;
  const billing = getApplicationCatalog(locale).phase4e.billing;
  const copy = VOICE_NUMBER_COPY[locale];
  const selectionCopy = VOICE_SELECTION_COPY[locale];
  const typeCopy = VOICE_NUMBER_TYPE_COPY[locale];
  const numberTypes = ['local', 'mobile', 'toll_free', 'national', 'shared_cost'];
  const numberTypeLabel = (type: string) => numberTypes.includes(type)
    ? typeCopy[numberTypes.indexOf(type) + 1] : t.common.insufficientData;
  const health = VOICE_HEALTH_COPY[locale];
  const tenantId = identity?.company.id;
  const [context, setContext] = useState<Capabilities | null>(null);
  const [status, setStatus] = useState<{ tenant: string; data: VoiceStatus } | null>(null);
  const [result, setResult] = useState<{ tenant: string; offers: Offer[] } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [quote, setQuote] = useState<NumberQuote | null>(null);
  const [ownedNumber, setOwnedNumber] = useState("");
  const [pinMessage, setPinMessage] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({ country_code: "", region: "", locality: "", area_code: "", prefix: "", number_type: "local" });
  const [features, setFeatures] = useState(["voice"]);
  const searchAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(async () => {
      if (controller.signal.aborted) return;
      setContext(null); setResult(null); setSelected(null); setStatus(null); setError(false); setBusy(false);
      setQuote(null); setOwnedNumber(""); setPinMessage("");
      if (!tenantId) return;
      try {
        const response = await fetch("/api/v1/voice/capabilities", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("capabilities_unavailable");
        const data: Capabilities = await response.json();
        if (!controller.signal.aborted && data.tenant_id === tenantId) setContext(data);
        const state = await fetch("/api/v1/voice/status", { signal: controller.signal, cache: "no-store" });
        if (state.ok) {
          const payload: VoiceStatus = await state.json();
          if (!controller.signal.aborted) setStatus({ tenant: tenantId, data: payload });
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    });
    return () => { controller.abort(); searchAbort.current?.abort(); };
  }, [tenantId, identity?.user.id, sourceRevision]);

  const active = context?.tenant_id === tenantId ? context : null;
  const currentStatus = status && status.tenant === tenantId ? status.data : null;
  const offers = result && result.tenant === tenantId ? result.offers : [];
  const enabled = active?.enabled_modules.includes("voice") ?? false;
  const planName = active?.subscription_plan === 'professional' ? billing.planProfessional
    : active?.subscription_plan === 'enterprise' || active?.subscription_plan === 'custom_enterprise' ? billing.planEnterprise : billing.planDemo;
  const canManageVoice = active?.permissions.includes("modules:manage") ?? false;
  const agentLabel = (key: string) => ({ retail: t.navigation.retailAi, crm: t.navigation.crmAi, accounting: t.navigation.accountingAi, voice: t.navigation.voiceAi, tenant_capabilities: t.navigation.billing }[key] ?? key);
  const price = (offer: Offer, key: "upfront_cost" | "monthly_cost") => {
    const value = offer.cost_information[key];
    return value != null && offer.cost_information.currency && Number.isFinite(Number(value))
      ? new Intl.NumberFormat(locale, { style: "currency", currency: offer.cost_information.currency }).format(Number(value))
      : t.common.insufficientData;
  };
  const messages = VOICE_AUTH_MESSAGES[locale] ?? VOICE_AUTH_MESSAGES.en;

  async function refreshVoiceStatus() {
    const response = await fetch("/api/v1/voice/status", { cache: "no-store" });
    if (!response.ok) throw new Error("voice_status_unavailable");
    setStatus({ tenant: tenantId ?? "", data: await response.json() });
  }

  async function importOwnedNumber() {
    if (!tenantId || !ownedNumber || !window.confirm(`${ownedNumber} · ${messages[6]}`)) return;
    setBusy(true); setError(false);
    try {
      const response = await fetch("/api/v1/voice/numbers/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number: ownedNumber, confirmed: true }) });
      if (!response.ok) throw new Error("owned_number_import_unavailable");
      setOwnedNumber(""); await refreshVoiceStatus();
    } catch { setError(true); } finally { setBusy(false); }
  }

  async function configureOwnedNumber() {
    if (!currentStatus?.number_id || !window.confirm(`${currentStatus.business_number} · ${messages[6]}`)) return;
    setBusy(true); setError(false);
    try {
      const response = await fetch("/api/v1/voice/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ number_id: currentStatus.number_id, confirmed: true }) });
      if (!response.ok) throw new Error("voice_setup_unavailable");
      await refreshVoiceStatus();
    } catch { setError(true); } finally { setBusy(false); }
  }

  async function saveVoicePin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("voice-pin") as HTMLInputElement;
    const pin = input.value;
    const passwordInput = event.currentTarget.elements.namedItem("voice-account-password") as HTMLInputElement;
    setPinMessage("");
    try {
      const response = await fetch("/api/v1/voice/auth/pin", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin, confirm_pin: pin, current_password: passwordInput.value }) });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error?.message || (typeof payload?.detail === "string" ? payload.detail : company.connectionsGenericError));
      }
      setPinMessage(messages[5]);
    } catch (error) { setPinMessage(error instanceof Error ? error.message : company.connectionsGenericError); } finally { input.value = ""; passwordInput.value = ""; }
  }

  async function requestQuote() {
    const offer = offers.find(item => item.phone_number === selected);
    if (!offer) return;
    setQuote(null); setBusy(true); setError(false);
    const params = new URLSearchParams({ phone_number: offer.phone_number, country_code: offer.country_code ?? filters.country_code, number_type: offer.number_type, ...(offer.region ? { region: offer.region } : {}), ...(offer.locality ? { locality: offer.locality } : {}) });
    try {
      const response = await fetch(`/api/v1/voice/numbers/quote?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error("number_quote_unavailable");
      setQuote(await response.json());
    } catch { setError(true); } finally { setBusy(false); }
  }

  async function confirmNumberPurchase() {
    if (!quote || !quote.purchase_allowed || !window.confirm(`${quote.offer.phone_number} · ${selectionCopy[4]}: ${price(quote.offer, "upfront_cost")} · ${copy.monthlyPrice}: ${price(quote.offer, "monthly_cost")}`)) return;
    setBusy(true); setError(false);
    try {
      const response = await fetch("/api/v1/voice/numbers/provision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone_number: quote.offer.phone_number, country_code: quote.offer.country_code ?? filters.country_code, region: quote.offer.region, locality: quote.offer.locality, number_type: quote.offer.number_type, confirmed: true, quote_token: quote.quote_token }) });
      if (!response.ok) throw new Error("number_provision_unavailable");
      setQuote(null); setSelected(null); setResult(null); await refreshVoiceStatus();
    } catch { setError(true); } finally { setBusy(false); }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!tenantId || !enabled || !canManageVoice) return;
    searchAbort.current?.abort();
    const controller = new AbortController(); searchAbort.current = controller;
    setBusy(true); setError(false); setSelected(null); setQuote(null); setResult(null);
    const params = new URLSearchParams({ country_code: filters.country_code.toUpperCase(), number_type: filters.number_type, limit: "10" });
    for (const key of ["region", "locality", "area_code", "prefix"] as const) if (filters[key].trim()) params.set(key, filters[key].trim());
    for (const feature of features) params.append("capabilities", feature);
    try {
      const response = await fetch(`/api/v1/voice/numbers/search?${params}`, { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("number_search_unavailable");
      const payload = await response.json();
      if (!controller.signal.aborted) setResult({ tenant: tenantId, offers: payload.offers });
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <div className="space-y-7">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-bold">{t.navigation.voiceAi}</h1>
      <Link href="/settings" className="inline-flex items-center gap-2 text-sm"><Settings size={16} />{t.navigation.settings}</Link>
    </header>
    {error && <p role="alert" className="flex items-center gap-2 text-sm text-red-700 dark:text-red-300"><ShieldAlert size={16} />{company.connectionsGenericError}</p>}
    {active && (credits.remaining === 0 || !["active", "trialing"].includes(active.subscription_status)) && <div role="alert" className="rounded-xl border border-amber-400 bg-amber-500/10 p-4 text-sm"><p>{locale.startsWith("fr") ? (credits.remaining === 0 ? "Accueil téléphonique bloqué : votre solde de crédits IA est épuisé." : "Accueil téléphonique bloqué : votre abonnement est inactif.") : (credits.remaining === 0 ? "Phone assistant blocked: your AI credit balance is exhausted." : "Phone assistant blocked: your subscription is inactive.")}</p><p className="mt-2">{locale.startsWith("fr") ? "Solde disponible" : "Available balance"}: {creditError ? "—" : credits.remaining ?? "—"} · <Link href="/billing" className="underline">{t.navigation.billing}</Link></p></div>}
    {!active ? <p role="status">{error ? t.integrations.statusNeedsAttention : company.connectionsLoading}</p> : <>
      <section className="grid gap-4 border-y border-slate-200 py-4 text-sm sm:grid-cols-3 dark:border-white/10">
        <div><div className="text-slate-500">{t.navigation.billing}</div><div className="mt-1 font-semibold">{planName} · {active.subscription_status === 'active' ? billing.statusActive : active.subscription_status === 'trialing' ? billing.statusTrialing : billing.statusInactive}</div><div className="mt-1 flex items-center gap-1">{active.plan_compatible_modules?.includes('voice') && <Check size={14} />}{t.navigation.voiceAi}: {enabled ? billing.statusActive : billing.statusInactive}</div><Link className="mt-2 inline-block underline" href="/billing">{t.navigation.billing}</Link></div>
        <div><div className="text-slate-500">{health.phone}</div><div className="mt-1 font-mono">{currentStatus?.business_number ?? selectionCopy[0]}</div><div className="mt-1 text-xs">{[currentStatus?.country, currentStatus?.region, currentStatus?.locality].filter(Boolean).join(" · ")}</div></div>
        <div><div className="text-slate-500">{locale.startsWith("fr") ? "Crédits IA disponibles" : "Available AI credits"}</div><div className="mt-1">{creditError ? t.common.insufficientData : credits.remaining ?? t.common.insufficientData}</div><div className="mt-1 text-xs">{health.calls}: {currentStatus?.call_count ?? t.common.insufficientData} · {health.minutes}: {currentStatus?.call_minutes ?? t.common.insufficientData}</div></div>
      </section>
      <section className="space-y-3 text-sm">
        <h2 className="font-semibold">{t.navigation.agentsAi}</h2>
        <div className="flex flex-wrap gap-x-5 gap-y-2">{active.available_agents.map(agent => <span key={agent} className="inline-flex items-center gap-1"><Check size={14} className="text-emerald-600" />{agentLabel(agent)}</span>)}</div>
        <div className="text-slate-500">{active.locale} · {active.timezone} · {health.freshness}: {currentStatus?.data_freshness?.freshness_status ?? t.common.insufficientData}</div>
        <div className="text-xs text-slate-500">{active.authorized_sources.sources?.map(source => source.display_name ?? source.name ?? source.source_id).join(' · ')}</div>
      </section>
      {enabled && canManageVoice && !currentStatus?.number_id && <form onSubmit={event => { event.preventDefault(); void importOwnedNumber(); }} className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4 dark:border-white/10">
        <label className="min-w-56 flex-1 space-y-1 text-xs"><span>{health.phone}</span><input aria-label={health.phone} value={ownedNumber} onChange={event => setOwnedNumber(event.target.value)} placeholder="+..." autoComplete="tel" className="w-full rounded border border-slate-300 bg-transparent p-2 text-sm dark:border-white/20" /></label>
        <button type="submit" disabled={busy || !ownedNumber} className="rounded border border-slate-300 px-3 py-2 text-sm disabled:opacity-40 dark:border-white/20">{messages[5]}</button>
      </form>}
      {enabled && canManageVoice && currentStatus?.number_id && currentStatus.configuration_status === "NOT_CONFIGURED" && <section className="space-y-3 border-t border-slate-200 pt-4 text-sm dark:border-white/10">
        <p>{currentStatus.business_number} · {messages[6]}</p>
        <button type="button" disabled={busy} onClick={() => void configureOwnedNumber()} className="rounded border border-slate-300 px-3 py-2 disabled:opacity-40 dark:border-white/20">{selectionCopy[0]}</button>
      </section>}
      {enabled && <VoiceCustomizationSection tenantId={tenantId} />}
      {enabled && <section className="space-y-3 border-t border-slate-200 pt-4 dark:border-white/10">
        <h2 className="text-sm font-semibold">{t.shell.profile} · {messages[3]}</h2>
        <form onSubmit={saveVoicePin} className="flex flex-wrap items-end gap-3">
        <label className="min-w-48 space-y-1 text-xs"><span>{locale === "fr" ? "Mot de passe actuel" : "Current password"}</span><input aria-label={locale === "fr" ? "Mot de passe actuel" : "Current password"} name="voice-account-password" type="password" autoComplete="current-password" required className="w-full rounded border border-slate-300 bg-transparent p-2 text-sm dark:border-white/20" /></label>
        <label className="min-w-48 space-y-1 text-xs"><span>{messages[4]}</span><input aria-label={messages[4]} name="voice-pin" type="password" inputMode="numeric" pattern="[0-9]{6,12}" minLength={6} maxLength={12} autoComplete="new-password" required className="w-full rounded border border-slate-300 bg-transparent p-2 text-sm dark:border-white/20" /></label>
        <button type="submit" className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-white/20">{messages[5]}</button>
        {pinMessage && <span role="status" className="text-xs">{pinMessage}</span>}
        </form>
      </section>}
      {!!currentStatus?.recent_calls?.length && <section className="space-y-2 text-sm"><h2 className="font-semibold">{health.calls}</h2>{currentStatus.recent_calls.map(call => <div key={call.id} className="flex flex-wrap justify-between gap-2 border-b border-slate-100 py-2 dark:border-white/10"><span>{call.started_at ? new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short', timeZone: active.timezone }).format(new Date(call.started_at)) : t.common.insufficientData}</span><span>{call.status}</span></div>)}</section>}
      <section className="space-y-4 border-t border-slate-200 pt-5 dark:border-white/10">
        <h2 className="font-semibold">{selectionCopy[0]}</h2>
        {!enabled || !canManageVoice ? <Link href="/settings" className="inline-flex items-center gap-2 text-sm underline"><Settings size={15} />{t.navigation.settings}</Link> : <>
          <form onSubmit={search} className="grid gap-3 sm:grid-cols-3">
            {([['country_code', copy.country], ['region', copy.region], ['locality', copy.locality], ['area_code', selectionCopy[1]], ['prefix', selectionCopy[2]]] as const).map(([key, label]) => <label key={key} className="space-y-1 text-xs"><span>{label}</span><input required={key === 'country_code'} maxLength={key === 'country_code' ? 2 : 80} value={filters[key]} onChange={event => setFilters({ ...filters, [key]: event.target.value })} className="w-full rounded border border-slate-300 bg-transparent p-2 text-sm dark:border-white/20" /></label>)}
            <label className="space-y-1 text-xs"><span>{typeCopy[0]}</span><select aria-label={typeCopy[0]} value={filters.number_type} onChange={event => setFilters({ ...filters, number_type: event.target.value })} className="w-full rounded border border-slate-300 bg-transparent p-2 text-sm dark:border-white/20">{numberTypes.map(value => <option key={value} value={value}>{numberTypeLabel(value)}</option>)}</select></label>
            <div className="flex gap-4 text-xs">{['voice', 'sms', 'mms'].map(feature => <label key={feature} className="flex items-center gap-1"><input type="checkbox" checked={features.includes(feature)} onChange={event => setFeatures(event.target.checked ? [...features, feature] : features.filter(item => item !== feature))} />{feature.toUpperCase()}</label>)}</div>
            <button disabled={busy || filters.country_code.length !== 2} className="inline-flex items-center justify-center gap-2 rounded border border-slate-300 px-3 py-2 text-sm disabled:opacity-40 dark:border-white/20"><Search size={16} />{copy.search}</button>
          </form>
          {result?.tenant === tenantId && offers.length === 0 && <p role="status" className="text-sm">{company.connectionsNoDataTitle}</p>}
          <div className="divide-y divide-slate-200 dark:divide-white/10">{offers.map((offer, index) => <label key={`${offer.phone_number}-${index}`} className="flex items-start gap-3 py-4 text-sm">
            <input type="radio" name="voice-number" aria-label={`${selectionCopy[3]} ${offer.phone_number}`} checked={selected === offer.phone_number} disabled={!offer.is_orderable} onChange={() => setSelected(offer.phone_number)} className="mt-1" />
            <div className="min-w-0 space-y-1 break-words"><div className="font-mono font-semibold">{offer.phone_number}</div><div>{[offer.country_code, offer.region, offer.locality, numberTypeLabel(offer.number_type)].filter(Boolean).join(' · ')}</div><div>{offer.capabilities.join(' · ')}</div><div>{selectionCopy[4]}: {price(offer, 'upfront_cost')} · {copy.monthlyPrice}: {price(offer, 'monthly_cost')}</div><div className="text-xs text-slate-500">{copy.regulatoryRequirements}: {offer.regulatory_status === 'unknown' ? t.common.insufficientData : JSON.stringify(offer.regulatory_requirements)}</div></div>
          </label>)}</div>
          {selected && <button type="button" disabled={busy} onClick={() => void requestQuote()} className="rounded border border-slate-300 px-3 py-2 text-sm disabled:opacity-40 dark:border-white/20">{selectionCopy[0]}</button>}
          {quote && <section className="space-y-2 border-t border-slate-200 pt-4 text-sm dark:border-white/10">
            <p>{quote.offer.phone_number} · {selectionCopy[4]}: {price(quote.offer, "upfront_cost")} · {copy.monthlyPrice}: {price(quote.offer, "monthly_cost")} · {quote.expires_in_seconds}s</p>
            <p>{copy.regulatoryRequirements}: {quote.offer.regulatory_status === "verified_no_requirements" ? "0" : t.common.insufficientData}</p>
            {quote.purchase_allowed && <button type="button" disabled={busy} onClick={() => void confirmNumberPurchase()} className="rounded border border-slate-300 px-3 py-2 disabled:opacity-40 dark:border-white/20">{copy.purchase}</button>}
          </section>}
        </>}
      </section>
      <details className="border-t border-slate-200 pt-4 dark:border-white/10"><summary className="cursor-pointer text-sm font-semibold">{t.navigation.voiceAi} · STT / LLM / TTS</summary><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead><tr><th className="p-2">Locale</th>{['UI_TRANSLATION_SUPPORTED', 'STT_SUPPORTED', 'LLM_LANGUAGE_SUPPORTED', 'TTS_SUPPORTED', 'LIVE_AUDIO_VALIDATED'].map(field => <th key={field} className="p-2" title={field}>{field.replace('_SUPPORTED', '').replace('_TRANSLATION', '')}</th>)}</tr></thead><tbody>{active.language_matrix.map(item => <tr key={item.locale} className="border-b border-slate-100 dark:border-white/10"><td className="p-2">{item.locale}</td>{(['UI_TRANSLATION_SUPPORTED', 'STT_SUPPORTED', 'LLM_LANGUAGE_SUPPORTED', 'TTS_SUPPORTED', 'LIVE_AUDIO_VALIDATED'] as const).map(field => <td key={field} className="p-2">{item[field] === true ? <Check size={14} aria-label={billing.statusActive} /> : t.common.insufficientData}</td>)}</tr>)}</tbody></table></div></details>
    </>}
  </div>;
}

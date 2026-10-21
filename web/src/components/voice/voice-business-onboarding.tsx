"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { LOCALES } from "@/lib/i18n/locales";
import { VOICE_ONBOARDING_COPY } from "@/lib/i18n/voice-onboarding-copy";

type WorkingPeriod = { open: string; close: string };
type CrmSchedule = { weekly?: Record<string, WorkingPeriod[]>; date_overrides?: Record<string, WorkingPeriod[]>; verification_only?: boolean };
type Profile = {
  expected_version: number; business_name: string; industry: string; description: string;
  activities: string[]; locations: string[]; timezone: string; opening_hours: Record<string, WorkingPeriod> | CrmSchedule;
  primary_locale: string; secondary_locales: string[]; contact_phone: string | null; website: string;
  bookable_service_ids: string[]; allowed_actions: string[]; cancellation_policy: string;
  communication_style: string; accent_preference: string; vocabulary: string[];
};
type Setup = {
  profile: Profile; industry_suggestions: string[]; context_version: string;
  services: { id: string; name: string; duration_minutes: number; price: number; currency: string }[];
  actions: { id: string; module: string; granted: boolean; module_active: boolean }[];
  readiness: { configuration_saved: boolean; booking_authorized: boolean; telephone_verified: boolean };
};
const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const fieldClass = "mt-1 w-full rounded-xl border border-slate-300 bg-white p-2.5 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100";

export function VoiceBusinessOnboarding({ tenantId, canManage }: { tenantId?: string; canManage: boolean }) {
  const { locale } = useLocale();
  const t = VOICE_ONBOARDING_COPY[locale];
  const [loaded, setLoaded] = useState<{ tenant: string; value: Setup } | null>(null);
  const [step, setStep] = useState(0);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef(tenantId);
  useEffect(() => { active.current = tenantId; }, [tenantId]);
  useEffect(() => {
    const abort = new AbortController();
    if (!tenantId || !canManage) return;
    const tenant = tenantId;
    void apiFetch("/api/v1/voice/business-profile", { signal: abort.signal })
      .then(r => r.json()).then((value: Setup) => {
        if (!value?.profile || typeof value.profile.business_name !== "string" || !Array.isArray(value.profile.allowed_actions)
            || !Array.isArray(value.profile.activities) || !Array.isArray(value.services) || !Array.isArray(value.actions)) throw new Error("Invalid setup");
        if (!abort.signal.aborted && active.current === tenant) { setLoaded({ tenant, value }); setNotice(""); setBusy(false); }
      }).catch(() => { if (!abort.signal.aborted) setNotice(t.error); });
    return () => abort.abort();
  }, [tenantId, canManage, t.error]);
  if (!canManage) return null;
  const data = loaded && loaded.tenant === tenantId ? loaded.value : null;
  const profile = data?.profile;
  const crmSchedule = profile && ("weekly" in profile.opening_hours || "date_overrides" in profile.opening_hours)
    ? profile.opening_hours as CrmSchedule : null;
  const simpleHours = (crmSchedule ? {} : profile?.opening_hours ?? {}) as Record<string, WorkingPeriod>;
  const edit = (patch: Partial<Profile>) => {
    if (data && tenantId) setLoaded({ tenant: tenantId, value: { ...data, profile: { ...data.profile, ...patch } } });
    setNotice("");
  };
  const textField = (key: "business_name" | "industry" | "timezone" | "website" | "communication_style" | "accent_preference", label: string) =>
    <label className="block text-sm font-medium">{label}<input className={fieldClass} value={profile?.[key] ?? ""} onChange={e => edit({ [key]: e.target.value })} required={key === "business_name" || key === "industry" || key === "timezone"} /></label>;
  const listField = (key: "activities" | "locations" | "vocabulary", label: string) =>
    <label className="block text-sm font-medium">{label}<textarea className={fieldClass} value={profile?.[key].join("\n") ?? ""} onChange={e => edit({ [key]: e.target.value.split("\n") })} /></label>;
  const save = async () => {
    if (!profile || !tenantId) return;
    const tenant = tenantId;
    setBusy(true); setNotice("");
    try {
      const payload = { ...profile, activities: profile.activities.filter(s => s.trim()),
        locations: profile.locations.filter(s => s.trim()), vocabulary: profile.vocabulary.filter(s => s.trim()) };
      const response = await apiFetch("/api/v1/voice/business-profile", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const value = await response.json() as Setup;
      if (!value?.profile || !value.readiness) throw new Error("Invalid setup");
      if (active.current === tenant) { setLoaded({ tenant, value }); setNotice(t.saved); }
    } catch { if (active.current === tenant) setNotice(t.error); }
    finally { if (active.current === tenant) setBusy(false); }
  };
  const labels = [t.identity, t.offerings, t.access];
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-7">
    <h2 className="text-lg font-semibold text-slate-950 dark:text-white">{t.title}</h2>
    {notice && <p role={notice === t.saved ? "status" : "alert"} className="mt-3 text-sm">{notice}</p>}
    {!data || !profile ? <p className="mt-3 text-sm" aria-busy={!notice}>…</p> : <>
      <p className="mt-3 text-sm font-medium text-blue-700 dark:text-blue-300">{data.readiness.booking_authorized ? t.ready : t.blocked}</p>
      <nav aria-label={t.title} className="my-5 flex flex-wrap gap-2">{labels.map((label, i) => <button key={label} type="button" aria-current={step === i ? "step" : undefined} onClick={() => setStep(i)} className={`rounded-xl px-3 py-2 text-sm ${step === i ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"}`}>{label}</button>)}</nav>
      <form onSubmit={e => { e.preventDefault(); void save(); }}>
        {step === 0 && <div className="grid gap-4 sm:grid-cols-2">
          {textField("business_name", t.name)}{textField("industry", t.industry)}
          <label className="block text-sm sm:col-span-2">{t.description}<textarea className={fieldClass} maxLength={3000} value={profile.description} onChange={e => edit({ description: e.target.value })} /></label>
          {listField("activities", t.activities)}{listField("locations", t.locations)}{textField("timezone", t.timezone)}{textField("website", t.website)}
          <label className="block text-sm">{t.phone}<input className={fieldClass} type="tel" value={profile.contact_phone ?? ""} onChange={e => edit({ contact_phone: e.target.value || null })} /></label>
          <label className="block text-sm">{t.primary}<select className={fieldClass} value={profile.primary_locale} onChange={e => edit({ primary_locale: e.target.value })}>{LOCALES.map(l => <option key={l.code} value={l.code}>{l.nativeName}</option>)}</select></label>
          <label className="block text-sm">{t.secondary}<select multiple className={fieldClass} value={profile.secondary_locales} onChange={e => edit({ secondary_locales: Array.from(e.target.selectedOptions, o => o.value) })}>{LOCALES.filter(l => l.code !== profile.primary_locale).map(l => <option key={l.code} value={l.code}>{l.nativeName}</option>)}</select></label>
          {textField("communication_style", t.style)}{textField("accent_preference", t.accent)}{listField("vocabulary", t.vocabulary)}
          {crmSchedule ? <div className="space-y-2 text-sm sm:col-span-2"><h3 className="font-medium">{t.hours}</h3><p>{t.crmHours}</p>
            {days.map((day, i) => <p key={day}>{new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 0, 5 + i)))} : {(crmSchedule.weekly?.[day] ?? []).map(p => `${p.open}–${p.close}`).join(", ") || t.closed}</p>)}
            <Link href="/crm" className="text-blue-600 underline">{t.crm}</Link>
          </div> : <fieldset className="space-y-2 sm:col-span-2"><legend className="text-sm font-medium">{t.hours}</legend>{days.map((day, i) => <div key={day} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="w-24">{new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 0, 5 + i)))}</span>
            <label><input type="checkbox" checked={!simpleHours[day]} onChange={e => { const hours = { ...simpleHours }; if (e.target.checked) delete hours[day]; else hours[day] = { open: "09:00", close: "17:00" }; edit({ opening_hours: hours }); }} /> {t.closed}</label>
            {simpleHours[day] && ["open", "close"].map(side => <label key={side}>{side === "open" ? t.open : t.close}<input type="time" className="ml-2 rounded border p-1 dark:bg-slate-950" value={simpleHours[day][side as "open" | "close"]} onChange={e => edit({ opening_hours: { ...simpleHours, [day]: { ...simpleHours[day], [side]: e.target.value } } })} /></label>)}
          </div>)}</fieldset>}
        </div>}
        {step === 1 && <div className="space-y-4">
          <h3 className="font-medium">{t.services}</h3><p className="text-sm text-slate-600 dark:text-slate-300">{t.catalog}</p>
          {!data.services.length && <p>{t.none}</p>}
          {data.services.map(s => <label key={s.id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700"><input type="checkbox" checked={profile.bookable_service_ids.includes(s.id)} onChange={e => edit({ bookable_service_ids: e.target.checked ? [...profile.bookable_service_ids, s.id] : profile.bookable_service_ids.filter(id => id !== s.id) })} /><span>{s.name}<span className="block text-sm text-slate-500">{s.duration_minutes} min · {new Intl.NumberFormat(locale, { style: "currency", currency: s.currency }).format(s.price)}</span></span></label>)}
          <Link href="/crm" className="inline-block text-sm text-blue-600 underline">{t.crm}</Link>
          <label className="block text-sm">{t.cancellation}<textarea className={fieldClass} maxLength={1500} value={profile.cancellation_policy} onChange={e => edit({ cancellation_policy: e.target.value })} /></label>
        </div>}
        {step === 2 && <div className="space-y-3"><p className="text-sm">{t.rights}</p>{data.actions.filter(a => a.module_active).map(a => {
          const action = a.id.split(":")[1] as keyof typeof t;
          return <label key={a.id} className="flex items-center gap-3 text-sm"><input type="checkbox" disabled={!a.granted} checked={profile.allowed_actions.includes(a.id)} onChange={e => edit({ allowed_actions: e.target.checked ? [...profile.allowed_actions, a.id] : profile.allowed_actions.filter(id => id !== a.id) })} /><span>{t[action] ?? a.module}{!a.granted && <small className="ml-2 text-slate-500">{t.pending}</small>}</span></label>;
        })}</div>}
        <p className="my-5 text-xs text-slate-500 dark:text-slate-400">{t.validation}</p>
        <button disabled={busy} className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50" type="submit">{busy ? t.saving : t.save}</button>
      </form>
    </>}
  </section>;
}

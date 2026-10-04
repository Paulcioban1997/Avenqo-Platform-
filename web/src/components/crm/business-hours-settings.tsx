"use client";

import { useEffect, useState } from "react";
import { Check, Clock, Plus, Save, Trash2 } from "lucide-react";
import { apiFetch } from "@/lib/api-request";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { BUSINESS_HOURS_COPY } from "@/lib/i18n/business-hours-copy";
import { useLocale } from "@/lib/i18n/locale-context";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
type Period = { open: string; close: string };

export function BusinessHoursSettings() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const [title, zoneLabel, openLabel, closeLabel] = BUSINESS_HOURS_COPY[locale];
  const [zone, setZone] = useState("");
  const [hours, setHours] = useState<Record<string, Period[]>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  const [employeeId, setEmployeeId] = useState("");
  const [employees, setEmployees] = useState<{ id: string; name: string }[]>([]);
  const load = async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await apiFetch(`/api/v1/crm/settings/business-hours${employeeId ? `?employee_id=${employeeId}` : ""}`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      setZone(data.timezone);
      setHours(data.hours);
    } catch { setError(true); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [employeeId]);
  useEffect(() => {
    void apiFetch("/api/v1/crm/employees").then(async (response) => {
      if (response.ok) setEmployees(await response.json());
    }).catch(() => {});
  }, []);
  const update = (day: string, periods: Period[]) => {
    setHours((current) => ({ ...current, [day]: periods }));
    setSaved(false);
  };
  const save = async () => {
    setSaving(true);
    setError(false);
    try {
      const response = await apiFetch("/api/v1/crm/settings/business-hours", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timezone: zone, hours, employee_id: employeeId || null }),
      });
      if (!response.ok) throw new Error();
      setSaved(true);
    } catch { setError(true); }
    finally { setSaving(false); }
  };
  return <section className="border-t border-gray-200 py-6 dark:border-gray-800" aria-labelledby="business-hours-title">
    <h3 id="business-hours-title" className="mb-4 flex items-center gap-2 text-base font-semibold"><Clock size={18} />{title}</h3>
    {employees.length > 0 && <label className="mb-4 block max-w-md text-sm">{t.crm.filters.employee}<select value={employeeId} disabled={loading || saving} onChange={(event) => { setEmployeeId(event.target.value); setSaved(false); }} className="mt-1 w-full rounded border border-gray-300 bg-transparent px-3 py-2"><option value="">{t.shell.company}</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name}</option>)}</select></label>}
    {error && <div role="alert" className="mb-3 text-sm text-red-600">{t.crm.actions.mutationError}<button type="button" onClick={() => void load()} className="ms-3 underline">{t.common.retry}</button></div>}
    <label className="mb-4 block max-w-md text-sm">{zoneLabel}
      <input value={zone} list="business-timezones" disabled={loading || saving || !!employeeId} onChange={(event) => { setZone(event.target.value); setSaved(false); }} className="mt-1 w-full rounded border border-gray-300 bg-transparent px-3 py-2" />
      <datalist id="business-timezones">{Intl.supportedValuesOf("timeZone").map((name) => <option key={name} value={name} />)}</datalist>
    </label>
    <fieldset disabled={loading || saving} className="max-w-3xl divide-y divide-gray-200 dark:divide-gray-800">
      {DAYS.map((day, dayIndex) => {
        const periods = hours[day] || [];
        const name = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 9, 5 + dayIndex)));
        return <div key={day} className="flex flex-wrap items-start gap-3 py-3">
          <label className="flex w-36 shrink-0 items-center gap-2 pt-2 text-sm"><input type="checkbox" checked={periods.length > 0} onChange={(event) => update(day, event.target.checked ? [{ open: "09:00", close: "17:00" }] : [])} />{name}</label>
          <div className="min-w-0 flex-1 space-y-2">{periods.map((period, index) => <div key={index} className="flex flex-wrap items-end gap-2">
            <label className="text-xs">{openLabel}<input type="time" aria-label={`${name} ${openLabel} ${index + 1}`} value={period.open} onChange={(event) => update(day, periods.map((item, itemIndex) => itemIndex === index ? { ...item, open: event.target.value } : item))} className="mt-1 block rounded border border-gray-300 bg-transparent px-2 py-2" /></label>
            <label className="text-xs">{closeLabel}<input type="time" aria-label={`${name} ${closeLabel} ${index + 1}`} value={period.close} onChange={(event) => update(day, periods.map((item, itemIndex) => itemIndex === index ? { ...item, close: event.target.value } : item))} className="mt-1 block rounded border border-gray-300 bg-transparent px-2 py-2" /></label>
            <button type="button" title={t.common.deletePermanently} aria-label={`${name} ${t.common.deletePermanently} ${index + 1}`} onClick={() => update(day, periods.filter((_, itemIndex) => itemIndex !== index))} className="h-10 w-10 rounded border border-gray-300"><Trash2 size={16} className="mx-auto" /></button>
          </div>)}</div>
          {periods.length > 0 && <button type="button" title={title} aria-label={`${name} +`} onClick={() => update(day, [...periods, { open: periods.at(-1)!.close, close: "18:00" }])} className="mt-5 h-10 w-10 rounded border border-gray-300"><Plus size={16} className="mx-auto" /></button>}
        </div>;
      })}
    </fieldset>
    <button type="button" disabled={loading || saving || !zone} onClick={() => void save()} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">{saved ? <Check size={16} /> : <Save size={16} />}{t.crm.actions.save}</button>
  </section>;
}
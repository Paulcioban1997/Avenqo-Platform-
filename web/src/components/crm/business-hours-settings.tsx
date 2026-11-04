"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  Clock,
  Save,
  Check,
  Copy,
  Calendar,
  AlertCircle,
  Coffee,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { apiFetch } from "@/lib/api-request";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { BUSINESS_HOURS_COPY } from "@/lib/i18n/business-hours-copy";
import { useLocale } from "@/lib/i18n/locale-context";

const DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

type DayKey = (typeof DAYS)[number];
type Period = { open: string; close: string };

interface DayScheduleState {
  enabled: boolean;
  open: string;
  close: string;
  hasBreak: boolean;
  breakStart: string;
  breakEnd: string;
}

const DEFAULT_OPEN = "09:00";
const DEFAULT_CLOSE = "17:00";
const DEFAULT_BREAK_START = "12:00";
const DEFAULT_BREAK_END = "13:00";

function parsePeriodsToSchedule(periods: Period[]): Omit<DayScheduleState, "enabled"> & { enabled: boolean } {
  if (!periods || periods.length === 0) {
    return {
      enabled: false,
      open: DEFAULT_OPEN,
      close: DEFAULT_CLOSE,
      hasBreak: false,
      breakStart: DEFAULT_BREAK_START,
      breakEnd: DEFAULT_BREAK_END,
    };
  }
  if (periods.length === 1) {
    return {
      enabled: true,
      open: periods[0].open || DEFAULT_OPEN,
      close: periods[0].close || DEFAULT_CLOSE,
      hasBreak: false,
      breakStart: DEFAULT_BREAK_START,
      breakEnd: DEFAULT_BREAK_END,
    };
  }
  // 2 or more periods -> assume period 1 is morning, break between period 1 and 2, period 2 is afternoon
  return {
    enabled: true,
    open: periods[0].open || DEFAULT_OPEN,
    close: periods[periods.length - 1].close || DEFAULT_CLOSE,
    hasBreak: true,
    breakStart: periods[0].close || DEFAULT_BREAK_START,
    breakEnd: periods[1].open || DEFAULT_BREAK_END,
  };
}

function serializeScheduleToPeriods(state: DayScheduleState): Period[] {
  if (!state.enabled) return [];
  if (!state.hasBreak) {
    return [{ open: state.open, close: state.close }];
  }
  // Validate break ordering
  if (state.open < state.breakStart && state.breakStart < state.breakEnd && state.breakEnd < state.close) {
    return [
      { open: state.open, close: state.breakStart },
      { open: state.breakEnd, close: state.close },
    ];
  }
  // Fallback if break is misconfigured
  return [{ open: state.open, close: state.close }];
}

export function BusinessHoursSettings() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const copyEntry = BUSINESS_HOURS_COPY[locale as keyof typeof BUSINESS_HOURS_COPY] ?? BUSINESS_HOURS_COPY.en;
  const [title, zoneLabel] = copyEntry;

  const [zone, setZone] = useState("America/Toronto");
  const [employeeId, setEmployeeId] = useState("");
  const [employees, setEmployees] = useState<{ id: string; name: string }[]>([]);

  const [schedule, setSchedule] = useState<Record<DayKey, DayScheduleState>>({
    monday: { enabled: true, open: "09:00", close: "17:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    tuesday: { enabled: true, open: "09:00", close: "17:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    wednesday: { enabled: true, open: "09:00", close: "17:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    thursday: { enabled: true, open: "09:00", close: "17:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    friday: { enabled: true, open: "09:00", close: "17:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    saturday: { enabled: false, open: "10:00", close: "16:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
    sunday: { enabled: false, open: "10:00", close: "16:00", hasBreak: false, breakStart: "12:00", breakEnd: "13:00" },
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const response = await apiFetch(
        `/api/v1/crm/settings/business-hours${employeeId ? `?employee_id=${employeeId}` : ""}`
      );
      if (!response.ok) throw new Error("Erreur de chargement");
      const data = await response.json();
      if (data.timezone) setZone(data.timezone);
      const incomingHours: Record<string, Period[]> = data.hours || {};
      const newSched = {} as Record<DayKey, DayScheduleState>;
      for (const d of DAYS) {
        newSched[d] = parsePeriodsToSchedule(incomingHours[d] || []);
      }
      setSchedule(newSched);
    } catch {
      setErrorMsg(t.crm.actions.mutationError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [employeeId]);

  useEffect(() => {
    void apiFetch("/api/v1/crm/employees")
      .then(async (res) => {
        if (res.ok) setEmployees(await res.json());
      })
      .catch(() => {});
  }, []);

  const handleUpdateDay = (day: DayKey, partial: Partial<DayScheduleState>) => {
    setSchedule((prev) => ({
      ...prev,
      [day]: { ...prev[day], ...partial },
    }));
    setSaved(false);
  };

  const copyMondayToWeekdays = () => {
    const mondayState = schedule.monday;
    setSchedule((prev) => ({
      ...prev,
      tuesday: { ...mondayState },
      wednesday: { ...mondayState },
      thursday: { ...mondayState },
      friday: { ...mondayState },
    }));
    setSaved(false);
  };

  const copyMondayToAll = () => {
    const mondayState = schedule.monday;
    setSchedule((prev) => {
      const next = { ...prev };
      for (const d of DAYS) {
        next[d] = { ...mondayState };
      }
      return next;
    });
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg(null);
    try {
      const serializedHours: Record<string, Period[]> = {};
      for (const d of DAYS) {
        serializedHours[d] = serializeScheduleToPeriods(schedule[d]);
      }
      const response = await apiFetch("/api/v1/crm/settings/business-hours", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          timezone: zone || "America/Toronto",
          hours: serializedHours,
          employee_id: employeeId || null,
        }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Erreur d'enregistrement");
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 4000);
    } catch (e: any) {
      setErrorMsg(e.message || t.crm.actions.mutationError);
    } finally {
      setSaving(false);
    }
  };

  const dayNames = useMemo(() => {
    const map = {} as Record<DayKey, string>;
    DAYS.forEach((day, idx) => {
      // 2026-10-05 is a Monday
      const d = new Date(Date.UTC(2026, 9, 5 + idx));
      map[day] = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(d);
    });
    return map;
  }, [locale]);

  const fr = locale.startsWith("fr");

  return (
    <section
      className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-6"
      aria-labelledby="business-hours-title"
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-white/[0.06]">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-[#0076FF] dark:text-[#00D4FF]">
            <Clock size={20} />
          </div>
          <div>
            <h3 id="business-hours-title" className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              {title}
            </h3>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              {fr
                ? "Configurez vos plages d'ouverture hebdomadaires et pauses pour les prises de rendez-vous."
                : "Configure your weekly opening hours and break times for appointment booking."}
            </p>
          </div>
        </div>

        {/* Quick Batch Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copyMondayToWeekdays}
            disabled={loading || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.06] dark:hover:bg-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer"
            title={fr ? "Copie la plage du lundi vers mardi, mercredi, jeudi et vendredi" : "Copy Monday schedule to Tue-Fri"}
          >
            <Copy size={13} className="text-[#0076FF]" />
            <span>{fr ? "Copier lundi → mar-ven" : "Copy Mon → Tue-Fri"}</span>
          </button>
          <button
            type="button"
            onClick={copyMondayToAll}
            disabled={loading || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.06] dark:hover:bg-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer"
            title={fr ? "Copie la plage du lundi vers tous les jours de la semaine" : "Apply Monday schedule to all days"}
          >
            <Calendar size={13} className="text-[#0076FF]" />
            <span>{fr ? "Appliquer à tous" : "Apply to all"}</span>
          </button>
        </div>
      </div>

      {/* Scope Controls: Employee selector & Timezone */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {employees.length > 0 && (
          <div>
            <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">
              {t.crm.filters.employee}
            </label>
            <select
              value={employeeId}
              disabled={loading || saving}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-[#111D3D] text-xs font-medium text-slate-800 dark:text-slate-200"
            >
              <option value="">{fr ? "Horaires globaux de l'entreprise" : "Company Global Schedule"}</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">
            {zoneLabel} (Fuseau horaire de référence)
          </label>
          <input
            value={zone}
            list="business-timezones"
            disabled={loading || saving || !!employeeId}
            onChange={(e) => {
              setZone(e.target.value);
              setSaved(false);
            }}
            placeholder="America/Toronto"
            className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-[#111D3D] text-xs font-mono font-medium text-slate-800 dark:text-slate-200"
          />
          <datalist id="business-timezones">
            <option value="America/Toronto">America/Toronto (Montréal, Toronto, Québec)</option>
            <option value="America/Vancouver">America/Vancouver (Pacifique)</option>
            <option value="America/New_York">America/New_York (Eastern Time)</option>
            <option value="Europe/Paris">Europe/Paris (France CET)</option>
            <option value="UTC">UTC (Coordinated Universal Time)</option>
          </datalist>
        </div>
      </div>

      {/* Feedback Messages */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex items-center justify-between text-xs text-rose-800 dark:text-rose-300">
          <div className="flex items-center gap-2">
            <AlertCircle size={15} />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => void loadData()} className="underline font-bold">
            {t.common.retry}
          </button>
        </div>
      )}

      {saved && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 flex items-center gap-2 text-xs text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 size={16} />
          <span>{fr ? "Horaires enregistrés avec succès." : "Business hours saved successfully."}</span>
        </div>
      )}

      {/* Weekly Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200/80 dark:border-white/[0.08] text-slate-400 dark:text-slate-500 uppercase font-bold text-[10px] tracking-wider">
              <th className="py-2.5 px-3">{fr ? "Jour" : "Day"}</th>
              <th className="py-2.5 px-3">{fr ? "Statut" : "Status"}</th>
              <th className="py-2.5 px-3">{fr ? "Horaires d'ouverture" : "Working Hours"}</th>
              <th className="py-2.5 px-3">{fr ? "Pause déjeuner" : "Break Time"}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
            {DAYS.map((day) => {
              const current = schedule[day];
              const isWeekend = day === "saturday" || day === "sunday";

              return (
                <tr
                  key={day}
                  className={`transition-colors ${
                    current.enabled
                      ? "hover:bg-slate-50/60 dark:hover:bg-white/[0.01]"
                      : "bg-slate-50/30 dark:bg-white/[0.01] opacity-75"
                  }`}
                >
                  {/* Day Label */}
                  <td className="py-3 px-3 font-semibold text-slate-800 dark:text-slate-200 capitalize">
                    {dayNames[day]}
                    {isWeekend && (
                      <span className="ml-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 dark:bg-white/[0.06] text-slate-400">
                        {fr ? "Week-end" : "Weekend"}
                      </span>
                    )}
                  </td>

                  {/* Open / Closed Toggle Switch */}
                  <td className="py-3 px-3">
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={current.enabled}
                        disabled={loading || saving}
                        onChange={(e) => handleUpdateDay(day, { enabled: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-800 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-slate-600 peer-checked:bg-[#0076FF]"></div>
                      <span className={`text-[11px] font-bold ${current.enabled ? "text-emerald-600 dark:text-emerald-400" : "text-slate-400"}`}>
                        {current.enabled ? (fr ? "Ouvert" : "Open") : (fr ? "Fermé" : "Closed")}
                      </span>
                    </label>
                  </td>

                  {/* Working Hours (Open - Close) */}
                  <td className="py-3 px-3">
                    {current.enabled ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="time"
                          value={current.open}
                          disabled={loading || saving}
                          onChange={(e) => handleUpdateDay(day, { open: e.target.value })}
                          className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium text-slate-800 dark:text-slate-200"
                        />
                        <span className="text-slate-400">→</span>
                        <input
                          type="time"
                          value={current.close}
                          disabled={loading || saving}
                          onChange={(e) => handleUpdateDay(day, { close: e.target.value })}
                          className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium text-slate-800 dark:text-slate-200"
                        />
                      </div>
                    ) : (
                      <span className="text-slate-400 text-xs italic">{fr ? "Non disponible" : "Not available"}</span>
                    )}
                  </td>

                  {/* Lunch / Break Time */}
                  <td className="py-3 px-3">
                    {current.enabled ? (
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={current.hasBreak}
                            disabled={loading || saving}
                            onChange={(e) => handleUpdateDay(day, { hasBreak: e.target.checked })}
                            className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                          />
                          <Coffee size={13} className={current.hasBreak ? "text-amber-500" : "text-slate-400"} />
                          <span>{fr ? "Pause" : "Break"}</span>
                        </label>

                        {current.hasBreak && (
                          <div className="flex items-center gap-1.5 animate-in fade-in">
                            <input
                              type="time"
                              value={current.breakStart}
                              disabled={loading || saving}
                              onChange={(e) => handleUpdateDay(day, { breakStart: e.target.value })}
                              className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono text-slate-700 dark:text-slate-300"
                            />
                            <span className="text-slate-400">à</span>
                            <input
                              type="time"
                              value={current.breakEnd}
                              disabled={loading || saving}
                              onChange={(e) => handleUpdateDay(day, { breakEnd: e.target.value })}
                              className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono text-slate-700 dark:text-slate-300"
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-300 dark:text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Save Button */}
      <div className="pt-4 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between">
        <p className="text-[11px] text-slate-400">
          {fr
            ? "Les modifications d'horaires s'appliquent immédiatement à la prise de rendez-vous en ligne et par Voice AI."
            : "Schedule adjustments apply immediately to online bookings and Voice AI agents."}
        </p>

        <button
          type="button"
          disabled={loading || saving}
          onClick={() => void handleSave()}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold shadow-xs transition-colors cursor-pointer disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : saved ? (
            <Check size={14} />
          ) : (
            <Save size={14} />
          )}
          <span>{saved ? (fr ? "Enregistré !" : "Saved!") : t.crm.actions.save}</span>
        </button>
      </div>
    </section>
  );
}

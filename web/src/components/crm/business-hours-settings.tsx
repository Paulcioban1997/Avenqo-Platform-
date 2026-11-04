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
import {
  BUSINESS_HOURS_COPY,
  BUSINESS_HOURS_EXTENDED_COPY,
  type BusinessHoursExtendedCopy,
} from "@/lib/i18n/business-hours-copy";
import { CANONICAL_LOCALES } from "@/lib/i18n/canonical-locales.generated";
import { useLocale } from "@/lib/i18n/locale-context";
import type { LocaleCode } from "@/lib/i18n/types";

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

function parsePeriodsToSchedule(periods: Period[]): DayScheduleState {
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

export function validateDaySchedule(
  day: DayKey,
  state: DayScheduleState,
  dayLabel: string,
  ui: BusinessHoursExtendedCopy,
): string | null {
  if (!state.enabled) return null;

  if (state.open >= state.close) {
    return `${dayLabel}: ${ui.invalidOrder} (${state.open} ≥ ${state.close})`;
  }

  if (state.hasBreak) {
    if (state.breakStart >= state.breakEnd) {
      return `${dayLabel}: ${ui.invalidBreakOrder} (${state.breakStart} ≥ ${state.breakEnd})`;
    }
    if (state.breakStart <= state.open) {
      return `${dayLabel}: ${ui.invalidBreakStart} (${state.breakStart} ≤ ${state.open})`;
    }
    if (state.breakEnd >= state.close) {
      return `${dayLabel}: ${ui.invalidBreakEnd} (${state.breakEnd} ≥ ${state.close})`;
    }
  }

  return null;
}

function serializeScheduleToPeriods(state: DayScheduleState): Period[] {
  if (!state.enabled) return [];
  if (!state.hasBreak) {
    return [{ open: state.open, close: state.close }];
  }
  return [
    { open: state.open, close: state.breakStart },
    { open: state.breakEnd, close: state.close },
  ];
}

export function BusinessHoursSettings() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const copyEntry =
    BUSINESS_HOURS_COPY[locale as keyof typeof BUSINESS_HOURS_COPY] ??
    BUSINESS_HOURS_COPY.en;
  const [title, zoneLabel] = copyEntry;

  const ui =
    BUSINESS_HOURS_EXTENDED_COPY[locale as LocaleCode] ??
    BUSINESS_HOURS_EXTENDED_COPY.en;

  const dir = useMemo(() => {
    const found = CANONICAL_LOCALES.find((l) => l.code === locale);
    return found?.direction || "ltr";
  }, [locale]);

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
  const [invalidDay, setInvalidDay] = useState<DayKey | null>(null);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg(null);
    setInvalidDay(null);
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
    if (invalidDay === day) {
      setInvalidDay(null);
      setErrorMsg(null);
    }
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
    setInvalidDay(null);
    setErrorMsg(null);
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
    setInvalidDay(null);
    setErrorMsg(null);
  };

  const dayNames = useMemo(() => {
    const map: Record<DayKey, string> = {} as any;
    DAYS.forEach((day, idx) => {
      // 2026-10-05 is a Monday
      const d = new Date(Date.UTC(2026, 9, 5 + idx));
      map[day] = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(d);
    });
    return map;
  }, [locale]);

  const handleSave = async () => {
    setErrorMsg(null);
    setInvalidDay(null);

    // Strict validation before saving: never silently delete breaks or accept invalid hours
    for (const d of DAYS) {
      const validationError = validateDaySchedule(d, schedule[d], dayNames[d], ui);
      if (validationError) {
        setErrorMsg(validationError);
        setInvalidDay(d);
        return;
      }
    }

    setSaving(true);
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
        const data = await response.json().catch(() => ({}));
        throw new Error(data?.detail || t.crm.actions.mutationError);
      }

      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setErrorMsg(err.message || t.crm.actions.mutationError);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      dir={dir}
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
              {ui.subtitle}
            </p>
          </div>
        </div>

        {/* Quick Batch Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copyMondayToWeekdays}
            disabled={loading || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.06] dark:hover:bg-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Copy size={13} className="text-[#0076FF]" />
            <span>{ui.copyMonday}</span>
          </button>
          <button
            type="button"
            onClick={copyMondayToAll}
            disabled={loading || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.06] dark:hover:bg-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Calendar size={13} className="text-[#0076FF]" />
            <span>{ui.copyAll}</span>
          </button>
        </div>
      </div>

      {/* Scope: Timezone and Employee Selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">
            {zoneLabel}
          </label>
          <input
            type="text"
            value={zone}
            disabled={loading || saving}
            onChange={(e) => {
              setZone(e.target.value);
              setSaved(false);
            }}
            placeholder="America/Toronto"
            className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-[#111D3D] text-xs font-mono font-medium text-slate-800 dark:text-slate-200"
          />
        </div>

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
              <option value="">{t.crm.calendar.allEmployees}</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Alerts */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/40 flex items-center gap-2.5 text-xs text-red-700 dark:text-red-300 animate-in fade-in">
          <AlertCircle size={16} className="shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {saved && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40 flex items-center gap-2.5 text-xs text-emerald-700 dark:text-emerald-300 animate-in fade-in">
          <CheckCircle2 size={16} className="shrink-0" />
          <span>{ui.saved}</span>
        </div>
      )}

      {/* Modern Schedule Table Grid */}
      <div className="overflow-x-auto rounded-xl border border-slate-200/80 dark:border-white/[0.08]">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50/80 dark:bg-[#060B13]/40 text-slate-400 dark:text-slate-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-100 dark:border-white/[0.06]">
            <tr>
              <th className="py-3 px-3">{ui.day}</th>
              <th className="py-3 px-3">{ui.status}</th>
              <th className="py-3 px-3">{ui.mainHours}</th>
              <th className="py-3 px-3">{ui.lunchBreak}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
            {DAYS.map((day) => {
              const current = schedule[day];
              const isWeekend = day === "saturday" || day === "sunday";
              const isDayInvalid = invalidDay === day;

              return (
                <tr
                  key={day}
                  className={`transition-colors ${
                    isDayInvalid
                      ? "bg-red-50/50 dark:bg-red-950/20 border-l-4 border-l-red-500"
                      : current.enabled
                        ? "hover:bg-slate-50/60 dark:hover:bg-white/[0.01]"
                        : "bg-slate-50/30 dark:bg-white/[0.01] opacity-75"
                  }`}
                >
                  {/* Day Label */}
                  <td className="py-3 px-3 font-semibold text-slate-800 dark:text-slate-200 capitalize">
                    {dayNames[day]}
                    {isWeekend && (
                      <span className="ms-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 dark:bg-white/[0.06] text-slate-400">
                        {ui.weekend}
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
                        {current.enabled ? ui.open : ui.closed}
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
                          className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium"
                        />
                        <span className="text-slate-400">{ui.to}</span>
                        <input
                          type="time"
                          value={current.close}
                          disabled={loading || saving}
                          onChange={(e) => handleUpdateDay(day, { close: e.target.value })}
                          className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium"
                        />
                      </div>
                    ) : (
                      <span className="text-slate-400 italic text-[11px]">{ui.closed}</span>
                    )}
                  </td>

                  {/* Break Hours (Lunch Break) */}
                  <td className="py-3 px-3">
                    {current.enabled ? (
                      <div className="flex flex-wrap items-center gap-3">
                        <label className="inline-flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={current.hasBreak}
                            disabled={loading || saving}
                            onChange={(e) => handleUpdateDay(day, { hasBreak: e.target.checked })}
                            className="rounded border-slate-300 dark:border-slate-600 text-[#0076FF] focus:ring-0"
                          />
                          <span className="text-[11px] font-medium text-slate-600 dark:text-slate-300 flex items-center gap-1">
                            <Coffee size={12} className={current.hasBreak ? "text-amber-500" : "text-slate-400"} />
                            <span>{ui.pause}</span>
                          </span>
                        </label>

                        {current.hasBreak && (
                          <div className="flex items-center gap-2 animate-in fade-in">
                            <input
                              type="time"
                              value={current.breakStart}
                              disabled={loading || saving}
                              onChange={(e) => handleUpdateDay(day, { breakStart: e.target.value })}
                              className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium"
                            />
                            <span className="text-slate-400">{ui.to}</span>
                            <input
                              type="time"
                              value={current.breakEnd}
                              disabled={loading || saving}
                              onChange={(e) => handleUpdateDay(day, { breakEnd: e.target.value })}
                              className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#111D3D] text-xs font-mono font-medium"
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-400 italic text-[11px]">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Save Button */}
      <div className="pt-4 border-t border-slate-100 dark:border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="text-[11px] text-slate-400">
          {ui.notice}
        </p>

        <button
          type="button"
          disabled={loading || saving}
          onClick={() => void handleSave()}
          aria-label={t.crm.actions.save}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold shadow-xs transition-colors cursor-pointer disabled:opacity-50 self-end sm:self-auto"
        >
          {saving ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : saved ? (
            <Check size={14} />
          ) : (
            <Save size={14} />
          )}
          <span>{saved ? ui.saved : t.crm.actions.save}</span>
        </button>
      </div>
    </section>
  );
}

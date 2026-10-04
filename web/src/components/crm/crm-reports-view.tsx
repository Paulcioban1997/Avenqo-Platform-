"use client";

import React, { useState, useEffect } from "react";
import { BarChart3, Users, CalendarCheck, TrendingUp, DollarSign, Download, RefreshCw } from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import { type CRMKpis } from "./crm-kpi-cards";
import { useLocale } from "@/lib/i18n/locale-context";
import { apiFetch } from "@/lib/api-request";
import { currencyText, finiteMetric, metricText } from "./crm-format";

interface CRMReportsViewProps {
  t: AppTranslations;
}

export function CRMReportsView({ t }: CRMReportsViewProps) {
  const { locale } = useLocale();
  const [kpis, setKpis] = useState<CRMKpis>({});
  const [summary, setSummary] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const fetchReportData = async () => {
    setIsLoading(true);
    setKpis({});
    setSummary(null);
    setFailed(false);
    try {
      const headers = getAuthHeaders();
      const [kpiRes, sumRes] = await Promise.all([
        apiFetch("/api/v1/crm/kpis", { headers }),
        apiFetch("/api/v1/crm/summary", { headers }),
      ]);
      if (kpiRes.ok) {
        setKpis(await kpiRes.json() ?? {});
      }
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      }
    } catch {
      setFailed(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReportData();
  }, []);

  const unavailable = t.common.insufficientData;
  const formattedRevenue = currencyText(kpis.total_revenue_generated, kpis.currency, locale, unavailable);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {failed && <div role="alert">{t.common.errorTitle}</div>}
      {/* REPORTS HEADER */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-[#0B132B] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {t.crm.tabs.reports}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {t.crm.headerSubtitle}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchReportData}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
            title={t.integrations.syncNow}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* METRICS GRID */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>{t.crm.kpis.activeClients}</span>
            <Users className="w-4 h-4 text-[#0076FF]" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {isLoading ? t.crm.calendar.loadingAppointments : metricText(kpis.active_clients, locale, unavailable)}
          </div>
          <div className="text-[10px] text-slate-400">{t.crm.tabs.clients}</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>{t.crm.kpis.appointmentsThisMonth}</span>
            <CalendarCheck className="w-4 h-4 text-[#00D4FF]" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {isLoading ? t.crm.calendar.loadingAppointments : metricText(kpis.appointments_this_month, locale, unavailable)}
          </div>
          <div className="text-[10px] text-slate-400">{t.crm.status.confirmed}</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>{t.crm.kpis.attendanceRate}</span>
            <TrendingUp className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {finiteMetric(kpis.attendance_rate_percent) === null ? unavailable : `${metricText(kpis.attendance_rate_percent, locale, unavailable, 1)} %`}
          </div>
          <div className="text-[10px] text-slate-400">{t.crm.kpis.attendanceRate}</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>{t.crm.kpis.revenueGenerated}</span>
            <DollarSign className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {formattedRevenue}
          </div>
          <div className="text-[10px] text-slate-400">{t.crm.kpis.revenueGenerated}</div>
        </div>
      </div>

      {/* SUMMARY OVERVIEW CARD */}
      <div className="bg-white dark:bg-[#0B132B] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[#0076FF]" />
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            {t.crm.headerSubtitle}
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{t.crm.tabs.clients}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {metricText(summary?.total_leads, locale, unavailable)}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{t.crm.kpis.revenueGenerated}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {currencyText(summary?.total_pipeline_value, kpis.currency, locale, unavailable)}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{t.crm.actions.modify}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {metricText(summary?.pending_tasks_count, locale, unavailable)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

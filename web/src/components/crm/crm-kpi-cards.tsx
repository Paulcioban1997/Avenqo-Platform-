"use client";

import React from "react";
import { Users, Calendar, CheckCircle2, DollarSign } from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { useLocale } from "@/lib/i18n/locale-context";
import { finiteMetric, metricText } from "./crm-format";

export interface CRMKpis {
  active_clients?: number | null;
  appointments_this_month?: number | null;
  attendance_rate_percent?: number | null;
  total_revenue_generated?: number | null;
  currency?: string;
}

interface CRMKpiCardsProps {
  kpis: CRMKpis;
  t: AppTranslations;
  isLoading?: boolean;
}

export function CRMKpiCards({ kpis, t, isLoading = false }: CRMKpiCardsProps) {
  const { locale } = useLocale();
  const unavailable = t.common.insufficientData;
  const number = (value: unknown, digits = 0) => isLoading ? t.crm.calendar.loadingAppointments : metricText(value, locale, unavailable, digits);
  const hasRevenue = finiteMetric(kpis?.total_revenue_generated) !== null && typeof kpis?.currency === "string" && /^[A-Z]{3}$/.test(kpis.currency);
  const cards = [
    {
      title: t.crm.kpis.activeClients,
      value: number(kpis?.active_clients),
      icon: Users,
      color: "text-[#0076FF]",
      bg: "bg-blue-50 dark:bg-blue-950/40 border-blue-100 dark:border-blue-900/40",
    },
    {
      title: t.crm.kpis.appointmentsThisMonth,
      value: number(kpis?.appointments_this_month),
      icon: Calendar,
      color: "text-[#00D4FF]",
      bg: "bg-cyan-50 dark:bg-cyan-950/40 border-cyan-100 dark:border-cyan-900/40",
    },
    {
      title: t.crm.kpis.attendanceRate,
      value: isLoading ? number(null) : finiteMetric(kpis?.attendance_rate_percent) === null ? unavailable : `${number(kpis.attendance_rate_percent, 1)}%`,
      icon: CheckCircle2,
      color: "text-emerald-500",
      bg: "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-100 dark:border-emerald-900/40",
    },
    {
      title: t.crm.kpis.revenueGenerated,
      value: isLoading ? number(null) : hasRevenue ? `${number(kpis.total_revenue_generated, 2)} ${kpis.currency}` : unavailable,
      icon: DollarSign,
      color: "text-violet-500",
      bg: "bg-violet-50 dark:bg-violet-950/40 border-violet-100 dark:border-violet-900/40",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm hover:shadow-md transition-all duration-200"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-500 dark:text-[#94A3B8] uppercase tracking-wider">
                {card.title}
              </span>
              <div className={`p-2.5 rounded-xl border ${card.bg}`}>
                <Icon className={`w-4 h-4 ${card.color}`} />
              </div>
            </div>
            <div className="mt-3">
              <span className="break-words text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
                {card.value}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

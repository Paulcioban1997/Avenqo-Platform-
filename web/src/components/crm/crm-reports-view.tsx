"use client";

import React, { useState, useEffect } from "react";
import { BarChart3, Users, CalendarCheck, TrendingUp, DollarSign, Download, RefreshCw } from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import { type CRMKpis } from "./crm-kpi-cards";

interface CRMReportsViewProps {
  t: AppTranslations;
}

export function CRMReportsView({ t }: CRMReportsViewProps) {
  const [kpis, setKpis] = useState<CRMKpis>({
    active_clients: 0,
    appointments_this_month: 0,
    attendance_rate_percent: 0,
    total_revenue_generated: 0,
    currency: "CAD",
  });
  const [summary, setSummary] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchReportData = async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();
      const [kpiRes, sumRes] = await Promise.all([
        fetch("/api/v1/crm/kpis", { headers }),
        fetch("/api/v1/crm/summary", { headers }),
      ]);
      if (kpiRes.ok) {
        setKpis(await kpiRes.json());
      }
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      }
    } catch {
      // Keep real zeroes
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReportData();
  }, []);

  const formattedRevenue = new Intl.NumberFormat("fr-CA", {
    style: "currency",
    currency: kpis.currency || "CAD",
  }).format(kpis.total_revenue_generated);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* REPORTS HEADER */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-[#0B132B] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {t.crm.tabs.reports || "Rapports & Performance CRM"}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Indicateurs consolidés en temps réel sur le registre certifié de votre entreprise.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchReportData}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
            title="Rafraîchir"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* METRICS GRID */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Clients actifs</span>
            <Users className="w-4 h-4 text-[#0076FF]" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {kpis.active_clients}
          </div>
          <div className="text-[10px] text-slate-400">Base clients enregistrée</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Rendez-vous ce mois</span>
            <CalendarCheck className="w-4 h-4 text-[#00D4FF]" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {kpis.appointments_this_month}
          </div>
          <div className="text-[10px] text-slate-400">Planifications confirmées</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Taux de présence</span>
            <TrendingUp className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {kpis.attendance_rate_percent.toFixed(1)} %
          </div>
          <div className="text-[10px] text-slate-400">Ratio de présence réelle</div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-slate-800 shadow-xs space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Revenus générés</span>
            <DollarSign className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {formattedRevenue}
          </div>
          <div className="text-[10px] text-slate-400">Chiffre d'affaires validé</div>
        </div>
      </div>

      {/* SUMMARY OVERVIEW CARD */}
      <div className="bg-white dark:bg-[#0B132B] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[#0076FF]" />
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            Répartition de l'activité commerciale
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">Prospects & Leads</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {summary?.total_leads ?? 0}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">Valeur totale du pipeline</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {summary?.total_pipeline_value ?? 0} {kpis.currency}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">Tâches de suivi en attente</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {summary?.pending_tasks_count ?? 0}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

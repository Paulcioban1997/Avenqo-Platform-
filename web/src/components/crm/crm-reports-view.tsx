"use client";

import React, { useState, useEffect } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";
import { type CRMKpis } from "./crm-kpi-cards";
import { useLocale } from "@/lib/i18n/locale-context";
import { apiFetch } from "@/lib/api-request";
import { currencyText, metricText } from "./crm-format";

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
            {locale.startsWith("fr")
              ? "Les cartes du haut sont les indicateurs du mois. Le bloc ci-dessous est le pipeline, pas ce revenu."
              : "The cards above are this month’s figures. The block below is the pipeline, not that revenue."}
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

      <div className="bg-white dark:bg-[#0B132B] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
        <div className="flex items-start gap-2">
          <BarChart3 className="w-5 h-5 text-[#0076FF] shrink-0" />
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {locale.startsWith("fr") ? "Pipeline des affaires" : "Deal pipeline"}
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              {locale.startsWith("fr")
                ? "La valeur additionne les affaires de cette entreprise qui ne sont pas perdues. Ce n’est pas le revenu du mois. Les contacts du registre sont distincts des clients actifs."
                : "The value adds this company’s deals that are not lost. It is not this month’s revenue. Register contacts are separate from active clients."}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{locale.startsWith("fr") ? "Contacts du registre" : "Register contacts"}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {metricText(summary?.total_contacts, locale, unavailable)}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{locale.startsWith("fr") ? "Valeur du pipeline" : "Pipeline value"}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {currencyText(summary?.total_pipeline_value, kpis.currency || summary?.currency || "CAD", locale, unavailable)}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.04]">
            <div className="text-xs text-slate-400">{locale.startsWith("fr") ? "Suivis en attente" : "Pending follow-ups"}</div>
            <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {metricText(summary?.pending_follow_ups ?? summary?.pending_tasks_count, locale, unavailable)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

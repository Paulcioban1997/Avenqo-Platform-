"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Megaphone,
  Sparkles,
  Users,
  TrendingUp,
  Target,
  Send,
  Plug,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { ApiRequestError, apiFetch } from "@/lib/api-request";
import { useSession } from "@/lib/session-context";

type CustomerAnalysis = { available: boolean; currency: string; source_context: { name?: string };
  summary: { total_customers: number; active_customers: number | null; purchase_frequency: number; average_customer_value: number | null } | null;
  segments: { label: string; count: number }[] };

export function MarketingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const company = getApplicationCatalog(locale).company;
  const session = useSession();
  const tenant = session.identity?.company.id;
  const revision = session.sourceRevision;
  const contextRef = useRef({ tenant, revision });
  useEffect(() => {
    contextRef.current = { tenant, revision };
    setGeneratedCampaign(null); setGenerationError(""); setGenerating(false);
  }, [tenant, revision]);
  const [analysis, setAnalysis] = useState<{ tenant: string; revision: number; data: CustomerAnalysis } | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    setAnalysis(null); setAnalysisError("");
    if (tenant) void apiFetch("/api/v1/customers/summary?period=all&page_size=1", { signal: abort.signal })
      .then(r => r.json()).then(data => {
        if (abort.signal.aborted) return;
        if (!data || typeof data.available !== "boolean" || !Array.isArray(data.segments) ||
          (data.summary && typeof data.summary.total_customers !== "number")) throw new Error("Invalid analysis");
        setAnalysis({ tenant, revision, data });
      }).catch(() => { if (!abort.signal.aborted) setAnalysisError(locale.startsWith("fr")
        ? "L’analyse de la source sélectionnée n’a pas pu être chargée." : "Could not load the selected source analysis."); });
    return () => abort.abort();
  }, [tenant, revision, locale]);
  const data = analysis?.tenant === tenant && analysis?.revision === revision ? analysis.data : null;
  const number = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value) : "—";


  const [campaignPrompt, setCampaignPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedCampaign, setGeneratedCampaign] = useState<{ content: string; provider: string } | null>(null);

  const [generationError, setGenerationError] = useState("");

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!campaignPrompt.trim()) return;
    const requestContext = contextRef.current;
    setGenerating(true);
    setGenerationError("");
    setGeneratedCampaign(null);
    try {
      const response = await apiFetch("/api/v1/media/generations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: campaignPrompt, kind: "marketing_text" }),
      });
      const payload: unknown = await response.json();
      if (!payload || typeof payload !== "object" ||
          !("output_text" in payload) || typeof payload.output_text !== "string" ||
          !payload.output_text.trim()) throw new Error("Invalid generation response");
      if (contextRef.current !== requestContext) return;
      setGeneratedCampaign({ content: payload.output_text,
        provider: "provider" in payload && typeof payload.provider === "string" ? payload.provider : "" });
    } catch (error) {
      if (contextRef.current !== requestContext) return;
      const fr = locale.startsWith("fr");
      setGenerationError(error instanceof ApiRequestError && error.status === 403
        ? (fr ? "Accès refusé. Vérifiez les permissions et l’activation de Marketing IA dans Mes modules." : "Access denied. Check permissions and Marketing AI activation in My modules.")
        : error instanceof ApiRequestError && error.status === 401
        ? (fr ? "Votre session a expiré. Reconnectez-vous." : "Your session expired. Sign in again.")
        : error instanceof ApiRequestError && error.status === 402
        ? (fr ? "Vérifiez votre abonnement et votre solde de crédits IA." : "Check your subscription and AI credit balance.")
        : (fr ? "La génération a échoué. Réessayez ou vérifiez la disponibilité du service IA." : "Generation failed. Retry or check AI service availability."));
    } finally {
      if (contextRef.current === requestContext) setGenerating(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400">
            <Megaphone size={22} />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
              {t.navigation.marketingAi}
            </h1>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
              {company.businessRecommendationsDescription}
            </p>
          </div>
        </div>

        <Link
          href="/connections"
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors self-start sm:self-auto"
        >
          <Plug size={14} />
          <span>{company.connectionsSynchronizedSource}</span>
        </Link>
      </div>

      {analysisError && <p role="alert" className="text-sm text-rose-600">{analysisError}</p>}
      <p role="status" className="text-xs text-slate-500">{data ? (data.available
        ? `${data.source_context?.name || (locale.startsWith("fr") ? "Source sélectionnée" : "Selected source")} · ${locale.startsWith("fr") ? "Historique complet disponible" : "Full available history"}`
        : company.analyticsUnavailable) : (analysisError || (locale.startsWith("fr") ? "Chargement de l’analyse…" : "Loading analysis…"))}</p>
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{locale.startsWith("fr") ? "Clients identifiés" : "Identified customers"}</span>
            <Users size={16} className="text-blue-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {number(data?.summary?.total_customers)}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {data?.available ? (locale.startsWith("fr") ? "Calculé sur la source sélectionnée" : "Calculated from selected source") : company.analyticsUnavailable}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{locale.startsWith("fr") ? "Clients actifs (30 derniers jours)" : "Active customers (last 30 days)"}</span>
            <Megaphone size={16} className="text-purple-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {number(data?.summary?.active_customers)}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {data?.available ? (locale.startsWith("fr") ? "Calculé sur la source sélectionnée" : "Calculated from selected source") : company.analyticsUnavailable}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{company.customersFrequency}</span>
            <Target size={16} className="text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {number(data?.summary?.purchase_frequency)}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {data?.available ? (locale.startsWith("fr") ? "Calculé sur la source sélectionnée" : "Calculated from selected source") : company.analyticsUnavailable}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{company.customersAverageValue}</span>
            <TrendingUp size={16} className="text-amber-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {number(data?.summary?.average_customer_value)} {data?.summary?.average_customer_value != null ? data.currency : ""}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {data?.available ? (locale.startsWith("fr") ? "Calculé sur la source sélectionnée" : "Calculated from selected source") : company.analyticsUnavailable}
          </div>
        </div>
      </div>

      {/* AI Campaign Generator */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="text-[#0076FF] dark:text-[#00D4FF]" size={18} />
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
            {t.copilot.title}
          </h2>
        </div>
        <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
          {t.copilot.subtitle}
        </p>

        <form onSubmit={handleGenerate} className="space-y-3">
          <div className="relative">
            <textarea
              value={campaignPrompt}
              onChange={(e) => setCampaignPrompt(e.target.value)}
              placeholder={t.copilot.inputPlaceholder}
              className="w-full p-3.5 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#0076FF] min-h-[90px]"
            />
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={generating || !campaignPrompt.trim()}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            >
              <Send size={13} className={generating ? "animate-spin" : ""} />
              <span>{generating ? t.copilot.statusThinking : t.copilot.sendButton}</span>
            </button>
          </div>
        </form>

        {generationError && <div role="alert" className="rounded-xl border border-rose-300 p-3 text-sm text-rose-700 dark:text-rose-300">
          <p>{generationError}</p><Link href="/workspace/modules" className="underline">{locale.startsWith("fr") ? "Mes modules" : "My modules"}</Link>
        </div>}
        {generatedCampaign && (
          <div className="mt-4 p-4 rounded-xl bg-blue-50/50 dark:bg-[#111D3D]/60 border border-blue-100 dark:border-blue-900/40 space-y-3 animate-in fade-in">
            <p className="text-xs font-bold text-slate-900 dark:text-white">
              {generatedCampaign.provider === "prompt_draft"
                ? (locale.startsWith("fr") ? "Brouillon basé sur votre consigne" : "Draft based on your prompt")
                : (locale.startsWith("fr") ? "Brouillon" : "Draft")}
            </p>
            <div className="p-3 rounded-lg bg-white dark:bg-[#0B132B] border border-slate-200/60 dark:border-white/[0.08] text-xs font-mono whitespace-pre-line text-slate-700 dark:text-slate-300">
              {generatedCampaign.content}
            </div>
          </div>
        )}
      </div>

      {/* Segments Overview */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
          {company.customersSegment}
        </h2>
        {data?.available && data.segments.length ? <ul className="grid gap-3 sm:grid-cols-3">{data.segments.map(segment =>
          <li key={segment.label} className="rounded-xl border p-4">
            <div className="flex items-center justify-between"><span>{locale.startsWith("fr") ? ({ dormant: "Inactifs", loyal: "Fidèles", vip: "VIP", regular: "Réguliers", high_value: "Forte valeur" } as Record<string, string>)[segment.label] || segment.label : segment.label}</span><strong>{number(segment.count)}</strong></div>
            <div role="img" aria-label={`${segment.label}: ${segment.count} / ${data.summary?.total_customers ?? 0}`} className="mt-3 h-3 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, Math.max(0, segment.count / Math.max(1, data.summary?.total_customers ?? 0) * 100))}%` }} />
            </div>
          </li>)}</ul>
          : <p className="text-sm text-slate-500">{company.analyticsUnavailable}</p>}
      </div>
    </div>
  );
}

"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Megaphone,
  Sparkles,
  Users,
  TrendingUp,
  Target,
  Send,
  Plus,
  ArrowUpRight,
  Mail,
  MessageSquare,
  Zap,
  Plug,
  CheckCircle2,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { apiFetch } from "@/lib/api-request";

export function MarketingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const company = getApplicationCatalog(locale).company;

  const [campaignPrompt, setCampaignPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedCampaign, setGeneratedCampaign] = useState<any>(null);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!campaignPrompt.trim()) return;
    setGenerating(true);
    try {
      const response = await apiFetch("/api/v1/media/generations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: campaignPrompt, kind: "marketing_text" }),
      });
      if (!response.ok) {
        setGeneratedCampaign({ content: locale.startsWith("fr") ? "Activez Marketing AI ou Media AI pour générer un brouillon réel." : "Activate Marketing AI or Media AI to generate a real draft." });
      } else {
        const payload = await response.json();
        setGeneratedCampaign({ content: payload.output_text, provider: payload.provider });
      }
    } finally {
      setGenerating(false);
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{company.customersActive}</span>
            <Users size={16} className="text-blue-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            0 {company.customersSearch}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {company.connectionsConnectedDataTitle}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{t.navigation.marketingAi}</span>
            <Megaphone size={16} className="text-purple-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            0 {company.connectionsProcessingError}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {company.businessRecommendationsDescription}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{company.customersFrequency}</span>
            <Target size={16} className="text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            —
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {company.analyticsUnavailable}
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{company.customersAverageValue}</span>
            <TrendingUp size={16} className="text-amber-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            —
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {company.salesForecastTitle}
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
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
              {t.marketing.loyalVip}
            </div>
            <div className="text-lg font-extrabold text-[#0076FF] dark:text-[#00D4FF] mt-1">
              {t.marketing.topPercent.replace(
                "{percent}",
                new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(0.15),
              )}
            </div>
            <div className="text-[11px] text-slate-400 mt-1">{t.marketing.repeatPurchase}</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">{t.marketing.churnRisk}</div>
            <div className="text-lg font-extrabold text-amber-600 dark:text-amber-400 mt-1">
              {company.customerSegmentDormant}
            </div>
            <div className="text-[11px] text-slate-400 mt-1">{t.marketing.lastPurchase60Days}</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">{t.marketing.abandonedCarts}</div>
            <div className="text-lg font-extrabold text-purple-600 dark:text-purple-400 mt-1">
              {t.marketing.reactivate}
            </div>
            <div className="text-[11px] text-slate-400 mt-1">{t.marketing.recentPurchaseIntent}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

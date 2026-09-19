"use client";

import React from "react";
import Link from "next/link";
import {
  Mic2,
  FileScan,
  MessagesSquare,
  Zap,
  Bot,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";

interface ModulePreviewProps {
  iconType?: "voice" | "ocr" | "chatbots" | "automations" | "agents";
  titleEn: string;
  titleFr: string;
  descriptionEn: string;
  descriptionFr: string;
  featuresEn: string[];
  featuresFr: string[];
  badge?: string;
  targetRelease?: string;
}

const iconMap = {
  voice: Mic2,
  ocr: FileScan,
  chatbots: MessagesSquare,
  automations: Zap,
  agents: Bot,
};

export function ModulePreview({
  iconType = "agents",
  titleEn,
  titleFr,
  descriptionEn,
  descriptionFr,
  featuresEn,
  featuresFr,
  badge = "Enterprise AI",
  targetRelease = "2026",
}: ModulePreviewProps) {
  const { locale } = useLocale();
  const isFr = locale === "fr";

  const Icon = iconMap[iconType] || Sparkles;
  const title = isFr ? titleFr : titleEn;
  const description = isFr ? descriptionFr : descriptionEn;
  const features = isFr ? featuresFr : featuresEn;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-8">
      {/* Top Banner */}
      <div className="bg-gradient-to-br from-blue-900/20 via-[#0B132B] to-[#060B13] border border-blue-500/20 rounded-3xl p-6 sm:p-10 relative overflow-hidden shadow-xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        
        <div className="relative z-10 space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-blue-500/10 border border-blue-400/30 text-[#0076FF] dark:text-[#00D4FF]">
              <Icon className="w-8 h-8" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-500/20 text-[#0076FF] dark:text-[#00D4FF] border border-blue-400/30 uppercase tracking-wider">
                  {badge}
                </span>
                <span className="text-xs text-slate-400 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {isFr ? `Disponible prochainement (${targetRelease})` : `Coming soon (${targetRelease})`}
                </span>
              </div>
              <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-slate-900 dark:text-white mt-1">
                {title}
              </h1>
            </div>
          </div>

          <p className="text-base sm:text-lg text-slate-600 dark:text-slate-300 max-w-2xl leading-relaxed">
            {description}
          </p>

          <div className="flex flex-wrap items-center gap-4 pt-2">
            <button
              disabled
              className="px-5 py-2.5 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-400 dark:text-slate-500 font-semibold text-sm cursor-not-allowed border border-slate-300 dark:border-white/[0.06] flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              {isFr ? "Accès anticipé restreint" : "Restricted Early Access"}
            </button>
            <Link
              href="/connections"
              className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-semibold text-sm transition-colors flex items-center gap-2 shadow-xs"
            >
              {isFr ? "Connecter vos données" : "Connect your data"}
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Planned Capabilities */}
      <div className="bg-white dark:bg-[#0B132B] rounded-2xl border border-slate-200/80 dark:border-white/[0.08] p-6 sm:p-8 shadow-xs space-y-6">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {isFr ? "Fonctionnalités au programme" : "Planned capabilities"}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {isFr
              ? "Ce module sera alimenté par vos données synchronisées sans aucune fuite entre organisations."
              : "This module will be directly powered by your synchronized datasets with complete tenant isolation."}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {features.map((feat, idx) => (
            <div
              key={idx}
              className="p-4 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06] flex items-start gap-3"
            >
              <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {feat}
              </span>
            </div>
          ))}
        </div>

        <div className="pt-4 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-[#0076FF]" />
            {isFr ? "Architecture scellée multi-tenant Avenqo" : "Avenqo isolated multi-tenant architecture"}
          </span>
          <Link href="/dashboard" className="text-[#0076FF] hover:underline font-medium">
            {isFr ? "Retour au tableau de bord" : "Return to dashboard"}
          </Link>
        </div>
      </div>
    </div>
  );
}

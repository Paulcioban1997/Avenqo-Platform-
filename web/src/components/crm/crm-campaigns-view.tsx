"use client";

import React from "react";
import Link from "next/link";
import { Megaphone, Mail, MessageSquare, Plus, ArrowRight, ShieldCheck } from "lucide-react";
import type { AppTranslations } from "@/lib/i18n/app-dictionary";

interface CRMCampaignsViewProps {
  t: AppTranslations;
}

export function CRMCampaignsView({ t }: CRMCampaignsViewProps) {
  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* CAMPAIGNS HEADER */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-[#0B132B] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {t.crm.tabs.campaigns || "Campagnes Marketing CRM"}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Relances omnicanales par courriel et SMS ciblés sur vos segments clients.
          </p>
        </div>
        <button
          disabled
          className="px-4 py-2 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-white/[0.06] text-slate-400 dark:text-slate-500 cursor-not-allowed flex items-center gap-2"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Nouvelle campagne</span>
        </button>
      </div>

      {/* CLEAN REAL EMPTY STATE — NO FAKE METRICS */}
      <div className="bg-white dark:bg-[#0B132B] p-10 rounded-2xl border border-slate-200 dark:border-slate-800 text-center flex flex-col items-center justify-center max-w-xl mx-auto space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900/50 flex items-center justify-center text-[#0076FF] dark:text-[#00D4FF]">
          <Megaphone className="w-7 h-7" />
        </div>
        <div className="space-y-1.5">
          <h3 className="text-base font-bold text-slate-900 dark:text-white">
            Aucune campagne marketing active
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Pour diffuser des campagnes personnalisées, configurez vos passerelles de messagerie (SMTP / Twilio) ou associez vos audiences depuis l'espace Intégrations.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full pt-2 text-left">
          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/80 dark:border-white/[0.06] space-y-1">
            <div className="flex items-center gap-2 text-slate-800 dark:text-slate-200 font-semibold text-xs">
              <Mail className="w-3.5 h-3.5 text-[#0076FF]" />
              <span>Campagnes Courriel</span>
            </div>
            <p className="text-[11px] text-slate-400">
              Relances automatisées 24h avant rendez-vous et anniversaires clients.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/80 dark:border-white/[0.06] space-y-1">
            <div className="flex items-center gap-2 text-slate-800 dark:text-slate-200 font-semibold text-xs">
              <MessageSquare className="w-3.5 h-3.5 text-[#00D4FF]" />
              <span>Notifications SMS</span>
            </div>
            <p className="text-[11px] text-slate-400">
              Confirmations instantanées et rappels de présence sans intermédiaire.
            </p>
          </div>
        </div>

        <div className="pt-2">
          <Link
            href="/integrations"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#0076FF] dark:text-[#00D4FF] hover:underline"
          >
            <span>Configurer les passerelles dans Intégrations</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}

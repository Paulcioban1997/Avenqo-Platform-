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

export function MarketingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [campaignPrompt, setCampaignPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedCampaign, setGeneratedCampaign] = useState<any>(null);

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!campaignPrompt.trim()) return;
    setGenerating(true);
    setTimeout(() => {
      setGeneratedCampaign({
        title: "Campagne Flash — Réactivation Clients",
        subject: "Offre Spéciale Exclusivité Avenqo pour Vous",
        channel: "Email & SMS",
        target_segment: "Clients inactifs > 30 jours",
        predicted_roi: "3.8x",
        content: `Bonjour,\n\nNous avons remarqué que vous n'aviez pas visité notre boutique récemment. Profitez d'un avantage exceptionnel de 15 % sur votre prochaine commande avec le code FLASH15.\n\nÀ très vite sur notre boutique !`,
      });
      setGenerating(false);
    }, 900);
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
              {t.navigation?.marketingAi || "Marketing & Croissance IA"}
            </h1>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
              Génération de campagnes automatisées, segmentation prédictive de clients et optimisation du ROI.
            </p>
          </div>
        </div>

        <Link
          href="/connections"
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors self-start sm:self-auto"
        >
          <Plug size={14} />
          <span>Synchroniser l'audience</span>
        </Link>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Audience Qualifiée</span>
            <Users size={16} className="text-blue-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            0 contact
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Basé sur vos données connectées
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Campagnes Actives</span>
            <Megaphone size={16} className="text-purple-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            0 en cours
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Automatisations multicanales
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Taux de Conversion Prédit</span>
            <Target size={16} className="text-emerald-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            3.4 %
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Optimisation algorithmique IA
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>ROI Moyen Espéré</span>
            <TrendingUp size={16} className="text-amber-500" />
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            4.2x
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Retour sur investissement prévu
          </div>
        </div>
      </div>

      {/* AI Campaign Generator */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="text-[#0076FF] dark:text-[#00D4FF]" size={18} />
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
            Générateur de Campagnes IA
          </h2>
        </div>
        <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
          Décrivez votre objectif marketing (relance de paniers abandonnés, promotion de rentrée, offre VIP) et l'IA créera une campagne ciblée sur mesure.
        </p>

        <form onSubmit={handleGenerate} className="space-y-3">
          <div className="relative">
            <textarea
              value={campaignPrompt}
              onChange={(e) => setCampaignPrompt(e.target.value)}
              placeholder="Exemple: Créer une campagne e-mail pour relancer les clients qui n'ont rien acheté depuis 30 jours avec une réduction de 10% sur les nouveaux produits..."
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
              <span>{generating ? "Génération en cours..." : "Générer la campagne IA"}</span>
            </button>
          </div>
        </form>

        {generatedCampaign && (
          <div className="mt-4 p-4 rounded-xl bg-blue-50/50 dark:bg-[#111D3D]/60 border border-blue-100 dark:border-blue-900/40 space-y-3 animate-in fade-in">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900 dark:text-white">
                {generatedCampaign.title}
              </span>
              <span className="px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 text-[10px] font-bold">
                ROI estimé: {generatedCampaign.predicted_roi}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-600 dark:text-slate-300">
              <div>
                <strong>Canal :</strong> {generatedCampaign.channel}
              </div>
              <div>
                <strong>Segment :</strong> {generatedCampaign.target_segment}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-white dark:bg-[#0B132B] border border-slate-200/60 dark:border-white/[0.08] text-xs font-mono whitespace-pre-line text-slate-700 dark:text-slate-300">
              {generatedCampaign.content}
            </div>
          </div>
        )}
      </div>

      {/* Segments Overview */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
          Segments Prédits de l'Audience
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">Clients Fidèles & VIP</div>
            <div className="text-lg font-extrabold text-[#0076FF] dark:text-[#00D4FF] mt-1">
              Top 15 %
            </div>
            <div className="text-[11px] text-slate-400 mt-1">Panier moyen supérieur, fort réachat</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">À Risque d'Attrition</div>
            <div className="text-lg font-extrabold text-amber-600 dark:text-amber-400 mt-1">
              Dormants
            </div>
            <div className="text-[11px] text-slate-400 mt-1">Dernier achat il y a plus de 60 jours</div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">Paniers Abandonnés</div>
            <div className="text-lg font-extrabold text-purple-600 dark:text-purple-400 mt-1">
              À Réactiver
            </div>
            <div className="text-[11px] text-slate-400 mt-1">Intention d'achat récente non concrétisée</div>
          </div>
        </div>
      </div>
    </div>
  );
}

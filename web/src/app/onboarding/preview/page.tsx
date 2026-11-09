"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Building2,
  Layers,
  ShoppingBag,
  TrendingUp,
  DollarSign,
  ShoppingCart,
  Users,
  Percent,
  Sparkles,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  FileText,
  Sliders,
  Calendar,
  AlertCircle,
  Eye,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingPreviewPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [state, setState] = useState<any>(null);

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          setState(data);
        }
      } catch (err) {
        console.error("Erreur de chargement aperçu:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const handleContinue = () => {
    router.push("/onboarding/contracts");
  };

  const handleEditDesign = () => {
    router.push("/onboarding/design");
  };

  if (isLoading || !state) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Génération de l'aperçu dynamique…
      </div>
    );
  }

  const design = state.design || {};
  const companyInfo = state.company_info || {};
  const selectedModules = state.modules?.selected_modules || ["retail", "crm"];
  const displayName = design.display_name || companyInfo.commercial_name || "Mon Entreprise";
  const primaryColor = design.primary_color || "#0076FF";
  const secondaryColor = design.secondary_color || "#0B132B";
  const accentColor = design.accent_color || "#00D4FF";

  return (
    <OnboardingWizardLayout
      currentStepIndex={4}
      title={copy.preview.title}
      subtitle={copy.preview.subtitle}
      onNext={handleContinue}
      nextLabel={copy.preview.proceedToContracts}
    >
      <div className="space-y-6">
        {/* Banner: Données de démonstration */}
        <div className="p-4 rounded-2xl bg-blue-950/40 border border-blue-500/30 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-600/20 text-[#00D4FF] border border-blue-500/30 shrink-0">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs font-bold text-white block">
                {copy.preview.bannerNotice}
              </span>
              <span className="text-[11px] text-slate-400">
                Couleur d'accent : <span style={{ color: primaryColor }} className="font-mono font-bold">{primaryColor}</span> · Thème actif : <span className="font-bold text-white">{design.theme_id}</span>
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleEditDesign}
            className="px-4 py-2 rounded-xl border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs font-semibold text-white transition-colors cursor-pointer shrink-0"
          >
            {copy.preview.editDesign}
          </button>
        </div>

        {/* Live Workspace Mock Screen Container */}
        <div
          className="rounded-2xl border border-white/10 overflow-hidden shadow-2xl flex flex-col md:flex-row min-h-[580px]"
          style={{ backgroundColor: secondaryColor }}
        >
          {/* Mock Sidebar */}
          <div className="w-full md:w-64 bg-black/40 border-r border-white/[0.06] p-4 flex flex-col justify-between shrink-0">
            <div className="space-y-6">
              {/* Tenant Header with Logo */}
              <div className="flex items-center gap-3 pb-4 border-b border-white/[0.06]">
                {design.company_logo_url ? (
                  <img
                    src={design.company_logo_url}
                    alt={displayName}
                    className="w-9 h-9 rounded-xl object-contain bg-white/5 border border-white/10 p-1"
                  />
                ) : (
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-white shadow-sm"
                    style={{ backgroundColor: primaryColor }}
                  >
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                )}
                <div className="truncate">
                  <div className="text-sm font-extrabold text-white truncate">{displayName}</div>
                  <div className="text-[9px] font-semibold text-slate-400 uppercase tracking-widest">
                    Avenqo Workspace
                  </div>
                </div>
              </div>

              {/* Navigation Items (Only Selected Modules) */}
              <div className="space-y-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 px-3 mb-2">
                  Opérations
                </div>

                <div
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-white"
                  style={{ backgroundColor: `${primaryColor}25`, borderLeft: `3px solid ${primaryColor}` }}
                >
                  <TrendingUp className="w-4 h-4" style={{ color: primaryColor }} />
                  <span>Tableau de bord</span>
                </div>

                {selectedModules.includes("retail") && (
                  <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-white/[0.04]">
                    <ShoppingBag className="w-4 h-4 text-slate-400" />
                    <span>Retail IA</span>
                  </div>
                )}

                {selectedModules.includes("crm") && (
                  <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-white/[0.04]">
                    <Users className="w-4 h-4 text-slate-400" />
                    <span>CRM IA</span>
                  </div>
                )}

                {selectedModules.includes("voice") && (
                  <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-white/[0.04]">
                    <Sliders className="w-4 h-4 text-slate-400" />
                    <span>Voice AI</span>
                  </div>
                )}

                {selectedModules.includes("ocr") && (
                  <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-white/[0.04]">
                    <FileText className="w-4 h-4 text-slate-400" />
                    <span>OCR Documents</span>
                  </div>
                )}
              </div>
            </div>

            {/* Central AI Banner inside Sidebar */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center gap-2 mt-4">
              <Sparkles className="w-4 h-4 text-[#00D4FF]" />
              <div className="text-[11px]">
                <span className="font-bold text-white block">Central Avenqo IA</span>
                <span className="text-[9px] text-slate-400">Actif & disponible</span>
              </div>
            </div>
          </div>

          {/* Mock Dashboard Workspace */}
          <div className="flex-1 p-6 space-y-6 overflow-y-auto bg-black/20">
            {/* Topbar Greeting */}
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-4">
              <div>
                <h2 className="text-lg font-bold text-white">
                  Bonjour, {companyInfo.authorized_rep_first_name || "Directeur"}
                </h2>
                <p className="text-xs text-slate-400">
                  Vue synthétique consolidée de {displayName}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                  Espace Prêt
                </span>
              </div>
            </div>

            {/* Mock KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <span>Chiffre d'affaires</span>
                  <DollarSign className="w-4 h-4" style={{ color: primaryColor }} />
                </div>
                <div className="text-xl font-bold text-white">124 500,00 $</div>
                <div className="text-[11px] text-emerald-400 mt-1 font-semibold">+14.2% vs période préc.</div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <span>Commandes</span>
                  <ShoppingCart className="w-4 h-4" style={{ color: accentColor }} />
                </div>
                <div className="text-xl font-bold text-white">1 482</div>
                <div className="text-[11px] text-emerald-400 mt-1 font-semibold">+8.5% vs période préc.</div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <span>Ratio Client / Vente</span>
                  <Percent className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-xl font-bold text-white">4.8%</div>
                <div className="text-[11px] text-slate-400 mt-1">Ratio indicatif d'activité</div>
              </div>
            </div>

            {/* Mock Combined Chart & Avenqo Insights */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 p-5 rounded-xl bg-white/[0.03] border border-white/[0.08] space-y-4">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white">Tendance Mensuelle Consolidée</span>
                  <span className="text-slate-400">12 derniers mois</span>
                </div>
                {/* Mock Chart Bar Lines */}
                <div className="h-32 flex items-end justify-between gap-2 pt-4 px-2">
                  {[40, 55, 45, 65, 80, 75, 90, 85, 95, 110, 105, 125].map((h, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <div
                        className="w-full rounded-t transition-all"
                        style={{ height: `${h}%`, backgroundColor: primaryColor }}
                      />
                      <span className="text-[9px] text-slate-500 font-mono">M{i + 1}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-5 rounded-xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 text-xs font-bold text-white mb-2">
                    <Sparkles className="w-4 h-4 text-[#00D4FF]" />
                    <span>Recommandation Central AI</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Vos modules configurés sont prêts à synchroniser vos flux commerciaux dès
                    votre première connexion.
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-white/[0.06] text-[10px] text-slate-400">
                  Niveau de confiance IA : 99.8%
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}


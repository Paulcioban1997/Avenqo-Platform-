"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Sparkles,
  Building2,
  Layers,
  Palette,
  CreditCard,
  ShieldCheck,
  ArrowRight,
  TrendingUp,
  FileCheck,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingCompletePage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [isActivating, setIsActivating] = useState(false);
  const [activationResult, setActivationResult] = useState<any>(null);
  const [state, setState] = useState<any>(null);

  useEffect(() => {
    async function activateAndLoad() {
      try {
        const headers = getAuthHeaders();
        // 1. Charger l'état actuel
        const stateRes = await apiFetch("/api/v1/onboarding/state", { headers });
        if (stateRes.ok) {
          const stateData = await stateRes.json();
          setState(stateData);

          // 2. Finaliser et activer
          setIsActivating(true);
          const finalizeRes = await apiFetch("/api/v1/onboarding/finalize", {
            method: "POST",
            headers,
          });
          if (finalizeRes.ok) {
            const finalData = await finalizeRes.json();
            setActivationResult(finalData);
          }
        }
      } catch (err) {
        console.error("Erreur de finalisation:", err);
      } finally {
        setIsLoading(false);
        setIsActivating(false);
      }
    }
    void activateAndLoad();
  }, []);

  const handleGoToDashboard = () => {
    router.push("/dashboard");
  };

  if (isLoading || !state) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Activation définitive de votre environnement d'affaires…
      </div>
    );
  }

  const companyInfo = state.company_info || {};
  const design = state.design || {};
  const selectedModules = activationResult?.activated_modules || state.modules?.selected_modules || ["retail", "crm"];
  const planCode = activationResult?.plan_code || state.subscription?.selected_plan || "professional";
  const planName = planCode === "base" ? "Base" : "Professional";
  const monthlyCredits = planCode === "base" ? "6 500" : "20 000";

  return (
    <OnboardingWizardLayout
      currentStepIndex={8}
      title={copy.complete.title}
      subtitle={copy.complete.subtitle}
      onNext={handleGoToDashboard}
      nextLabel={copy.navigation.goToDashboard}
    >
      <div className="max-w-3xl mx-auto space-y-8 animate-in fade-in duration-300">
        {/* Celebration Header Card */}
        <div className="p-8 rounded-3xl bg-gradient-to-b from-[#0076FF]/20 via-[#0B132B] to-[#060B13] border border-[#0076FF]/40 text-center space-y-4 shadow-2xl relative overflow-hidden">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-cyan-400 text-white flex items-center justify-center mx-auto shadow-lg shadow-blue-500/30">
            <CheckCircle2 className="w-9 h-9 stroke-[2.5]" />
          </div>

          <div className="space-y-1">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Votre Espace Entreprise est Actif
            </h2>
            <p className="text-sm text-slate-300 max-w-lg mx-auto">
              L'infrastructure isolée, les permissions de rôles et vos modules autorisés sont
              désormais prêts pour vos premières opérations.
            </p>
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={handleGoToDashboard}
              className="px-8 py-3.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 active:scale-[0.98] text-base font-bold text-white shadow-xl shadow-blue-500/30 transition-all inline-flex items-center gap-2.5 cursor-pointer"
            >
              <span>{copy.navigation.goToDashboard}</span>
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Recap Grid */}
        <div className="p-6 sm:p-8 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] space-y-6 shadow-xl">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#00D4FF]" />
            <span>{copy.complete.recapTitle}</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Identity */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center gap-3.5">
              {design.company_logo_url ? (
                <img
                  src={design.company_logo_url}
                  alt="Logo"
                  className="w-10 h-10 rounded-xl object-contain bg-white/5 p-1 border border-white/10"
                />
              ) : (
                <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold">
                  <Building2 className="w-5 h-5" />
                </div>
              )}
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  Organisation
                </span>
                <span className="text-sm font-bold text-white">
                  {companyInfo.commercial_name || "Entreprise"}
                </span>
              </div>
            </div>

            {/* Plan */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center justify-center">
                <CreditCard className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  Abonnement
                </span>
                <span className="text-sm font-bold text-white">
                  Plan {planName} · {monthlyCredits} crédits IA / mois
                </span>
              </div>
            </div>

            {/* Theme & Style */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center justify-center">
                <Palette className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  Thème & Style
                </span>
                <span className="text-sm font-bold text-white">
                  {design.theme_id || "Avenqo Obsidian"} ({design.mode === "light" ? "Clair" : "Sombre"})
                </span>
              </div>
            </div>

            {/* Contracts */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 flex items-center justify-center">
                <FileCheck className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  Conformité Légale
                </span>
                <span className="text-sm font-bold text-white">
                  Accords signés & horodatés UTC
                </span>
              </div>
            </div>
          </div>

          {/* Activated Modules Badges */}
          <div className="pt-4 border-t border-white/[0.06]">
            <span className="text-xs font-semibold text-slate-400 block mb-3">
              Modules Métier Activés :
            </span>
            <div className="flex flex-wrap gap-2">
              <span className="px-3 py-1 rounded-xl bg-blue-500/20 text-[#00D4FF] border border-blue-500/30 text-xs font-bold flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                Central AI (Inclus)
              </span>
              {selectedModules.map((m: string) => (
                <span
                  key={m}
                  className="px-3 py-1 rounded-xl bg-white/[0.04] border border-white/[0.08] text-xs font-semibold text-slate-200 capitalize"
                >
                  {m === "retail"
                    ? "Retail Intelligence"
                    : m === "crm"
                    ? "CRM IA"
                    : m === "voice"
                    ? "Voice AI"
                    : m === "ocr"
                    ? "OCR Documents"
                    : m === "marketing"
                    ? "Marketing AI"
                    : m === "accounting"
                    ? "Accounting AI"
                    : m}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}

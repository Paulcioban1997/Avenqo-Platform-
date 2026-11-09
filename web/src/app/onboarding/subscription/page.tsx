"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  CreditCard,
  Check,
  Sparkles,
  Zap,
  Building2,
  Shield,
  Layers,
  ArrowRight,
  AlertTriangle,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingSubscriptionPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [selectedPlan, setSelectedPlan] = useState<"base" | "professional">("professional");
  const [currency, setCurrency] = useState("CAD");
  const [selectedModules, setSelectedModules] = useState<string[]>(["retail", "crm"]);

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.subscription?.selected_plan) {
            const p = data.subscription.selected_plan.toLowerCase();
            if (p === "base" || p === "professional") {
              setSelectedPlan(p);
            }
          }
          if (data.modules?.selected_modules) {
            setSelectedModules(data.modules.selected_modules);
          }
          if (data.company_info?.country !== "Canada") {
            setCurrency("USD");
          }
        }
      } catch (err) {
        console.error("Erreur de chargement plan:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const handleSelectPlan = (plan: "base" | "professional") => {
    setSelectedPlan(plan);
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/step/subscription", {
        method: "PUT",
        headers,
        body: JSON.stringify({
          plan_code: selectedPlan,
          billing_cycle: "monthly",
          currency: currency,
        }),
      });
      if (res.ok) {
        setSaveStatus("saved");
        router.push("/onboarding/checkout");
      }
    } catch (err) {
      console.error("Erreur de sauvegarde plan:", err);
      setSaveStatus("idle");
    }
  };

  const maxAllowed = selectedPlan === "base" ? 2 : 5;
  const isModuleCountExceeded = selectedModules.length > maxAllowed;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Chargement des offres d'abonnement…
      </div>
    );
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={6}
      title={copy.subscription.title}
      subtitle={copy.subscription.subtitle}
      onNext={() => void handleSaveAndContinue()}
      nextLabel="Procéder au Paiement Sécurisé"
      saveStatus={saveStatus}
    >
      <div className="space-y-8">
        {/* Module reconciliation warning if needed */}
        {isModuleCountExceeded && (
          <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-200">
              <span className="font-bold block text-sm text-amber-300 mb-0.5">
                Ajustement de votre sélection de modules
              </span>
              Vous avez présélectionné {selectedModules.length} modules, alors que le plan Base
              en inclut 2 au choix. En choisissant Base, vos 2 premiers modules prioritaires seront
              activés, ou vous pouvez opter pour l'offre Professional (jusqu'à 5 modules inclus).
            </div>
          </div>
        )}

        {/* Currency Switcher */}
        <div className="flex items-center justify-end gap-2 text-xs">
          <span className="text-slate-400 font-semibold">Devise de facturation :</span>
          <div className="bg-slate-900 border border-white/10 rounded-xl p-1 flex items-center gap-1">
            <button
              type="button"
              onClick={() => setCurrency("CAD")}
              className={`px-3 py-1 rounded-lg font-bold text-xs transition-colors ${
                currency === "CAD" ? "bg-[#0076FF] text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              CAD ($)
            </button>
            <button
              type="button"
              onClick={() => setCurrency("USD")}
              className={`px-3 py-1 rounded-lg font-bold text-xs transition-colors ${
                currency === "USD" ? "bg-[#0076FF] text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              USD ($)
            </button>
          </div>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* BASE PLAN */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => handleSelectPlan("base")}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleSelectPlan("base");
              }
            }}
            className={`p-6 sm:p-8 rounded-2xl border transition-all text-left flex flex-col justify-between cursor-pointer select-none ${
              selectedPlan === "base"
                ? "bg-[#0B132B] border-[#0076FF] shadow-xl shadow-blue-500/20 ring-2 ring-[#0076FF]"
                : "bg-[#0B132B]/60 border-white/[0.08] hover:border-white/20 hover:bg-[#0B132B]"
            }`}
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Offre Essentielle
                </span>
                {selectedPlan === "base" && (
                  <span className="px-2.5 py-1 rounded-full bg-blue-500/20 text-[#00D4FF] border border-blue-500/30 text-xs font-bold">
                    Sélectionné
                  </span>
                )}
              </div>

              <h3 className="text-2xl font-extrabold text-white">Base</h3>
              <p className="text-xs text-slate-400 mt-1">
                Pour petites entreprises souhaitant digitaliser leurs opérations clés.
              </p>

              <div className="mt-6 mb-6 pb-6 border-b border-white/[0.08]">
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-extrabold text-white">
                    {currency === "CAD" ? "29,99 $" : "21,99 $"}
                  </span>
                  <span className="text-xs text-slate-400 font-semibold">
                    {currency} / mois
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Facturé mensuellement · Sans engagement</div>
              </div>

              <ul className="space-y-3 text-xs text-slate-300">
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span><strong>2 modules métier inclus</strong> au choix</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span><strong>6 500 crédits IA inclus</strong> chaque mois</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Central AI inclus sans restriction</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Jusqu'à 3 utilisateurs & 1 agent vocal</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Imports de données volumineux jusqu'à <strong>250 Mo</strong></span>
                </li>
              </ul>
            </div>
          </div>

          {/* PROFESSIONAL PLAN */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => handleSelectPlan("professional")}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleSelectPlan("professional");
              }
            }}
            className={`p-6 sm:p-8 rounded-2xl border transition-all text-left flex flex-col justify-between cursor-pointer select-none relative overflow-hidden ${
              selectedPlan === "professional"
                ? "bg-[#0B132B] border-[#0076FF] shadow-2xl shadow-blue-500/25 ring-2 ring-[#0076FF]"
                : "bg-[#0B132B]/60 border-white/[0.08] hover:border-white/20 hover:bg-[#0B132B]"
            }`}
          >
            {/* Top highlight ribbon */}
            <div className="absolute top-0 right-0 bg-gradient-to-l from-blue-600 to-[#0076FF] text-white text-[10px] font-extrabold uppercase px-4 py-1 rounded-bl-xl shadow-xs">
              Recommandé Fondateur
            </div>

            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-[#00D4FF]">
                  Performance Complète
                </span>
                {selectedPlan === "professional" && (
                  <span className="px-2.5 py-1 rounded-full bg-blue-500/20 text-[#00D4FF] border border-blue-500/30 text-xs font-bold mr-16">
                    Sélectionné
                  </span>
                )}
              </div>

              <h3 className="text-2xl font-extrabold text-white">Professional</h3>
              <p className="text-xs text-slate-400 mt-1">
                La suite complète multi-modules pour automatiser la croissance.
              </p>

              <div className="mt-6 mb-6 pb-6 border-b border-white/[0.08]">
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-extrabold text-white">
                    {currency === "CAD" ? "49,99 $" : "36,99 $"}
                  </span>
                  <span className="text-xs text-slate-400 font-semibold">
                    {currency} / mois
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Facturé mensuellement · Sans engagement</div>
              </div>

              <ul className="space-y-3 text-xs text-slate-300">
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span><strong>Jusqu'à 5 modules inclus</strong> simultanément</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span><strong>20 000 crédits IA inclus</strong> chaque mois</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Voice AI avec 3 agents et 2 appels simultanés</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Jusqu'à 10 utilisateurs & 3 sites d'exploitation</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Imports jusqu'à <strong>250 Mo</strong> & priorité d'inférence IA</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Enterprise Banner on quote */}
        <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 shrink-0">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-white">Besoin d'un déploiement sur mesure ?</h4>
              <p className="text-xs text-slate-400 mt-0.5">
                L'offre Enterprise propose des instances isolées, formation dédiée et volumétrie sans plafond.
              </p>
            </div>
          </div>

          <a
            href="mailto:contact@avenqo.ca?subject=Demande%20Enterprise"
            className="px-4 py-2 rounded-xl border border-white/10 hover:bg-white/[0.04] text-xs font-semibold text-slate-200 transition-colors shrink-0 text-center"
          >
            {copy.subscription.contactSales}
          </a>
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}

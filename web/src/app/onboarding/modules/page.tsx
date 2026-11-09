"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Layers,
  Sparkles,
  ShoppingBag,
  Users,
  PhoneCall,
  FileSearch,
  Megaphone,
  Calculator,
  Workflow,
  Scale,
  Bot,
  Video,
  CheckCircle2,
  Calendar,
  Info,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

interface BusinessModuleItem {
  key: string;
  name: string;
  description: string;
  category: string;
  icon: any;
  isAvailable: boolean;
  integrations: string;
  isPremium?: boolean;
}

const AVAILABLE_MODULES: BusinessModuleItem[] = [
  {
    key: "retail",
    name: "Retail Intelligence",
    description: "Analyse prédictive des ventes, gestion intelligente des stocks et alertes d'anomalies en temps réel.",
    category: "Commerce",
    icon: ShoppingBag,
    isAvailable: true,
    integrations: "Shopify, WooCommerce, CSV, Parquet",
  },
  {
    key: "crm",
    name: "CRM IA & Relations Clients",
    description: "Fiches clients unifiées, historique commercial, scoring et copilot commercial automatisé.",
    category: "Clients",
    icon: Users,
    isAvailable: true,
    integrations: "Google Calendar, Outlook, Hubspot",
  },
  {
    key: "voice",
    name: "Voice AI & Standard Téléphonique",
    description: "Agent vocal conversationnel 24/7 capable de répondre, filtrer les appels et réserver des rendez-vous.",
    category: "Communication",
    icon: PhoneCall,
    isAvailable: true,
    integrations: "Telnyx, Retell, Numéros locaux dédiés",
    isPremium: true,
  },
  {
    key: "ocr",
    name: "OCR & Traitement Documentaire",
    description: "Numérisation et extraction intelligente des factures, contrats, reçus et bordereaux d'expédition.",
    category: "Documents",
    icon: FileSearch,
    isAvailable: true,
    integrations: "PDF, Scans, Multi-pages, JSON",
  },
  {
    key: "marketing",
    name: "Marketing AI",
    description: "Génération automatique de campagnes ciblées, newsletters et fiches produits indexées sur votre catalogue.",
    category: "Croissance",
    icon: Megaphone,
    isAvailable: true,
    integrations: "Meta Ads, Google Ads, Mailchimp",
  },
  {
    key: "accounting",
    name: "Accounting AI",
    description: "Rapprochement bancaire intelligent, pré-comptabilisation et détection automatique des écarts fiscaux.",
    category: "Finance",
    icon: Calculator,
    isAvailable: true,
    integrations: "QuickBooks, Xero, Formats bancaires",
  },
  {
    key: "workflow",
    name: "Automations & Workflows",
    description: "Déclencheurs, conditions et actions automatisées entre vos données, le CRM et vos applications externes.",
    category: "Opérations",
    icon: Workflow,
    isAvailable: true,
    integrations: "Webhooks, API REST, Central Avenqo",
  },
  {
    key: "legal",
    name: "Legal AI",
    description: "Analyse assistée de conformité contractuelle, clauses sensibles et révision documentaire rapide.",
    category: "Juridique",
    icon: Scale,
    isAvailable: true,
    integrations: "Accords SaaS, NDA, Loi 25 / RGPD",
  },
  {
    key: "ai_agents",
    name: "Agents Spécialisés",
    description: "Flotte d'assistants autonomes affectés aux opérations quotidiennes de votre entreprise.",
    category: "IA Avancée",
    icon: Bot,
    isAvailable: true,
    integrations: "Central AI, Workspace Tools",
    isPremium: true,
  },
  {
    key: "media",
    name: "Media & Studio AI",
    description: "Génération de contenus multimodaux et scripts de présentation de marque sécurisés.",
    category: "Contenu",
    icon: Video,
    isAvailable: true,
    integrations: "Banque d'actifs, Historique",
  },
  {
    key: "appointments",
    name: "Prise de Rendez-vous Avancée",
    description: "Module dédié à la réservation de consultations. Actuellement disponible dans le CRM IA.",
    category: "Opérations",
    icon: Calendar,
    isAvailable: false,
    integrations: "Inclus dans CRM IA",
  },
];

export default function OnboardingModulesPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [selectedModules, setSelectedModules] = useState<string[]>(["retail", "crm"]);

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          if (data.modules?.selected_modules && Array.isArray(data.modules.selected_modules)) {
            if (data.modules.selected_modules.length > 0) {
              setSelectedModules(data.modules.selected_modules);
            }
          }
        }
      } catch (err) {
        console.error("Erreur de chargement modules:", err);
      } finally {
        setIsLoading(false);
      }
    }
    void fetchState();
  }, []);

  const toggleModule = (key: string, isAvailable: boolean) => {
    if (!isAvailable) return;
    setSelectedModules((prev) =>
      prev.includes(key) ? prev.filter((m) => m !== key) : [...prev, key]
    );
  };

  const handleSaveAndContinue = async () => {
    setSaveStatus("saving");
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/step/modules", {
        method: "PUT",
        headers,
        body: JSON.stringify({ selected_modules: selectedModules }),
      });
      if (res.ok) {
        setSaveStatus("saved");
        router.push("/onboarding/design");
      }
    } catch (err) {
      console.error("Erreur de sauvegarde modules:", err);
      setSaveStatus("idle");
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Chargement des modules…
      </div>
    );
  }

  return (
    <OnboardingWizardLayout
      currentStepIndex={2}
      title={copy.modules.title}
      subtitle={copy.modules.subtitle}
      onNext={() => void handleSaveAndContinue()}
      isNextDisabled={selectedModules.length === 0}
      saveStatus={saveStatus}
    >
      <div className="space-y-6">
        {/* Banner: Central AI inclus sans surcoût */}
        <div className="p-4 rounded-2xl bg-gradient-to-r from-blue-900/30 via-indigo-950/40 to-cyan-950/30 border border-blue-500/30 flex items-start gap-3 shadow-lg">
          <div className="p-2 rounded-xl bg-blue-600/20 text-[#00D4FF] border border-blue-500/40 shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="text-xs">
            <span className="font-bold text-white block text-sm mb-0.5">
              Central AI Inclus d'Office
            </span>
            <p className="text-slate-300 leading-relaxed">
              {copy.modules.centralAiNotice} L'orchestration intelligente coordonne tous vos modules
              activés et donne accès aux outils unifiés.
            </p>
          </div>
        </div>

        {/* Selected count info bar */}
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Sélection en cours :
            </span>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-500/20 text-[#00D4FF] border border-blue-500/30 text-xs font-bold">
              {selectedModules.length} {copy.modules.selectedCount}
            </span>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">
            Vous pourrez ajuster cette sélection lors du choix de l'abonnement.
          </span>
        </div>

        {/* Modules Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {AVAILABLE_MODULES.map((mod) => {
            const Icon = mod.icon;
            const isSelected = selectedModules.includes(mod.key);

            return (
              <div
                key={mod.key}
                role="button"
                tabIndex={0}
                onClick={() => toggleModule(mod.key, mod.isAvailable)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleModule(mod.key, mod.isAvailable);
                  }
                }}
                className={`p-5 rounded-2xl border transition-all text-left flex flex-col justify-between select-none ${
                  !mod.isAvailable
                    ? "opacity-50 bg-white/[0.02] border-white/[0.04] cursor-not-allowed"
                    : isSelected
                    ? "bg-[#0B132B] border-[#0076FF] shadow-md shadow-blue-500/15 cursor-pointer ring-1 ring-[#0076FF]"
                    : "bg-[#0B132B]/60 border-white/[0.08] hover:border-white/20 hover:bg-[#0B132B] cursor-pointer"
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                          isSelected
                            ? "bg-[#0076FF] text-white"
                            : "bg-white/[0.06] text-slate-300"
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-bold text-white text-sm">{mod.name}</h3>
                          {mod.isPremium && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold uppercase">
                              Pro / IA
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-slate-400">{mod.category}</span>
                      </div>
                    </div>

                    <div
                      className={`w-6 h-6 rounded-lg flex items-center justify-center border transition-colors ${
                        isSelected
                          ? "bg-[#0076FF] border-[#0076FF] text-white"
                          : "border-white/20 bg-white/[0.02]"
                      }`}
                    >
                      {isSelected && <CheckCircle2 className="w-4 h-4" />}
                    </div>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">{mod.description}</p>
                </div>

                <div className="mt-4 pt-3 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400">
                  <span className="truncate max-w-[200px]">Connexions : {mod.integrations}</span>
                  {!mod.isAvailable && (
                    <span className="text-amber-400 font-semibold">Bientôt disponible</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}


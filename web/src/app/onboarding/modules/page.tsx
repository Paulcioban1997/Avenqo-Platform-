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
  Check,
  Building2,
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
    description: "Agent vocal conversationnel 24/7 capable de répondre, filtrer les appels et assister les employés au travail.",
    category: "Communication",
    icon: PhoneCall,
    isAvailable: true,
    integrations: "Telnyx, Retell, Numéros locaux dédiés",
    isPremium: true,
  },
  {
    key: "hr",
    name: "Ressources Humaines (HR AI)",
    description: "Organigramme d'équipe, fiches de poste & SOPs métiers, compétences, congés et coaching vocal.",
    category: "Ressources Humaines",
    icon: Users,
    isAvailable: true,
    integrations: "Hiérarchie d'entreprise, NIP vocal, Rituels d'équipe, Suivi des tâches",
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

function getSectorRecommendedModuleKeys(industry: string): string[] {
  const s = (industry || "").toLowerCase();
  if (s.includes("auto") || s.includes("mécani") || s.includes("garage")) {
    return ["voice", "crm", "hr", "ocr", "accounting"];
  }
  if (s.includes("construct") || s.includes("bâtiment") || s.includes("rénov")) {
    return ["voice", "crm", "hr", "ocr", "accounting"];
  }
  if (s.includes("beaut") || s.includes("coiff") || s.includes("esthét") || s.includes("spa")) {
    return ["voice", "crm", "hr", "marketing"];
  }
  if (s.includes("santé") || s.includes("médic") || s.includes("clinique")) {
    return ["voice", "crm", "hr", "ocr"];
  }
  if (s.includes("transport") || s.includes("logist")) {
    return ["voice", "crm", "hr", "ocr", "accounting"];
  }
  // Default Commerce / Retail
  return ["retail", "crm", "voice", "accounting", "marketing", "hr"];
}

export default function OnboardingModulesPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "idle">("idle");
  const [industryName, setIndustryName] = useState<string>("Commerce & Détail");
  const [selectedModules, setSelectedModules] = useState<string[]>(["retail", "crm", "voice", "hr"]);

  useEffect(() => {
    async function fetchState() {
      try {
        const headers = getAuthHeaders();
        const res = await apiFetch("/api/v1/onboarding/state", { headers });
        if (res.ok) {
          const data = await res.json();
          const ind = data.company_info?.industry || "Commerce & Détail";
          setIndustryName(ind);

          const recommended = getSectorRecommendedModuleKeys(ind);
          if (data.modules?.selected_modules && Array.isArray(data.modules.selected_modules) && data.modules.selected_modules.length > 0) {
            setSelectedModules(data.modules.selected_modules);
          } else {
            // Pre-select sector recommended modules
            setSelectedModules(recommended);
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

  const recommendedKeys = getSectorRecommendedModuleKeys(industryName);

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
        {/* Sector AI Recommendations Banner */}
        <div className="p-4 rounded-2xl bg-gradient-to-r from-blue-900/40 via-indigo-950/40 to-cyan-950/40 border border-blue-500/30 flex items-start justify-between flex-wrap gap-4 shadow-lg">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-xl bg-blue-600/20 text-[#00D4FF] border border-blue-500/40 shrink-0 mt-0.5">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="text-sm font-bold text-white">
                  Recommandations IA pour votre secteur : <span className="text-[#00D4FF]">{industryName}</span>
                </h4>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Adapté à votre métier
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                Les modules ci-dessous ont été pré-sélectionnés pour maximiser la rentabilité de votre entreprise,
                automatiser le support téléphonique et outiller vos collaborateurs sans alourdir vos coûts.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSelectedModules(recommendedKeys)}
            className="px-3 py-1.5 rounded-xl text-xs font-bold bg-[#0076FF] hover:bg-blue-600 text-white transition shrink-0"
          >
            Activer la sélection recommandée ({recommendedKeys.length})
          </button>
        </div>

        {/* Modules Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {AVAILABLE_MODULES.map((mod) => {
            const isSelected = selectedModules.includes(mod.key);
            const isRecommended = recommendedKeys.includes(mod.key);
            const Icon = mod.icon;

            return (
              <div
                key={mod.key}
                onClick={() => toggleModule(mod.key, mod.isAvailable)}
                className={`relative rounded-2xl p-5 border transition-all flex flex-col justify-between ${
                  !mod.isAvailable
                    ? "opacity-50 cursor-not-allowed bg-slate-900/20 border-white/[0.04]"
                    : isSelected
                    ? "bg-[#0B132B] border-[#0076FF] ring-2 ring-blue-500/30 shadow-xl cursor-pointer"
                    : "bg-[#0B132B]/50 border-white/[0.08] hover:border-white/20 hover:bg-[#0B132B] cursor-pointer"
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className={`p-2.5 rounded-xl ${
                          isSelected
                            ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/30"
                            : "bg-slate-900 text-slate-400 border border-white/10"
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-white">{mod.name}</h4>
                          {mod.isPremium && (
                            <span className="text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                              Pro
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                          {mod.category}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {isRecommended && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          Recommandé
                        </span>
                      )}
                      <div
                        className={`w-5 h-5 rounded-md flex items-center justify-center transition-colors ${
                          isSelected
                            ? "bg-[#0076FF] text-white"
                            : "border border-white/20 bg-slate-900/60"
                        }`}
                      >
                        {isSelected && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-slate-400 leading-relaxed">{mod.description}</p>
                </div>

                <div className="pt-4 border-t border-white/[0.06] mt-4 flex items-center justify-between text-[11px] text-slate-500">
                  <span>Intégrations : {mod.integrations}</span>
                  {!mod.isAvailable && <span className="italic">Bientôt disponible</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </OnboardingWizardLayout>
  );
}

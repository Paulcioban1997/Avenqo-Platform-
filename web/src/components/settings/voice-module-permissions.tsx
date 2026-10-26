"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Store,
  Calendar,
  Users,
  Lock,
  Check,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  Sparkles,
  RefreshCw,
  Sliders,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { VOICE_PERMISSIONS_COPY } from "@/lib/i18n/voice-permissions-copy";

interface VoiceActionGrant {
  action_code: string;
  granted: boolean;
  locked: boolean;
  tools: string[];
}
interface VoiceModuleGrant {
  module_code: string;
  active: boolean;
  locked: boolean;
  actions: VoiceActionGrant[];
}
interface VoiceModulePermissions {
  modules: VoiceModuleGrant[];
}

interface CapabilityDefinition {
  id: string;
  title: { fr: string; en: string };
  description: { fr: string; en: string };
  explanation: { fr: string; en: string };
  icon: typeof Store;
  actionCodes: string[];
  moduleCodes: string[];
  isSensitive?: boolean;
}

const CAPABILITIES: CapabilityDefinition[] = [
  {
    id: "retail_catalog",
    title: {
      fr: "Produits et stocks",
      en: "Products and inventory",
    },
    description: {
      fr: "Votre IA peut renseigner les clients sur votre catalogue et les disponibilités.",
      en: "Your AI can answer customer questions about your catalog and stock availability.",
    },
    explanation: {
      fr: "Permet à l'assistante de vérifier les fiches produits, prix et niveaux de stock pour répondre aux appelants en direct.",
      en: "Allows the assistant to check product listings, prices, and stock levels to answer callers directly.",
    },
    icon: Store,
    actionCodes: ["read_products", "read_inventory", "retail.products.query"],
    moduleCodes: ["retail"],
  },
  {
    id: "crm_appointments",
    title: {
      fr: "Rendez-vous et réservations",
      en: "Appointments and bookings",
    },
    description: {
      fr: "Votre IA peut trouver des créneaux et gérer des réservations.",
      en: "Your AI can check available slots and book appointments in your calendar.",
    },
    explanation: {
      fr: "Permet de vérifier les disponibilités, créer, modifier ou annuler des rendez-vous selon vos horaires d'ouverture réels.",
      en: "Allows checking open slots, creating, modifying, or cancelling appointments according to your actual business hours.",
    },
    icon: Calendar,
    actionCodes: [
      "read_availability",
      "list_slots",
      "create_appointment",
      "update_appointment",
      "cancel_appointment",
      "crm.appointments.view",
      "crm.appointments.create",
    ],
    moduleCodes: ["crm", "appointments"],
  },
  {
    id: "customer_service",
    title: {
      fr: "Service clientèle et accueil",
      en: "Customer service and company info",
    },
    description: {
      fr: "Votre IA répond aux questions sur votre entreprise.",
      en: "Your AI answers questions about your business, hours, and contact details.",
    },
    explanation: {
      fr: "Renseigne les clients sur votre secteur, vos horaires d'ouverture physiques, vos coordonnées et vos politiques commerciales.",
      en: "Informs callers about your domain, physical store hours, contact information, and business policies.",
    },
    icon: Users,
    actionCodes: ["read_client_self", "business.info.query", "read"],
    moduleCodes: ["crm", "retail", "marketing"],
  },
  {
    id: "internal_insights",
    title: {
      fr: "Informations internes (Sécurisé par NIP)",
      en: "Internal business insights (PIN secured)",
    },
    description: {
      fr: "Vos employés autorisés peuvent consulter certaines informations privées.",
      en: "Your authorized staff can consult select private business summaries.",
    },
    explanation: {
      fr: "Réservé exclusivement aux employés et gestionnaires munis de leur code NIP personnel. Vos clients et appelants externes n'y ont jamais accès.",
      en: "Restricted strictly to employees with their personal voice PIN. Callers and customers never have access to this information.",
    },
    icon: Lock,
    actionCodes: ["read_sales_summary", "read_cashflow", "read_business_health", "read_crm_metrics", "read_unpaid_invoices"],
    moduleCodes: ["retail", "accounting", "crm"],
    isSensitive: true,
  },
];

export function VoiceModulePermissionsSection({
  tenantId,
  canManage,
}: {
  tenantId: string | undefined;
  canManage: boolean;
}) {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const copy = VOICE_PERMISSIONS_COPY[locale];
  const [data, setData] = useState<VoiceModulePermissions | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  useEffect(() => {
    if (!tenantId || !canManage) return;
    const controller = new AbortController();
    queueMicrotask(async () => {
      try {
        const response = await fetch("/api/v1/voice/module-permissions", {
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.ok && !controller.signal.aborted) {
          const payload = await response.json();
          if (Array.isArray(payload?.modules)) setData(payload);
        }
      } catch {
        /* keep last known state */
      }
    });
    return () => controller.abort();
  }, [tenantId, canManage]);

  // Determine granted status per human capability
  const capabilityStates = useMemo(() => {
    if (!data?.modules) return {};
    const states: Record<string, { granted: boolean; locked: boolean; totalActions: number; grantedActions: number }> = {};

    for (const cap of CAPABILITIES) {
      let total = 0;
      let grantedCount = 0;
      let isLocked = false;

      for (const module of data.modules) {
        for (const action of module.actions) {
          if (cap.actionCodes.includes(action.action_code)) {
            total++;
            if (action.granted) grantedCount++;
            if (action.locked) isLocked = true;
          }
        }
      }

      states[cap.id] = {
        granted: total > 0 && grantedCount > 0,
        locked: isLocked && total === 0,
        totalActions: total,
        grantedActions: grantedCount,
      };
    }
    return states;
  }, [data]);

  // Toggle all actions in a capability
  async function toggleCapability(capability: CapabilityDefinition, targetGranted: boolean) {
    if (!data?.modules || busy) return;
    setBusy(true);

    const grants: Array<{ module_code: string; action_code: string; granted: boolean }> = [];

    for (const module of data.modules) {
      for (const action of module.actions) {
        if (capability.actionCodes.includes(action.action_code) && !action.locked) {
          grants.push({
            module_code: module.module_code,
            action_code: action.action_code,
            granted: targetGranted,
          });
        }
      }
    }

    if (grants.length === 0) {
      setBusy(false);
      return;
    }

    try {
      const response = await fetch("/api/v1/voice/module-permissions", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Requested-With": "avenqo-web" },
        body: JSON.stringify({ grants }),
      });
      if (response.ok) {
        const payload = await response.json();
        if (Array.isArray(payload?.modules)) setData(payload);
      }
    } finally {
      setBusy(false);
    }
  }

  // Toggle individual granular action (advanced mode)
  async function toggleSingleAction(module_code: string, action_code: string, granted: boolean) {
    setBusy(true);
    try {
      const response = await fetch("/api/v1/voice/module-permissions", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Requested-With": "avenqo-web" },
        body: JSON.stringify({ grants: [{ module_code, action_code, granted }] }),
      });
      if (response.ok) {
        const payload = await response.json();
        if (Array.isArray(payload?.modules)) setData(payload);
      }
    } finally {
      setBusy(false);
    }
  }

  if (!canManage || !Array.isArray(data?.modules)) return null;

  return (
    <section className="space-y-5 rounded-3xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] p-6 sm:p-7 shadow-xs">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-white/[0.06] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider bg-blue-50 text-[#0076FF] dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/40">
              {fr ? "Capacités de l'assistante" : "AI Capabilities"}
            </span>
            <span className="text-xs text-slate-400">
              {fr ? "Protection B2B intégrée" : "Enterprise protection"}
            </span>
          </div>
          <h3 className="text-base font-extrabold text-slate-900 dark:text-white mt-1">
            {copy.title}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            {copy.description}
          </p>
        </div>

        {busy && (
          <div className="flex items-center gap-2 text-xs font-semibold text-[#0076FF] animate-pulse">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            <span>{fr ? "Mise à jour sécurisée..." : "Updating..."}</span>
          </div>
        )}
      </div>

      {/* 4 HUMAN CAPABILITY CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CAPABILITIES.map((cap) => {
          const Icon = cap.icon;
          const state = capabilityStates[cap.id] || { granted: false, locked: false, totalActions: 0, grantedActions: 0 };
          const isEnabled = state.granted;

          return (
            <div
              key={cap.id}
              onClick={() => {
                if (!state.locked && !busy) {
                  void toggleCapability(cap, !isEnabled);
                }
              }}
              className={`p-5 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between select-none ${
                isEnabled
                  ? "border-[#0076FF] bg-blue-50/30 dark:bg-blue-950/20 shadow-xs shadow-blue-500/5"
                  : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-slate-50/40 dark:bg-slate-900/40"
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                        isEnabled
                          ? "bg-[#0076FF] text-white shadow-sm shadow-blue-500/20"
                          : "bg-slate-200 dark:bg-slate-800 text-slate-500"
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                        {fr ? cap.title.fr : cap.title.en}
                      </h4>
                      {cap.isSensitive && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 dark:text-amber-400 mt-0.5">
                          <Lock className="w-3 h-3" />
                          {fr ? "NIP requis" : "PIN required"}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* CUSTOM TOGGLE SWITCH */}
                  <div
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                      isEnabled ? "bg-[#0076FF]" : "bg-slate-300 dark:bg-slate-700"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                        isEnabled ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </div>
                </div>

                {/* PRIMARY BUSINESS STATEMENT */}
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-3 leading-snug">
                  {fr ? cap.description.fr : cap.description.en}
                </p>

                {/* DETAILED EXPLANATION */}
                <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed">
                  {fr ? cap.explanation.fr : cap.explanation.en}
                </p>
              </div>

              {/* STATUS FOOTER */}
              <div className="pt-3 mt-3 border-t border-slate-100 dark:border-white/[0.04] flex items-center justify-between text-[10px] font-bold">
                <span
                  className={
                    isEnabled
                      ? "text-emerald-700 dark:text-emerald-400 flex items-center gap-1"
                      : "text-slate-400 dark:text-slate-500"
                  }
                >
                  {isEnabled && <Check className="w-3 h-3" />}
                  {isEnabled
                    ? fr
                      ? "Capacité active"
                      : "Capability active"
                    : fr
                    ? "Désactivé"
                    : "Disabled"}
                </span>

                <span className="text-slate-400 font-mono text-[9px]">
                  {fr ? "Sécurisé côté serveur" : "Server enforced"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* COLLAPSIBLE ADVANCED TECHNICAL DETAILS (FOR AUDITORS / DEVS) */}
      <details className="pt-2 border-t border-slate-100 dark:border-white/[0.06] group">
        <summary className="text-[11px] font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1.5 transition cursor-pointer select-none py-1">
          <Sliders className="w-3.5 h-3.5 text-slate-400" />
          <span>
            {fr
              ? "Détails techniques et permissions avancées (optionnel pour développeurs)"
              : "Technical details and granular permissions (optional for developers)"}
          </span>
        </summary>

        <div className="mt-4 p-4 rounded-2xl bg-slate-50/70 dark:bg-slate-900/60 border border-slate-200/60 dark:border-white/[0.06] space-y-4">
          <p className="text-[11px] text-slate-500 leading-relaxed">
            {copy.description}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.modules
              .filter((module) => module.actions.length > 0)
              .map((module) => (
                <div key={module.module_code} className="space-y-2 p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200/70 dark:border-slate-800">
                  <div className="text-xs font-mono font-bold text-slate-800 dark:text-slate-200 flex items-center justify-between">
                    <span>{module.module_code}</span>
                    {module.locked && (
                      <span className="text-[10px] text-amber-600 font-sans font-bold">
                        {copy.locked}
                      </span>
                    )}
                  </div>
                  <div className="space-y-1.5 pt-1">
                    {module.actions.map((action) => (
                      <label key={action.action_code} className="flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
                        <input
                          type="checkbox"
                          value={action.action_code}
                          disabled={busy || action.locked}
                          checked={action.granted}
                          onChange={(e) => void toggleSingleAction(module.module_code, action.action_code, e.target.checked)}
                          className="rounded border-slate-300 text-[#0076FF] focus:ring-0"
                        />
                        <span>
                          {action.action_code}
                          {action.locked ? ` (${copy.moduleOff})` : ""}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        </div>
      </details>
    </section>
  );
}

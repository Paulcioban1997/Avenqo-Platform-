"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Sparkles,
  Layers,
  CheckCircle,
  ExternalLink,
  Settings,
  RefreshCw,
  Power,
  ShieldCheck,
  Calendar,
  ShoppingBag,
  Mic2,
  FileScan,
  ReceiptText,
  Megaphone,
  Zap,
  Globe,
  CreditCard,
  PhoneCall,
  Check,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

type ModuleEntitlement = {
  key: string;
  display_name: string;
  description: string;
  availability: string;
  active: boolean;
  state: string;
  premium: boolean;
  category: string;
};

type EntitlementsPayload = {
  plan_code: string;
  active_modules: string[];
  module_limit: number | null;
  remaining_module_slots: number | null;
  modules: ModuleEntitlement[];
};

type IntegrationItem = {
  id: string;
  name: string;
  provider: string;
  category: "ecommerce" | "calendar" | "payment" | "telephony" | "advertising";
  descriptionFr: string;
  descriptionEn: string;
  status: "connected" | "disconnected" | "action_required" | "coming_soon";
  statusTextFr: string;
  statusTextEn: string;
  logoUrl?: string;
  icon?: typeof Globe;
  configureUrl: string;
};

const EXTERNAL_INTEGRATIONS: IntegrationItem[] = [
  {
    id: "shopify",
    name: "Shopify",
    provider: "shopify",
    category: "ecommerce",
    descriptionFr: "Synchronisation des commandes, catalogue produits, stocks et clients en direct.",
    descriptionEn: "Live sync of orders, product catalog, inventory, and customer accounts.",
    status: "action_required",
    statusTextFr: "Action requise (Reconnexion)",
    statusTextEn: "Action Required (Reconnect)",
    configureUrl: "/connections",
  },
  {
    id: "woocommerce",
    name: "WooCommerce",
    provider: "woocommerce",
    category: "ecommerce",
    descriptionFr: "Importation continue des paniers et transactions e-commerce WordPress.",
    descriptionEn: "Continuous import of WordPress e-commerce orders and cart data.",
    status: "disconnected",
    statusTextFr: "Déconnecté",
    statusTextEn: "Disconnected",
    configureUrl: "/connections",
  },
  {
    id: "google_calendar",
    name: "Google Calendar",
    provider: "google",
    category: "calendar",
    descriptionFr: "Synchronisation bidirectionnelle des rendez-vous et détection des indisponibilités.",
    descriptionEn: "Two-way appointment synchronization and busy slot detection.",
    status: "connected",
    statusTextFr: "Connecté (Sync active)",
    statusTextEn: "Connected (Sync active)",
    configureUrl: "/crm",
  },
  {
    id: "outlook",
    name: "Microsoft Outlook",
    provider: "microsoft",
    category: "calendar",
    descriptionFr: "Intégration d'agenda Office 365 pour les professionnels et équipes.",
    descriptionEn: "Office 365 calendar integration for enterprise schedules.",
    status: "disconnected",
    statusTextFr: "Non configuré",
    statusTextEn: "Not configured",
    configureUrl: "/crm",
  },
  {
    id: "stripe",
    name: "Stripe",
    provider: "stripe",
    category: "payment",
    descriptionFr: "Paiement en ligne sécurisé, facturation périodique et prélèvements automatiques.",
    descriptionEn: "Secure online payments, recurring billing, and automated customer charges.",
    status: "connected",
    statusTextFr: "Connecté (Mode Sandbox)",
    statusTextEn: "Connected (Sandbox mode)",
    configureUrl: "/billing",
  },
  {
    id: "telnyx",
    name: "Telnyx Telephony",
    provider: "telnyx",
    category: "telephony",
    descriptionFr: "Attribution de numéros d'affaires, Webhooks de téléphonie et routage d'appels.",
    descriptionEn: "Business phone numbers, telephony webhooks, and Voice AI call control.",
    status: "connected",
    statusTextFr: "Connecté (Sandbox simulée)",
    statusTextEn: "Connected (Simulated Sandbox)",
    configureUrl: "/settings/voice",
  },
  {
    id: "meta_ads",
    name: "Meta Ads (Facebook & Instagram)",
    provider: "meta",
    category: "advertising",
    descriptionFr: "Publication de campagnes et suivi de retour sur investissement publicitaire.",
    descriptionEn: "Campaign publishing and ROAS tracking across Meta networks.",
    status: "coming_soon",
    statusTextFr: "En attente d'approbation Meta",
    statusTextEn: "Pending Meta Approval",
    configureUrl: "/marketing",
  },
];

const MODULE_ICONS: Record<string, typeof Globe> = {
  crm: Calendar,
  retail: ShoppingBag,
  accounting: ReceiptText,
  voice: Mic2,
  ocr: FileScan,
  legal: FileScan,
  marketing: Megaphone,
  workflow: Zap,
};

export function MarketplaceView() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");

  const [entitlements, setEntitlements] = useState<EntitlementsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "modules" | "integrations">("all");
  const [togglingKey, setTogglingKey] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/api/v1/modules/entitlements");
      if (response.ok) {
        setEntitlements(await response.json());
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.publicMessage || (fr ? "Erreur de chargement." : "Load error."));
      } else {
        setError(fr ? "Erreur serveur." : "Server error.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleToggleModule = async (moduleKey: string, currentlyActive: boolean) => {
    setTogglingKey(moduleKey);
    setError("");
    const action = currentlyActive ? "deactivate" : "activate";
    try {
      const response = await apiFetch(`/api/v1/modules/${moduleKey}/${action}`, {
        method: "POST",
      });
      if (response.ok) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("avenqo:sources-changed"));
        }
        await loadData();
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.publicMessage || (fr ? "Opération non autorisée." : "Operation unauthorized."));
      } else {
        setError(fr ? "Échec de modification du module." : "Failed to toggle module.");
      }
    } finally {
      setTogglingKey(null);
    }
  };

  const planCode = entitlements?.plan_code || "professional";
  const activeCount = entitlements?.active_modules.length || 0;
  const limitCount = entitlements?.module_limit;

  return (
    <div className="mx-auto max-w-6xl space-y-7 animate-in fade-in duration-300">
      {/* HEADER */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
              Avenqo Marketplace
            </span>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
              Plan {planCode.toUpperCase()} · {activeCount}{limitCount ? ` / ${limitCount}` : ""} {fr ? "modules actifs" : "active"}
            </span>
          </div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {fr ? "Catalogue des Modules & Intégrations" : "Modules & Integrations Marketplace"}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {fr
              ? "Activez les modules de votre forfait et gérez vos connecteurs externes."
              : "Activate your entitled modules and manage external commerce and calendar connectors."}
          </p>
        </div>

        <button
          onClick={() => void loadData()}
          disabled={loading}
          className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
          title={fr ? "Actualiser" : "Refresh"}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </header>

      {error && (
        <div role="alert" className="p-4 rounded-2xl border border-rose-200 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-sm flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* FILTER TABS */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab("all")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
            activeTab === "all"
              ? "bg-[#0076FF] text-white shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          {fr ? "Tous les éléments" : "All Items"}
        </button>
        <button
          onClick={() => setActiveTab("modules")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
            activeTab === "modules"
              ? "bg-[#0076FF] text-white shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          {fr ? "Modules Métier Avenqo" : "Avenqo Business Modules"}
        </button>
        <button
          onClick={() => setActiveTab("integrations")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
            activeTab === "integrations"
              ? "bg-[#0076FF] text-white shadow-xs"
              : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          {fr ? "Connecteurs Externes" : "External Connectors"}
        </button>
      </div>

      {/* SECTION 1: BUSINESS MODULES */}
      {(activeTab === "all" || activeTab === "modules") && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#0076FF]" />
              <span>{fr ? "Modules Métier Intelligents" : "Intelligent Business Modules"}</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {(entitlements?.modules || []).map((mod) => {
              const Icon = MODULE_ICONS[mod.key] || Sparkles;
              const isToggling = togglingKey === mod.key;

              return (
                <div
                  key={mod.key}
                  className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-5 shadow-xs flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-700 transition"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-blue-50 dark:bg-blue-950 text-[#0076FF] dark:text-[#00D4FF]">
                          <Icon className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="font-extrabold text-slate-900 dark:text-white text-sm">
                            {mod.display_name}
                          </h3>
                          <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                            {mod.category}
                          </span>
                        </div>
                      </div>

                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        mod.active
                          ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300"
                          : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                      }`}>
                        {mod.active ? (fr ? "Actif" : "Active") : (fr ? "Inclus" : "Included")}
                      </span>
                    </div>

                    <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                      {mod.description}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                    <Link
                      href={`/${mod.key === "workflow" ? "automations" : mod.key}`}
                      className="text-xs font-bold text-[#0076FF] hover:underline"
                    >
                      {fr ? "Accéder au module" : "Open module"}
                    </Link>

                    <button
                      onClick={() => void handleToggleModule(mod.key, mod.active)}
                      disabled={isToggling}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition ${
                        mod.active
                          ? "bg-rose-50 text-rose-600 dark:bg-rose-950/40 hover:bg-rose-100"
                          : "bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-xs"
                      }`}
                    >
                      {isToggling ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Power className="w-3.5 h-3.5" />
                      )}
                      <span>
                        {mod.active
                          ? fr ? "Désactiver" : "Deactivate"
                          : fr ? "Activer" : "Activate"}
                      </span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* SECTION 2: EXTERNAL INTEGRATIONS */}
      {(activeTab === "all" || activeTab === "integrations") && (
        <section className="space-y-4 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
              <Globe className="w-4 h-4 text-purple-600" />
              <span>{fr ? "Connecteurs & Intégrations Externes" : "External Connectors & Integrations"}</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {EXTERNAL_INTEGRATIONS.map((conn) => {
              const statusPillClass =
                conn.status === "connected"
                  ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
                  : conn.status === "action_required"
                  ? "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800"
                  : conn.status === "coming_soon"
                  ? "bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-200 dark:border-slate-700";

              return (
                <div
                  key={conn.id}
                  className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-5 shadow-xs flex flex-col justify-between hover:border-slate-300 dark:hover:border-slate-700 transition"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-purple-50 dark:bg-purple-950 text-purple-600">
                          <Globe className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="font-extrabold text-slate-900 dark:text-white text-sm">
                            {conn.name}
                          </h3>
                          <span className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                            {conn.category}
                          </span>
                        </div>
                      </div>

                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${statusPillClass}`}>
                        {fr ? conn.statusTextFr : conn.statusTextEn}
                      </span>
                    </div>

                    <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                      {fr ? conn.descriptionFr : conn.descriptionEn}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                    <span className="text-[11px] text-slate-400">
                      {conn.status === "connected"
                        ? fr ? "Opérationnel" : "Operational"
                        : conn.status === "action_required"
                        ? fr ? "Configuration requise" : "Config needed"
                        : fr ? "Non lié" : "Unlinked"}
                    </span>

                    <Link
                      href={conn.configureUrl}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                    >
                      <Settings className="w-3.5 h-3.5" />
                      <span>{fr ? "Configurer" : "Configure"}</span>
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

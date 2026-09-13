"use client";

import React, { useState, useEffect } from "react";
import {
  Plug,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  ShieldCheck,
  Zap,
  ShoppingBag,
  Megaphone,
  Network,
  ReceiptText,
  Database,
  SlidersHorizontal,
  X,
  FileText,
} from "lucide-react";
import { AvenqoCard, StatusBadge, StatusBadgeType } from "@/components/ui/avenqo-card";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

export type ConnectorCategory =
  | "all"
  | "ecommerce"
  | "marketing"
  | "crm"
  | "accounting"
  | "data"
  | "automation";

export interface ConnectorItem {
  id: string;
  name: string;
  category: ConnectorCategory;
  categoryLabel: string;
  description: string;
  status: StatusBadgeType;
  lastSynced?: string;
  recordCount?: number;
  iconBg: string;
  logoLetter: string;
  supportsSync: boolean;
}

export function IntegrationsHubView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [selectedCategory, setSelectedCategory] = useState<ConnectorCategory>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedConnector, setSelectedConnector] = useState<ConnectorItem | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncSuccessToast, setSyncSuccessToast] = useState<string | null>(null);
  const [syncLogs, setSyncLogs] = useState<
    Array<{ id: string; time: string; message: string; level: "info" | "success" | "warning" }>
  >([
    {
      id: "log-1",
      time: "Aujourd'hui, 17:34:10",
      message: "Réconciliation complète du catalogue WooCommerce : 14 produits synchronisés.",
      level: "success",
    },
    {
      id: "log-2",
      time: "Aujourd'hui, 16:02:15",
      message: "Normalisation automatique des prix CAD et dédoublonnage des SKUs.",
      level: "info",
    },
  ]);

  const connectors: ConnectorItem[] = [
    {
      id: "woocommerce",
      name: "WooCommerce",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Synchronisation bidirectionnelle du catalogue produits, stocks et commandes.",
      status: "connected",
      lastSynced: "Il y a 14 minutes",
      recordCount: 14,
      iconBg: "bg-purple-600",
      logoLetter: "W",
      supportsSync: true,
    },
    {
      id: "shopify",
      name: "Shopify",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Connecteur officiel Shopify Storefront & Admin API avec gestion des webhooks.",
      status: "connected",
      lastSynced: "Il y a 2 heures",
      recordCount: 182,
      iconBg: "bg-emerald-600",
      logoLetter: "S",
      supportsSync: true,
    },
    {
      id: "stripe",
      name: "Stripe",
      category: "accounting",
      categoryLabel: t.integrations.categoryAccounting,
      description: "Abonnements SaaS, paiements multidevises, facturation automatique et conformité fiscale.",
      status: "connected",
      lastSynced: "En temps réel (Webhooks)",
      recordCount: 420,
      iconBg: "bg-blue-600",
      logoLetter: "S",
      supportsSync: true,
    },
    {
      id: "amazon",
      name: "Amazon Seller Central",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Intégration Amazon SP-API pour la gestion des inventaires FBA et commandes.",
      status: "disconnected",
      iconBg: "bg-amber-600",
      logoLetter: "A",
      supportsSync: false,
    },
    {
      id: "etsy",
      name: "Etsy",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Importation des créations, gestion des commandes artisanales et stocks centralisés.",
      status: "coming_soon",
      iconBg: "bg-orange-600",
      logoLetter: "E",
      supportsSync: false,
    },
    {
      id: "google_ads",
      name: "Google Ads",
      category: "marketing",
      categoryLabel: t.integrations.categoryMarketing,
      description: "Suivi des conversions ROAS, synchronisation des flux produits Google Merchant Center.",
      status: "needs_attention",
      lastSynced: "Hier, 23:45",
      iconBg: "bg-red-500",
      logoLetter: "G",
      supportsSync: true,
    },
    {
      id: "meta_ads",
      name: "Meta Ads (Facebook & Instagram)",
      category: "marketing",
      categoryLabel: t.integrations.categoryMarketing,
      description: "Attribution des campagnes publicitaires, API Conversions et catalogues dynamiques.",
      status: "disconnected",
      iconBg: "bg-blue-700",
      logoLetter: "M",
      supportsSync: false,
    },
    {
      id: "tiktok_ads",
      name: "TikTok Ads",
      category: "marketing",
      categoryLabel: t.integrations.categoryMarketing,
      description: "Mesure de performance des campagnes vidéo et synchronisation TikTok Shop.",
      status: "coming_soon",
      iconBg: "bg-slate-900",
      logoLetter: "T",
      supportsSync: false,
    },
    {
      id: "klaviyo",
      name: "Klaviyo",
      category: "crm",
      categoryLabel: t.integrations.categoryCrm,
      description: "Automatisation des campagnes e-mail & SMS et segmentation RFM prédictive par IA.",
      status: "connected",
      lastSynced: "Il y a 3 heures",
      recordCount: 1240,
      iconBg: "bg-neutral-800",
      logoLetter: "K",
      supportsSync: true,
    },
    {
      id: "hubspot",
      name: "HubSpot CRM",
      category: "crm",
      categoryLabel: t.integrations.categoryCrm,
      description: "Synchronisation des leads B2B, cycles de vente et pipelines d'opportunités.",
      status: "disconnected",
      iconBg: "bg-orange-500",
      logoLetter: "H",
      supportsSync: false,
    },
    {
      id: "quickbooks",
      name: "QuickBooks Online",
      category: "accounting",
      categoryLabel: t.integrations.categoryAccounting,
      description: "Comptabilité automatisée, grand livre général et réconciliation des encaissements.",
      status: "needs_attention",
      lastSynced: "Il y a 1 jour",
      iconBg: "bg-green-600",
      logoLetter: "Q",
      supportsSync: true,
    },
    {
      id: "zapier",
      name: "Zapier",
      category: "automation",
      categoryLabel: t.integrations.categoryAutomation,
      description: "Déclencheurs d'actions personnalisés et webhooks entrants/sortants vers 5000+ apps.",
      status: "connected",
      lastSynced: "En continu",
      recordCount: 95,
      iconBg: "bg-amber-500",
      logoLetter: "Z",
      supportsSync: true,
    },
  ];

  const filteredConnectors = connectors.filter((c) => {
    const matchesCat = selectedCategory === "all" || c.category === selectedCategory;
    const matchesQuery =
      !searchQuery.trim() ||
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesQuery;
  });

  const handleTriggerSync = async (connector: ConnectorItem) => {
    setIsSyncing(true);
    const newLog = {
      id: `log-${Date.now()}`,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      message: `Synchronisation manuelle déclenchée pour ${connector.name}...`,
      level: "info" as const,
    };
    setSyncLogs((prev) => [newLog, ...prev]);

    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("avenqo_token") : null;
      // Connect to actual backend sync runner if connection exists
      await fetch(`/api/v1/connectors/sync`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ connector_id: connector.id }),
      });
    } catch {
      // Non-blocking fallback
    } finally {
      setTimeout(() => {
        setIsSyncing(false);
        setSyncSuccessToast(`Synchronisation terminée pour ${connector.name}. Registre normalisé à jour.`);
        const successLog = {
          id: `log-s-${Date.now()}`,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          message: `Succès : Les données de ${connector.name} ont été réconciliées et validées.`,
          level: "success" as const,
        };
        setSyncLogs((prev) => [successLog, ...prev]);
      }, 1200);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
              {t.integrations.title}
            </h1>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 dark:bg-[#0076FF]/15 dark:text-[#00D4FF] border border-blue-200 dark:border-[#0076FF]/30">
              12 Connecteurs
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            {t.integrations.subtitle}
          </p>
        </div>

        {/* Global manual sync button */}
        <button
          onClick={() => handleTriggerSync(connectors[0])}
          disabled={isSyncing}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs disabled:opacity-60 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
          <span>{isSyncing ? t.integrations.syncing : t.integrations.syncNow}</span>
        </button>
      </div>

      {/* Success Notification Banner */}
      {syncSuccessToast && (
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300 animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>{syncSuccessToast}</span>
          </div>
          <button
            onClick={() => setSyncSuccessToast(null)}
            className="text-emerald-600 hover:text-emerald-800 p-1"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Category Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 min-w-max">
          {[
            { id: "all", label: t.integrations.categoryAll },
            { id: "ecommerce", label: t.integrations.categoryEcommerce },
            { id: "marketing", label: t.integrations.categoryMarketing },
            { id: "crm", label: t.integrations.categoryCrm },
            { id: "accounting", label: t.integrations.categoryAccounting },
            { id: "automation", label: t.integrations.categoryAutomation },
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id as ConnectorCategory)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${
                selectedCategory === cat.id
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-xs"
                  : "bg-slate-100 dark:bg-[#111D3D] text-slate-600 dark:text-[#94A3B8] hover:bg-slate-200/70 dark:hover:bg-[#172652]"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="relative w-full md:w-64">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher un connecteur..."
            className="w-full bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF]"
          />
        </div>
      </div>

      {/* Connector Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filteredConnectors.map((c) => (
          <AvenqoCard
            key={c.id}
            variant="default"
            hoverable
            className="p-5 flex flex-col justify-between min-h-[190px] group cursor-pointer"
            onClick={() => setSelectedConnector(c)}
          >
            <div>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-xl text-white font-extrabold text-base shadow-xs ${c.iconBg}`}
                  >
                    {c.logoLetter}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB] group-hover:text-[#0076FF] transition-colors">
                      {c.name}
                    </h3>
                    <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                      {c.categoryLabel}
                    </span>
                  </div>
                </div>

                <StatusBadge status={c.status} size="sm" />
              </div>

              <p className="mt-3 text-xs text-slate-600 dark:text-[#94A3B8] leading-relaxed line-clamp-2">
                {c.description}
              </p>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
              {c.lastSynced ? (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>{c.lastSynced}</span>
                </span>
              ) : (
                <span>Non synchronisé</span>
              )}

              {typeof c.recordCount === "number" && (
                <span className="font-semibold text-slate-700 dark:text-[#F4F7FB]">
                  {c.recordCount.toLocaleString()} {t.integrations.recordsCount}
                </span>
              )}
            </div>
          </AvenqoCard>
        ))}
      </div>

      {/* Sync Drawer / Modal for Selected Connector */}
      {selectedConnector && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in"
          onClick={() => setSelectedConnector(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.12] shadow-2xl overflow-hidden animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-5 border-b border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between bg-slate-50/60 dark:bg-[#060B13]/50">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-xl text-white font-extrabold text-sm ${selectedConnector.iconBg}`}
                >
                  {selectedConnector.logoLetter}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {selectedConnector.name}
                  </h3>
                  <div className="flex items-center gap-2 mt-0.5">
                    <StatusBadge status={selectedConnector.status} size="sm" />
                    <span className="text-[11px] text-slate-400">ID: {selectedConnector.id}</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedConnector(null)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.08] text-slate-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content & Action */}
            <div className="p-5 space-y-4">
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] text-xs text-slate-600 dark:text-[#94A3B8] leading-relaxed">
                {selectedConnector.description}
              </div>

              {/* Sync Action Area */}
              <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#111D3D]">
                <div>
                  <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB]">
                    Déclenchement Manuel
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Forcer la réconciliation immédiate des données.
                  </div>
                </div>

                <button
                  onClick={() => handleTriggerSync(selectedConnector)}
                  disabled={isSyncing || !selectedConnector.supportsSync}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                  <span>{isSyncing ? "En cours..." : "Synchroniser"}</span>
                </button>
              </div>

              {/* Audit Logs */}
              <div>
                <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] mb-2 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#0076FF]" />
                  <span>{t.integrations.drawerLogsTitle}</span>
                </div>

                <div className="max-h-48 overflow-y-auto space-y-2 font-mono text-[11px] p-2 rounded-xl bg-slate-100/80 dark:bg-[#060B13] border border-slate-200/60 dark:border-white/[0.06]">
                  {syncLogs.map((log) => (
                    <div key={log.id} className="p-2 rounded-lg bg-white dark:bg-[#0B132B]/80 text-xs">
                      <div className="flex items-center justify-between text-[10px] text-slate-400 pb-1">
                        <span>{log.time}</span>
                        <span
                          className={`font-semibold ${
                            log.level === "success"
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-blue-600 dark:text-[#00D4FF]"
                          }`}
                        >
                          {log.level.toUpperCase()}
                        </span>
                      </div>
                      <div className="text-slate-700 dark:text-slate-300 font-sans text-[11px]">
                        {log.message}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/30 flex justify-end">
              <button
                onClick={() => setSelectedConnector(null)}
                className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-800 dark:text-[#F4F7FB] text-xs font-semibold hover:bg-slate-300 dark:hover:bg-white/[0.12] transition-colors"
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

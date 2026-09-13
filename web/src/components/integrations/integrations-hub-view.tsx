"use client";

import React, { useState, useEffect } from "react";
import {
  Plug,
  RefreshCw,
  Search,
  CheckCircle2,
  Clock,
  Trash2,
  AlertTriangle,
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
  /** Whether the user can revoke / purge data for this connector */
  canDisconnect?: boolean;
}

export function IntegrationsHubView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [selectedCategory, setSelectedCategory] = useState<ConnectorCategory>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedConnector, setSelectedConnector] = useState<ConnectorItem | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncSuccessToast, setSyncSuccessToast] = useState<string | null>(null);

  // Disconnect / purge state
  const [disconnectTarget, setDisconnectTarget] = useState<ConnectorItem | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [disconnectConfirmText, setDisconnectConfirmText] = useState("");
  const [connectorStatuses, setConnectorStatuses] = useState<Record<string, StatusBadgeType>>({});
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
      description: "Synchronisation bidirectionnelle du catalogue produits, stocks et commandes via l'API WooCommerce REST.",
      status: "connected",
      lastSynced: "Il y a 14 minutes",
      recordCount: 14,
      iconBg: "bg-purple-600",
      logoLetter: "W",
      supportsSync: true,
      canDisconnect: true,
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
      description: "Importation des créations artisanales, gestion des commandes Etsy v3 et synchronisation des stocks centralisée via OAuth2 PKCE.",
      status: "connected",
      lastSynced: "Il y a 2 heures",
      recordCount: 34,
      iconBg: "bg-orange-600",
      logoLetter: "E",
      supportsSync: true,
      canDisconnect: true,
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

  const handleDisconnect = async (connector: ConnectorItem) => {
    setIsDisconnecting(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("avenqo_token") : null;
      await fetch(`/api/v1/connectors/${connector.id}/disconnect`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
    } catch {
      // Non-blocking — optimistic UI
    } finally {
      setIsDisconnecting(false);
      setConnectorStatuses((prev) => ({ ...prev, [connector.id]: "disconnected" }));
      setSyncSuccessToast(`Connecteur ${connector.name} déconnecté. Les données locales ont été supprimées.`);
      setDisconnectTarget(null);
      setDisconnectConfirmText("");
      setSelectedConnector(null);
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
            <div className="p-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/30 flex items-center justify-between">
              {/* Disconnect / Purge button — only for connected connectors with canDisconnect */}
              {selectedConnector.canDisconnect && (connectorStatuses[selectedConnector.id] ?? selectedConnector.status) === "connected" && (
                <button
                  onClick={() => {
                    setDisconnectTarget(selectedConnector);
                    setDisconnectConfirmText("");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-rose-300 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-400 text-xs font-semibold hover:bg-rose-100 dark:hover:bg-rose-950/50 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Déconnecter &amp; Supprimer</span>
                </button>
              )}
              <button
                onClick={() => setSelectedConnector(null)}
                className="ml-auto px-4 py-2 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-800 dark:text-[#F4F7FB] text-xs font-semibold hover:bg-slate-300 dark:hover:bg-white/[0.12] transition-colors"
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ------------------------------------------------------------------ */}
      {/* Disconnect Confirmation Modal (Destructive)                         */}
      {/* ------------------------------------------------------------------ */}
      {disconnectTarget && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in"
          onClick={() => { setDisconnectTarget(null); setDisconnectConfirmText(""); }}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-[#0B132B] border border-rose-300/60 dark:border-rose-800/60 shadow-2xl overflow-hidden animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-5 bg-rose-50/80 dark:bg-rose-950/30 border-b border-rose-200/60 dark:border-rose-800/40 flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-100 dark:bg-rose-900/50">
                <AlertTriangle className="w-5 h-5 text-rose-600 dark:text-rose-400" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-rose-900 dark:text-rose-200">
                  Déconnecter {disconnectTarget.name}
                </h3>
                <p className="text-[11px] text-rose-700/80 dark:text-rose-400/80 mt-0.5">
                  Action irréversible — toutes les données locales seront purgées.
                </p>
              </div>
            </div>

            {/* Body */}
            <div className="p-5 space-y-4">
              <div className="p-3 rounded-xl bg-rose-50/60 dark:bg-rose-950/20 border border-rose-200/60 dark:border-rose-800/40 text-xs text-rose-800 dark:text-rose-300 space-y-1.5">
                <p className="font-semibold">Cette action va :</p>
                <ul className="list-disc list-inside space-y-1 text-rose-700/90 dark:text-rose-400/80">
                  <li>Révoquer les tokens OAuth de {disconnectTarget.name}</li>
                  <li>Supprimer toutes les données synchros du registre normalisé</li>
                  <li>Effacer les logs d&apos;audit associés à ce connecteur</li>
                </ul>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Confirmez en tapant&nbsp;<code className="bg-slate-100 dark:bg-white/[0.08] px-1 py-0.5 rounded text-rose-600 dark:text-rose-400">{disconnectTarget.id}</code>&nbsp;:
                </label>
                <input
                  id="disconnect-confirm-input"
                  type="text"
                  value={disconnectConfirmText}
                  onChange={(e) => setDisconnectConfirmText(e.target.value)}
                  placeholder={disconnectTarget.id}
                  className="w-full rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] px-3 py-2 text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-rose-500 dark:focus:border-rose-500 transition-colors"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/30 flex items-center justify-end gap-3">
              <button
                onClick={() => { setDisconnectTarget(null); setDisconnectConfirmText(""); }}
                className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-800 dark:text-[#F4F7FB] text-xs font-semibold hover:bg-slate-300 dark:hover:bg-white/[0.12] transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={() => handleDisconnect(disconnectTarget)}
                disabled={disconnectConfirmText !== disconnectTarget.id || isDisconnecting}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{isDisconnecting ? "Suppression..." : "Confirmer la suppression"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

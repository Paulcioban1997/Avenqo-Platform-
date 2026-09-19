"use client";

import React, { useState, useEffect, useCallback } from "react";
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
  Power,
  Sliders,
  Check,
  ExternalLink,
  Key,
  Globe,
  Store,
  ArrowRight,
  ShieldCheck,
  HelpCircle,
  Link2,
} from "lucide-react";
import { AvenqoCard, StatusBadge, StatusBadgeType } from "@/components/ui/avenqo-card";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

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
  canDisconnect?: boolean;
  storeUrl?: string;
  connectionId?: string;
}

interface RawConnection {
  id: string;
  provider: string;
  external_account_id: string;
  display_name?: string;
  status: string;
  records_processed: number;
  records_created?: number;
  records_updated?: number;
  records_failed?: number;
  last_successful_sync?: string;
  selected_entities?: string[];
  is_enabled?: boolean;
}

interface SyncLogItem {
  id: string;
  time: string;
  message: string;
  level: "info" | "success" | "warning" | "error";
}

export function IntegrationsHubView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [selectedCategory, setSelectedCategory] = useState<ConnectorCategory>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedConnector, setSelectedConnector] = useState<ConnectorItem | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncSuccessToast, setSyncSuccessToast] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Live connections from backend
  const [rawConnections, setRawConnections] = useState<RawConnection[]>([]);
  const [isLoadingConnections, setIsLoadingConnections] = useState(true);

  // Modal manual configuration inputs
  const [isSubmittingManual, setIsSubmittingManual] = useState(false);
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [wooStoreUrl, setWooStoreUrl] = useState("");
  const [wooConsumerKey, setWooConsumerKey] = useState("");
  const [wooConsumerSecret, setWooConsumerSecret] = useState("");
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken] = useState("");

  // Disconnect / purge state
  const [disconnectTarget, setDisconnectTarget] = useState<ConnectorItem | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [disconnectConfirmText, setDisconnectConfirmText] = useState("");

  // Toggles and entities per connector
  const [connectorActiveState, setConnectorActiveState] = useState<Record<string, boolean>>({});
  const [connectorEntitiesState, setConnectorEntitiesState] = useState<Record<string, string[]>>({});
  const [syncLogs, setSyncLogs] = useState<SyncLogItem[]>([]);

  // Fetch real connections from API
  const loadConnections = useCallback(async () => {
    setIsLoadingConnections(true);
    try {
      const headers = getAuthHeaders();
      const [connRes, historyRes] = await Promise.all([
        fetch("/api/v1/connectors/connections", { headers }).catch(() => null),
        fetch("/api/v1/connectors/sync/history?limit=10", { headers }).catch(() => null),
      ]);

      if (connRes && connRes.ok) {
        const data = await connRes.json();
        if (Array.isArray(data)) {
          setRawConnections(data);

          // Populate active states & entities
          const activeMap: Record<string, boolean> = {};
          const entitiesMap: Record<string, string[]> = {};
          data.forEach((c: RawConnection) => {
            activeMap[c.provider.toLowerCase()] = c.is_enabled ?? true;
            entitiesMap[c.provider.toLowerCase()] = c.selected_entities || [
              "orders",
              "products",
              "customers",
              "inventory",
              "refunds",
            ];
          });
          setConnectorActiveState((prev) => ({ ...prev, ...activeMap }));
          setConnectorEntitiesState((prev) => ({ ...prev, ...entitiesMap }));
        }
      }

      if (historyRes && historyRes.ok) {
        const historyData = await historyRes.json();
        if (Array.isArray(historyData) && historyData.length > 0) {
          const formatted: SyncLogItem[] = historyData.map((h: any) => ({
            id: h.id || `hist-${Math.random()}`,
            time: h.timestamp
              ? new Date(h.timestamp).toLocaleString(locale === "en" ? "en-US" : "fr-CA", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                  day: "numeric",
                  month: "short",
                })
              : "Récemment",
            message:
              h.message ||
              `Réconciliation ${h.provider} : ${h.records_synced || 0} enregistrements.`,
            level:
              h.status === "ERROR" || h.status === "FAILED"
                ? "error"
                : h.status === "READY" || h.status === "CONNECTED"
                ? "success"
                : "info",
          }));
          setSyncLogs(formatted);
        }
      }
    } catch {
      // Local fallback
    } finally {
      setIsLoadingConnections(false);
    }
  }, [locale]);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  // Handle opening modal for a connector
  const handleOpenConnector = (c: ConnectorItem) => {
    setSelectedConnector(c);
    setFormError(null);

    // If connected, show overview first; if not connected, show config form directly
    if (c.status === "connected") {
      setShowConfigForm(false);
      setWooStoreUrl(c.storeUrl || "");
    } else {
      setShowConfigForm(true);
      setWooStoreUrl("");
      setWooConsumerKey("");
      setWooConsumerSecret("");
      setShopifyDomain("");
      setShopifyToken("");
    }
  };

  const handleToggleConnectorActive = async (connectorId: string) => {
    const currentState = connectorActiveState[connectorId] ?? true;
    const nextState = !currentState;
    setConnectorActiveState((prev) => ({ ...prev, [connectorId]: nextState }));
    setSyncSuccessToast(
      `Connecteur ${selectedConnector?.name} : ${nextState ? "Activé" : "Désactivé (synchronisation suspendue)"}.`
    );

    const activeConn = rawConnections.find((c) => c.provider.toLowerCase() === connectorId);
    if (activeConn) {
      try {
        await fetch(`/api/v1/connectors/connections/${activeConn.id}/settings`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ is_enabled: nextState }),
        });
      } catch {
        // Fallback
      }
    }
  };

  const handleToggleEntity = async (connectorId: string, entityKey: string) => {
    const current = connectorEntitiesState[connectorId] || [
      "orders",
      "products",
      "customers",
      "inventory",
      "refunds",
    ];
    const next = current.includes(entityKey)
      ? current.filter((e) => e !== entityKey)
      : [...current, entityKey];
    setConnectorEntitiesState((prev) => ({ ...prev, [connectorId]: next }));
    setSyncSuccessToast(`Flux de données sélectionné mis à jour pour ${selectedConnector?.name}.`);

    const activeConn = rawConnections.find((c) => c.provider.toLowerCase() === connectorId);
    if (activeConn) {
      try {
        await fetch(`/api/v1/connectors/connections/${activeConn.id}/settings`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({ selected_entities: next }),
        });
      } catch {
        // Fallback
      }
    }
  };

  // Connect WooCommerce Store
  const handleConnectWooCommerce = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmittingManual(true);

    try {
      if (!wooStoreUrl.trim()) {
        throw new Error("Veuillez saisir l'URL de votre boutique WooCommerce.");
      }
      if (!wooConsumerKey.trim()) {
        throw new Error("Veuillez saisir la Consumer Key (commençant par ck_).");
      }
      if (!wooConsumerSecret.trim()) {
        throw new Error("Veuillez saisir la Consumer Secret (commençant par cs_).");
      }

      let formattedUrl = wooStoreUrl.trim();
      if (!formattedUrl.startsWith("http://") && !formattedUrl.startsWith("https://")) {
        formattedUrl = `https://${formattedUrl}`;
      }

      const res = await fetch("/api/v1/connectors/woocommerce/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          store_url: formattedUrl,
          consumer_key: wooConsumerKey.trim(),
          consumer_secret: wooConsumerSecret.trim(),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(
          errData?.detail ||
            "Échec de connexion à la boutique. Vérifiez l'adresse et vos clés d'accès."
        );
      }

      setSyncSuccessToast(
        `Boutique WooCommerce (${formattedUrl}) connectée avec succès ! Importation en cours...`
      );
      setShowConfigForm(false);
      await loadConnections();

      const newLog: SyncLogItem = {
        id: `log-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        message: `Boutique WooCommerce connectée : ${formattedUrl}. Synchronisation initiale lancée.`,
        level: "success",
      };
      setSyncLogs((prev) => [newLog, ...prev]);
    } catch (err: any) {
      setFormError(err.message || "Erreur lors de la connexion.");
    } finally {
      setIsSubmittingManual(false);
    }
  };

  // Connect Shopify Store
  const handleConnectShopify = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmittingManual(true);

    try {
      if (!shopifyDomain.trim()) {
        throw new Error("Veuillez saisir le domaine Shopify (ex: ma-boutique.myshopify.com).");
      }
      if (!shopifyToken.trim()) {
        throw new Error("Veuillez saisir le jeton d'accès Admin API (Admin Access Token).");
      }

      let cleanDomain = shopifyDomain.trim().toLowerCase();
      cleanDomain = cleanDomain.replace(/^https?:\/\//, "").replace(/\/$/, "");

      const res = await fetch("/api/v1/connectors/shopify/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          shop_domain: cleanDomain,
          access_token: shopifyToken.trim(),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(
          errData?.detail || "Échec de connexion à la boutique Shopify."
        );
      }

      setSyncSuccessToast(
        `Boutique Shopify (${cleanDomain}) connectée avec succès ! Importation en cours...`
      );
      setShowConfigForm(false);
      await loadConnections();

      const newLog: SyncLogItem = {
        id: `log-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        message: `Boutique Shopify connectée : ${cleanDomain}. Synchronisation initiale lancée.`,
        level: "success",
      };
      setSyncLogs((prev) => [newLog, ...prev]);
    } catch (err: any) {
      setFormError(err.message || "Erreur lors de la connexion.");
    } finally {
      setIsSubmittingManual(false);
    }
  };

  // Manual Synchronize Action
  const handleTriggerSync = async (connector: ConnectorItem) => {
    setIsSyncing(true);
    setFormError(null);

    const newLog: SyncLogItem = {
      id: `log-${Date.now()}`,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      message: `Synchronisation et réconciliation immédiate pour ${connector.name}...`,
      level: "info",
    };
    setSyncLogs((prev) => [newLog, ...prev]);

    try {
      const activeConn = rawConnections.find((c) => c.provider.toLowerCase() === connector.id);
      const url = activeConn
        ? `/api/v1/connectors/connections/${activeConn.id}/sync`
        : `/api/v1/connectors/sync`;

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          connector_id: activeConn ? activeConn.id : connector.id,
          provider: connector.id,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(
          errData?.detail ||
            `Impossible de déclencher la synchronisation pour ${connector.name}. Veuillez d'abord connecter votre boutique.`
        );
      }

      setSyncSuccessToast(
        `Synchronisation lancée avec succès pour ${connector.name}. Les données sont réconciliées en arrière-plan.`
      );
      await loadConnections();

      const successLog: SyncLogItem = {
        id: `log-s-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        message: `Synchronisation acceptée pour ${connector.name}. Registre normalisé en cours de mise à jour.`,
        level: "success",
      };
      setSyncLogs((prev) => [successLog, ...prev]);
    } catch (err: any) {
      setFormError(err.message);
      const errLog: SyncLogItem = {
        id: `log-e-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        message: `Erreur : ${err.message}`,
        level: "error",
      };
      setSyncLogs((prev) => [errLog, ...prev]);
    } finally {
      setIsSyncing(false);
    }
  };

  // Disconnect connector
  const handleDisconnect = async (connector: ConnectorItem) => {
    setIsDisconnecting(true);
    try {
      const activeConn = rawConnections.find((c) => c.provider.toLowerCase() === connector.id);
      if (activeConn) {
        await fetch(`/api/v1/connectors/connections/${activeConn.id}`, {
          method: "DELETE",
          headers: getAuthHeaders(),
        });
      }
      setSyncSuccessToast(`Connecteur ${connector.name} déconnecté et données supprimées.`);
      await loadConnections();
      setSelectedConnector(null);
      setDisconnectTarget(null);
      setDisconnectConfirmText("");
    } catch {
      // Optimistic
    } finally {
      setIsDisconnecting(false);
    }
  };

  // Dynamic Catalog of Connectors merging live state from backend
  const baseCatalog: Array<{
    id: string;
    name: string;
    category: ConnectorCategory;
    categoryLabel: string;
    description: string;
    iconBg: string;
    logoLetter: string;
    supportsSync: boolean;
    canDisconnect: boolean;
  }> = [
    {
      id: "woocommerce",
      name: "WooCommerce",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description:
        "Synchronisation bidirectionnelle du catalogue produits, stocks et commandes via l'API WooCommerce REST.",
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
      description:
        "Connecteur officiel Shopify Storefront & Admin API avec gestion des webhooks et des stocks.",
      iconBg: "bg-emerald-600",
      logoLetter: "S",
      supportsSync: true,
      canDisconnect: true,
    },
    {
      id: "stripe",
      name: "Stripe",
      category: "accounting",
      categoryLabel: t.integrations.categoryAccounting,
      description:
        "Abonnements SaaS, paiements multidevises, facturation automatique et conformité fiscale.",
      iconBg: "bg-blue-600",
      logoLetter: "S",
      supportsSync: true,
      canDisconnect: false,
    },
    {
      id: "amazon",
      name: "Amazon Seller Central",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Intégration Amazon SP-API pour la gestion des inventaires FBA et commandes.",
      iconBg: "bg-amber-600",
      logoLetter: "A",
      supportsSync: false,
      canDisconnect: false,
    },
    {
      id: "etsy",
      name: "Etsy",
      category: "ecommerce",
      categoryLabel: t.integrations.categoryEcommerce,
      description: "Synchronisation des fiches produits, variations d'articles et commandes de créateurs.",
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
      description: "Remontée des conversions hors-ligne, ROAS prédictif et audiences similaires Avenqo AI.",
      iconBg: "bg-blue-500",
      logoLetter: "G",
      supportsSync: true,
      canDisconnect: false,
    },
    {
      id: "meta_ads",
      name: "Meta Ads (Facebook / IG)",
      category: "marketing",
      categoryLabel: t.integrations.categoryMarketing,
      description: "API Conversions (CAPI) temps réel, catalogues dynamiques et optimisation des CPA.",
      iconBg: "bg-indigo-600",
      logoLetter: "M",
      supportsSync: true,
      canDisconnect: false,
    },
    {
      id: "klaviyo",
      name: "Klaviyo",
      category: "crm",
      categoryLabel: t.integrations.categoryCrm,
      description: "Automatisation des campagnes e-mail & SMS et segmentation RFM prédictive par IA.",
      iconBg: "bg-neutral-800",
      logoLetter: "K",
      supportsSync: true,
      canDisconnect: false,
    },
    {
      id: "hubspot",
      name: "HubSpot CRM",
      category: "crm",
      categoryLabel: t.integrations.categoryCrm,
      description: "Synchronisation des leads B2B, cycles de vente et pipelines d'opportunités.",
      iconBg: "bg-orange-500",
      logoLetter: "H",
      supportsSync: false,
      canDisconnect: false,
    },
    {
      id: "quickbooks",
      name: "QuickBooks Online",
      category: "accounting",
      categoryLabel: t.integrations.categoryAccounting,
      description: "Comptabilité automatisée, grand livre général et réconciliation des encaissements.",
      iconBg: "bg-green-600",
      logoLetter: "Q",
      supportsSync: true,
      canDisconnect: false,
    },
    {
      id: "zapier",
      name: "Zapier",
      category: "automation",
      categoryLabel: t.integrations.categoryAutomation,
      description: "Déclencheurs d'actions personnalisés et webhooks entrants/sortants vers 5000+ apps.",
      iconBg: "bg-amber-500",
      logoLetter: "Z",
      supportsSync: true,
      canDisconnect: false,
    },
  ];

  const connectors: ConnectorItem[] = baseCatalog.map((item) => {
    const activeConn = rawConnections.find(
      (c) =>
        c.provider.toLowerCase() === item.id.toLowerCase() &&
        c.status !== "DISCONNECTED"
    );

    if (activeConn) {
      const isOk =
        activeConn.status === "READY" ||
        activeConn.status === "CONNECTED" ||
        activeConn.status === "SYNCING";

      const lastDate = activeConn.last_successful_sync
        ? new Date(activeConn.last_successful_sync).toLocaleDateString(
            locale === "en" ? "en-US" : "fr-CA",
            { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
          )
        : "Synchronisé";

      return {
        ...item,
        status: isOk ? ("connected" as StatusBadgeType) : ("needs_attention" as StatusBadgeType),
        lastSynced: lastDate,
        recordCount: activeConn.records_processed,
        storeUrl: activeConn.external_account_id,
        connectionId: activeConn.id,
      };
    }

    // Default: disconnected
    return {
      ...item,
      status: "disconnected" as StatusBadgeType,
      lastSynced: undefined,
      recordCount: undefined,
      storeUrl: undefined,
      connectionId: undefined,
    };
  });

  const filteredConnectors = connectors.filter((c) => {
    const matchesCat = selectedCategory === "all" || c.category === selectedCategory;
    const matchesQuery =
      !searchQuery.trim() ||
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.storeUrl && c.storeUrl.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesCat && matchesQuery;
  });

  // Current active connection for the selected connector
  const currentActiveConn = selectedConnector
    ? rawConnections.find(
        (c) =>
          c.provider.toLowerCase() === selectedConnector.id.toLowerCase() &&
          c.status !== "DISCONNECTED"
      )
    : null;

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
              {connectors.length} Connecteurs
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            Configurez vos boutiques en ligne, collez vos clés d'API et synchronisez vos données réelles.
          </p>
        </div>

        {/* Global sync button */}
        <div className="flex items-center gap-2">
          <button
            onClick={loadConnections}
            disabled={isLoadingConnections}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingConnections ? "animate-spin text-[#0076FF]" : ""}`} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      {/* Success Notification Banner */}
      {syncSuccessToast && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300 animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span className="font-medium">{syncSuccessToast}</span>
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
            placeholder="Rechercher une boutique..."
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
            className="p-5 flex flex-col justify-between min-h-[190px] group cursor-pointer border-slate-200/80 dark:border-white/[0.08]"
            onClick={() => handleOpenConnector(c)}
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

              {/* Show connected store URL if configured */}
              {c.storeUrl && (
                <div className="mt-2.5 flex items-center gap-1 text-[11px] text-[#0076FF] dark:text-[#00D4FF] font-medium truncate">
                  <Store size={12} className="shrink-0" />
                  <span className="truncate">{c.storeUrl}</span>
                </div>
              )}

              <p className="mt-2 text-xs text-slate-600 dark:text-[#94A3B8] leading-relaxed line-clamp-2">
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
                <span className="italic">Non connecté</span>
              )}

              {typeof c.recordCount === "number" && c.recordCount > 0 ? (
                <span className="font-semibold text-slate-700 dark:text-[#F4F7FB]">
                  {c.recordCount.toLocaleString()} enregistrements
                </span>
              ) : (
                <span className="text-[#0076FF] font-semibold group-hover:underline flex items-center gap-1">
                  <span>Configurer</span>
                  <ArrowRight size={11} />
                </span>
              )}
            </div>
          </AvenqoCard>
        ))}
      </div>

      {/* ================================================================== */}
      {/* Modal: Connector Configuration / Store Import / Sync Management     */}
      {/* ================================================================== */}
      {selectedConnector && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in"
          onClick={() => setSelectedConnector(null)}
        >
          <div
            className="w-full max-w-xl max-h-[90vh] flex flex-col rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.12] shadow-2xl overflow-hidden animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between bg-slate-50/60 dark:bg-[#060B13]/50 shrink-0">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-xl text-white font-extrabold text-base ${selectedConnector.iconBg}`}
                >
                  {selectedConnector.logoLetter}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {selectedConnector.name}
                  </h3>
                  <div className="flex items-center gap-2 mt-0.5">
                    <StatusBadge
                      status={currentActiveConn ? "connected" : "disconnected"}
                      size="sm"
                    />
                    <span className="text-[11px] text-slate-400">
                      ID: {selectedConnector.id}
                    </span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedConnector(null)}
                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.08] text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="p-5 space-y-4 overflow-y-auto flex-1">
              {/* Error Banner */}
              {formError && (
                <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 flex items-start gap-2.5 text-xs text-rose-800 dark:text-rose-300 animate-in fade-in">
                  <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div className="flex-1 leading-relaxed">{formError}</div>
                  <button onClick={() => setFormError(null)} className="text-rose-500 hover:text-rose-700">
                    <X size={14} />
                  </button>
                </div>
              )}

              {/* Mode A: Store is connected AND not in editing mode */}
              {currentActiveConn && !showConfigForm ? (
                <div className="space-y-4">
                  {/* Connected Store Card */}
                  <div className="p-4 rounded-xl border border-emerald-200 dark:border-emerald-800/60 bg-emerald-50/50 dark:bg-emerald-950/20 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                        <CheckCircle2 size={16} className="text-emerald-600" />
                        <span>Boutique Connectée et Opérationnelle</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowConfigForm(true)}
                        className="text-[11px] font-semibold text-[#0076FF] hover:underline cursor-pointer"
                      >
                        Modifier l'URL ou les clés
                      </button>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 text-xs text-slate-700 dark:text-slate-300">
                      <div className="flex items-center gap-1.5 font-mono text-[11px] bg-white dark:bg-[#0B132B] px-2.5 py-1 rounded-lg border border-slate-200 dark:border-white/[0.08] truncate max-w-sm">
                        <Globe size={13} className="text-slate-400 shrink-0" />
                        <span className="truncate">{currentActiveConn.external_account_id}</span>
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        <span className="font-bold text-slate-900 dark:text-white">
                          {currentActiveConn.records_processed.toLocaleString()}
                        </span>{" "}
                        enregistrements synchronisés
                      </div>
                    </div>
                  </div>

                  {/* Activation Switch */}
                  <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#111D3D]/60">
                    <div>
                      <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-1.5">
                        <Power
                          size={14}
                          className={
                            connectorActiveState[selectedConnector.id] ?? true
                              ? "text-emerald-500"
                              : "text-slate-400"
                          }
                        />
                        <span>Statut du Connecteur</span>
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-[#94A3B8] mt-0.5">
                        {connectorActiveState[selectedConnector.id] ?? true
                          ? "Connecteur actif — La synchronisation automatique en arrière-plan est autorisée."
                          : "Connecteur inactif — La synchronisation est temporairement suspendue."}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleToggleConnectorActive(selectedConnector.id)}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        connectorActiveState[selectedConnector.id] ?? true
                          ? "bg-[#0076FF]"
                          : "bg-slate-300 dark:bg-slate-700"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          connectorActiveState[selectedConnector.id] ?? true
                            ? "translate-x-5"
                            : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  {/* Entity Selectors */}
                  <div className="p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#111D3D] space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-1.5">
                          <Sliders size={14} className="text-[#0076FF]" />
                          <span>Sélection des Données à Synchroniser</span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Choisissez vous-même les flux de données à importer dans Avenqo.
                        </div>
                      </div>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-[#00D4FF]">
                        {(connectorEntitiesState[selectedConnector.id] || []).length} sélectionnés
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      {[
                        { id: "orders", label: "Commandes & Ventes", desc: "Transactions et factures" },
                        { id: "products", label: "Produits & Catalogue", desc: "SKUs, prix, variantes" },
                        { id: "customers", label: "Clients & Profils", desc: "Coordonnées et profils" },
                        { id: "inventory", label: "Niveaux de Stocks", desc: "Quantités et ruptures" },
                        { id: "refunds", label: "Remboursements", desc: "Avoirs et retours" },
                      ].map((entity) => {
                        const isChecked = (
                          connectorEntitiesState[selectedConnector.id] || [
                            "orders",
                            "products",
                            "customers",
                            "inventory",
                            "refunds",
                          ]
                        ).includes(entity.id);

                        return (
                          <button
                            key={entity.id}
                            type="button"
                            onClick={() => handleToggleEntity(selectedConnector.id, entity.id)}
                            className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-left transition-all ${
                              isChecked
                                ? "bg-blue-50/70 border-blue-200 dark:bg-[#172652]/60 dark:border-[#0076FF]/40 text-slate-900 dark:text-[#F4F7FB]"
                                : "bg-slate-50/50 border-slate-200/60 dark:bg-[#0B132B]/60 dark:border-white/[0.04] text-slate-500 dark:text-slate-400 hover:border-slate-300"
                            }`}
                          >
                            <div
                              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-md border mt-0.5 ${
                                isChecked
                                  ? "bg-[#0076FF] border-[#0076FF] text-white"
                                  : "border-slate-300 dark:border-slate-600 bg-white dark:bg-[#0B132B]"
                              }`}
                            >
                              {isChecked && <Check size={11} strokeWidth={3} />}
                            </div>
                            <div>
                              <div className="text-xs font-semibold leading-tight">{entity.label}</div>
                              <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                                {entity.desc}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Manual Sync Trigger */}
                  <div className="flex items-center justify-between p-3.5 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-white dark:bg-[#111D3D]">
                    <div>
                      <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB]">
                        Synchronisation Manuelle
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Forcer la réconciliation et l'import immédiat des données.
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleTriggerSync(selectedConnector)}
                      disabled={isSyncing}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-colors cursor-pointer"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                      <span>{isSyncing ? "Importation..." : "Synchroniser maintenant"}</span>
                    </button>
                  </div>
                </div>
              ) : (
                /* Mode B: Configuration & Import Form (WooCommerce, Shopify or other) */
                <div className="space-y-4">
                  <div className="p-3.5 rounded-xl bg-blue-50/60 dark:bg-[#172652]/40 border border-blue-200 dark:border-[#0076FF]/30 text-xs text-slate-700 dark:text-[#94A3B8] leading-relaxed flex items-start gap-2.5">
                    <Store className="w-4 h-4 text-[#0076FF] shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-slate-900 dark:text-white">
                        Connectez la boutique avec laquelle vous travaillez.
                      </span>{" "}
                      Collez l'adresse web de votre boutique et vos clés d'API. Avenqo importera et
                      réconciliera automatiquement votre catalogue et vos commandes.
                    </div>
                  </div>

                  {/* Form for WooCommerce */}
                  {selectedConnector.id === "woocommerce" && (
                    <form onSubmit={handleConnectWooCommerce} className="space-y-3.5">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                          URL de votre boutique WooCommerce *
                        </label>
                        <div className="relative">
                          <Globe className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="text"
                            required
                            value={wooStoreUrl}
                            onChange={(e) => setWooStoreUrl(e.target.value)}
                            placeholder="https://votre-boutique-woocommerce.ca"
                            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF] transition-colors"
                          />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1">
                          Exemple : https://mon-magasin.com ou https://boutique.example.ca
                        </p>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                          Clé Client (Consumer Key) *
                        </label>
                        <div className="relative">
                          <Key className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="text"
                            required
                            value={wooConsumerKey}
                            onChange={(e) => setWooConsumerKey(e.target.value)}
                            placeholder="ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] text-xs font-mono text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF] transition-colors"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                          Clé Secrète (Consumer Secret) *
                        </label>
                        <div className="relative">
                          <Key className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="password"
                            required
                            value={wooConsumerSecret}
                            onChange={(e) => setWooConsumerSecret(e.target.value)}
                            placeholder="cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] text-xs font-mono text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF] transition-colors"
                          />
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200/60 dark:border-white/[0.06] text-[11px] text-slate-500 dark:text-slate-400 space-y-1">
                        <div className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                          <HelpCircle size={13} className="text-[#0076FF]" />
                          <span>Où trouver vos clés d'API WooCommerce ?</span>
                        </div>
                        <p className="leading-relaxed">
                          Dans l'administration WordPress de votre boutique : <strong>WooCommerce</strong> &gt; <strong>Réglages</strong> &gt; <strong>Avancé</strong> &gt; <strong>API REST</strong> &gt; Cliquez sur <strong>Ajouter une clé</strong> avec les permissions <strong>Lecture/Écriture</strong>.
                        </p>
                      </div>

                      <div className="flex items-center justify-end gap-2.5 pt-2">
                        {currentActiveConn && (
                          <button
                            type="button"
                            onClick={() => setShowConfigForm(false)}
                            className="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.04]"
                          >
                            Annuler
                          </button>
                        )}
                        <button
                          type="submit"
                          disabled={isSubmittingManual}
                          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold shadow-xs disabled:opacity-50 transition-colors cursor-pointer"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isSubmittingManual ? "animate-spin" : ""}`} />
                          <span>{isSubmittingManual ? "Connexion & Importation..." : "Importer & Connecter ma boutique"}</span>
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Form for Shopify */}
                  {selectedConnector.id === "shopify" && (
                    <form onSubmit={handleConnectShopify} className="space-y-3.5">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                          Nom de domaine Shopify *
                        </label>
                        <div className="relative">
                          <Globe className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="text"
                            required
                            value={shopifyDomain}
                            onChange={(e) => setShopifyDomain(e.target.value)}
                            placeholder="ma-boutique.myshopify.com"
                            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF] transition-colors"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                          Jeton d'accès Admin API (Admin Access Token) *
                        </label>
                        <div className="relative">
                          <Key className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                          <input
                            type="password"
                            required
                            value={shopifyToken}
                            onChange={(e) => setShopifyToken(e.target.value)}
                            placeholder="shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] text-xs font-mono text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF] transition-colors"
                          />
                        </div>
                      </div>

                      <div className="flex items-center justify-end gap-2.5 pt-2">
                        {currentActiveConn && (
                          <button
                            type="button"
                            onClick={() => setShowConfigForm(false)}
                            className="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.04]"
                          >
                            Annuler
                          </button>
                        )}
                        <button
                          type="submit"
                          disabled={isSubmittingManual}
                          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs disabled:opacity-50 transition-colors cursor-pointer"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${isSubmittingManual ? "animate-spin" : ""}`} />
                          <span>{isSubmittingManual ? "Importation..." : "Importer la boutique Shopify"}</span>
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Generic fallback form for other connectors */}
                  {selectedConnector.id !== "woocommerce" && selectedConnector.id !== "shopify" && (
                    <div className="p-4 rounded-xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50 dark:bg-white/[0.02] text-xs text-slate-600 dark:text-slate-400 space-y-3">
                      <p>
                        Pour activer le connecteur <strong>{selectedConnector.name}</strong>, vous
                        pouvez déclencher la liaison automatique ou synchroniser les données de
                        l'entreprise.
                      </p>
                      <button
                        type="button"
                        onClick={() => handleTriggerSync(selectedConnector)}
                        disabled={isSyncing}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-colors"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                        <span>Synchroniser {selectedConnector.name}</span>
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Real Audit Logs */}
              <div>
                <div className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB] mb-2 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-[#0076FF]" />
                  <span>Journal de synchronisation en direct</span>
                </div>

                <div className="max-h-40 overflow-y-auto space-y-1.5 font-mono text-[11px] p-2.5 rounded-xl bg-slate-100/80 dark:bg-[#060B13] border border-slate-200/60 dark:border-white/[0.06]">
                  {syncLogs.length > 0 ? (
                    syncLogs.map((log) => (
                      <div
                        key={log.id}
                        className="p-2 rounded-lg bg-white dark:bg-[#0B132B]/80 text-xs border border-slate-200/40 dark:border-white/[0.04]"
                      >
                        <div className="flex items-center justify-between text-[10px] text-slate-400 pb-1">
                          <span>{log.time}</span>
                          <span
                            className={`font-semibold uppercase text-[9px] px-1.5 py-0.5 rounded ${
                              log.level === "success"
                                ? "text-emerald-700 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-400"
                                : log.level === "error"
                                ? "text-rose-700 bg-rose-50 dark:bg-rose-950/40 dark:text-rose-400"
                                : "text-blue-700 bg-blue-50 dark:bg-blue-950/40 dark:text-[#00D4FF]"
                            }`}
                          >
                            {log.level}
                          </span>
                        </div>
                        <div className="text-slate-700 dark:text-slate-300 font-sans text-[11px]">
                          {log.message}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-3 text-center text-slate-400 font-sans text-xs">
                      Aucun historique de synchronisation pour l'instant.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/30 flex items-center justify-between shrink-0">
              {currentActiveConn && selectedConnector.canDisconnect && (
                <button
                  type="button"
                  onClick={() => {
                    setDisconnectTarget(selectedConnector);
                    setDisconnectConfirmText("");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-rose-300 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-400 text-xs font-semibold hover:bg-rose-100 dark:hover:bg-rose-950/50 transition-colors cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Déconnecter &amp; Supprimer</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedConnector(null)}
                className="ml-auto px-4 py-2 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-800 dark:text-[#F4F7FB] text-xs font-semibold hover:bg-slate-300 dark:hover:bg-white/[0.12] transition-colors cursor-pointer"
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ================================================================== */}
      {/* Disconnect Confirmation Modal (Destructive)                         */}
      {/* ================================================================== */}
      {disconnectTarget && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in"
          onClick={() => {
            setDisconnectTarget(null);
            setDisconnectConfirmText("");
          }}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-[#0B132B] border border-rose-300/60 dark:border-rose-800/60 shadow-2xl overflow-hidden animate-in zoom-in-95"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 bg-rose-50/80 dark:bg-rose-950/30 border-b border-rose-200/60 dark:border-rose-800/40 flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-100 dark:bg-rose-900/50">
                <AlertTriangle className="w-5 h-5 text-rose-600 dark:text-rose-400" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-rose-900 dark:text-rose-200">
                  Déconnecter {disconnectTarget.name}
                </h3>
                <p className="text-[11px] text-rose-700/80 dark:text-rose-400/80 mt-0.5">
                  Action irréversible — les enregistrements normalisés seront supprimés.
                </p>
              </div>
            </div>

            <div className="p-5 space-y-4">
              <p className="text-xs text-slate-600 dark:text-slate-300">
                Êtes-vous certain de vouloir déconnecter la boutique et supprimer les données associées ?
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Tapez&nbsp;<code className="bg-slate-100 dark:bg-white/[0.08] px-1 py-0.5 rounded text-rose-600 dark:text-rose-400">{disconnectTarget.id}</code>&nbsp;pour confirmer :
                </label>
                <input
                  type="text"
                  value={disconnectConfirmText}
                  onChange={(e) => setDisconnectConfirmText(e.target.value)}
                  placeholder={disconnectTarget.id}
                  className="w-full rounded-xl border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#111D3D] px-3 py-2 text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-rose-500 transition-colors"
                />
              </div>
            </div>

            <div className="p-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/30 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setDisconnectTarget(null);
                  setDisconnectConfirmText("");
                }}
                className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-white/[0.08] text-slate-800 dark:text-[#F4F7FB] text-xs font-semibold hover:bg-slate-300 dark:hover:bg-white/[0.12] transition-colors"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={() => handleDisconnect(disconnectTarget)}
                disabled={disconnectConfirmText !== disconnectTarget.id || isDisconnecting}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{isDisconnecting ? "Suppression..." : "Confirmer la déconnexion"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

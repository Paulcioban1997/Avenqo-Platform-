"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Database,
  RefreshCw,
  Trash2,
  Download,
  Eye,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  Plus,
  ShoppingBag,
  Store,
  Layers,
  Sparkles,
  AlertTriangle,
  X,
  Lock,
  Search,
  Info,
  ArrowUpRight,
} from "lucide-react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { RequestFailure } from "@/components/ui/request-failure";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { useOptionalSession } from "@/lib/session-context";

interface CanonicalConnector {
  key: string;
  name: string;
  category: "commerce" | "marketplace" | "pos" | "crm" | "marketing" | "voice" | "billing" | "fulfillment";
  categoryLabel: string;
  availability: "available" | "configuration_required" | "partner_approval_pending" | "coming_soon";
  route?: string;
  capabilities: string[];
  description: string;
  authMethod: "oauth2" | "api_key" | "webhook" | "sip_webrtc" | "oauth2_pkce";
  envVars?: string[];
  docLink?: string;
  setupInstructions?: string[];
}

const CANONICAL_22_CONNECTORS: CanonicalConnector[] = [
  {
    key: "shopify",
    name: "Shopify",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "available",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Clients", "Inventaire", "Webhooks"],
    description: "Synchronisation bidirectionnelle native des commandes, stocks et clients via Shopify Admin REST & GraphQL API.",
    authMethod: "oauth2",
    docLink: "https://shopify.dev/docs/apps",
    setupInstructions: [
      "Créer une application dans l'espace Partenaire ou Paramètres > Applications personnalisées de Shopify",
      "Configurer les URLs de redirection vers {origin}/api/v1/connectors/shopify/callback",
      "Accorder les permissions read_products, read_orders, read_customers, write_inventory",
    ],
  },
  {
    key: "woocommerce",
    name: "WooCommerce",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "available",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Clients", "Inventaire"],
    description: "Connexion directe à votre boutique WordPress WooCommerce via l'API REST v3 avec chiffrement des clés d'accès.",
    authMethod: "api_key",
    docLink: "https://woocommerce.github.io/woocommerce-rest-api-docs/",
    setupInstructions: [
      "Dans WordPress, aller dans WooCommerce > Réglages > Avancé > API REST",
      "Cliquer sur 'Ajouter une clé', choisir le niveau Lecture/Écriture",
      "Copier la Consumer Key et Consumer Secret dans la fenêtre Avenqo",
    ],
  },
  {
    key: "bigcommerce",
    name: "BigCommerce",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Clients", "Inventaire"],
    description: "Intégration cloud pour boutiques BigCommerce d'entreprise avec gestion multi-devises et catalogues complexes.",
    authMethod: "oauth2",
    envVars: ["BIGCOMMERCE_CLIENT_ID", "BIGCOMMERCE_CLIENT_SECRET"],
    docLink: "https://developer.bigcommerce.com/",
    setupInstructions: [
      "Accéder au portail BigCommerce Developer Portal",
      "Créer une Single-Click App avec les scopes V2/V3 Orders & Products",
      "Configurer l'authentification OAuth 2.0 dans les variables d'environnement Avenqo",
    ],
  },
  {
    key: "adobe_commerce",
    name: "Adobe Commerce (Magento)",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Clients", "Inventaire", "GraphQL"],
    description: "Connecteur haute performance pour instances Magento 2 / Adobe Commerce on-premise et Adobe Commerce Cloud.",
    authMethod: "api_key",
    envVars: ["MAGENTO_BASE_URL", "MAGENTO_INTEGRATION_TOKEN"],
    docLink: "https://developer.adobe.com/commerce/",
    setupInstructions: [
      "Dans le panneau Admin Magento, aller dans Système > Intégrations > Ajouter une nouvelle intégration",
      "Accorder les accès API aux modules Ventes, Catalogue et Clients",
      "Activer l'intégration et renseigner le Access Token",
    ],
  },
  {
    key: "wix_ecommerce",
    name: "Wix eCommerce",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Inventaire"],
    description: "Synchronisation en temps réel des catalogues et commandes pour les boutiques Wix Stores.",
    authMethod: "oauth2",
    envVars: ["WIX_APP_ID", "WIX_APP_SECRET"],
    docLink: "https://dev.wix.com/",
    setupInstructions: [
      "Créer une application dans Wix Developers Center",
      "Configurer les permissions Wix Stores API (Read Orders, Read Products)",
      "Ajouter le webhook pour la notification d'achat immédiat",
    ],
  },
  {
    key: "squarespace_commerce",
    name: "Squarespace Commerce",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Inventaire"],
    description: "Extraction des commandes et inventaires depuis Squarespace Commerce v1 API avec clés sécurisées.",
    authMethod: "api_key",
    envVars: ["SQUARESPACE_API_KEY"],
    docLink: "https://developers.squarespace.com/commerce-apis",
    setupInstructions: [
      "Dans Squarespace, aller dans Paramètres > Avancé > Clés API pour développeur",
      "Générer une clé avec les permissions Commandes et Produits",
      "Saisir la clé dans les paramètres de connecteur sécurisés",
    ],
  },
  {
    key: "prestashop",
    name: "PrestaShop",
    category: "commerce",
    categoryLabel: "E-Commerce",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Produits", "Clients"],
    description: "Connexion Webservice XML/JSON pour PrestaShop 1.7 et 8.x avec token d'authentification dédié.",
    authMethod: "api_key",
    envVars: ["PRESTASHOP_WEBSERVICE_KEY", "PRESTASHOP_SHOP_URL"],
    docLink: "https://devdocs.prestashop-project.org/",
    setupInstructions: [
      "Activer le Webservice dans Paramètres avancés > Service Web de PrestaShop",
      "Créer une clé avec les droits GET sur orders, products, customers, stock_availables",
    ],
  },
  {
    key: "amazon_sp_api",
    name: "Amazon Seller Central (SP-API)",
    category: "marketplace",
    categoryLabel: "Place de marché",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Inventaire", "Prix", "Rapports FBA"],
    description: "Connexion officielle Selling Partner API (SP-API) d'Amazon avec authentification LWA et rôle IAM AWS STS.",
    authMethod: "oauth2",
    envVars: ["AMAZON_SP_API_CLIENT_ID", "AMAZON_SP_API_CLIENT_SECRET", "AMAZON_AWS_ROLE_ARN"],
    docLink: "https://developer-docs.amazon.com/sp-api",
    setupInstructions: [
      "Enregistrer un compte développeur Amazon SP-API dans Seller Central",
      "Créer une application LWA (Login with Amazon) et un rôle IAM AWS STS avec politique de moindre privilège",
      "Renseigner les clés LWA et l'ARN dans les variables Railway Sandbox/Production",
    ],
  },
  {
    key: "ebay",
    name: "eBay",
    category: "marketplace",
    categoryLabel: "Place de marché",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Annonces", "Inventaire", "Fulfillment"],
    description: "Intégration eBay REST Sell APIs avec flux OAuth 2.0 pour la gestion automatisée des ventes marketplace.",
    authMethod: "oauth2",
    envVars: ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"],
    docLink: "https://developer.ebay.com/develop/apis",
    setupInstructions: [
      "Créer un compte sur eBay Developers Program",
      "Générer une paire de clés d'application de production (App ID / Cert ID)",
      "Configurer l'URL de redirection OAuth RuName pour Avenqo",
    ],
  },
  {
    key: "etsy",
    name: "Etsy",
    category: "marketplace",
    categoryLabel: "Place de marché",
    availability: "partner_approval_pending",
    route: "/connections",
    capabilities: ["Commandes", "Fiches produits", "Reçus", "Boutique"],
    description: "Accès à l'API Etsy v3 via OAuth 2.0 PKCE pour créateurs et commerçants indépendants.",
    authMethod: "oauth2_pkce",
    envVars: ["ETSY_API_KEY", "ETSY_SHARED_SECRET"],
    docLink: "https://developers.etsy.com/documentation/",
    setupInstructions: [
      "Déposer une demande d'application sur le portail développeur Etsy Developers",
      "Attendre la validation du statut commercial Etsy par l'équipe partenaires",
      "Configurer la clé d'application et la redirection OAuth PKCE",
    ],
  },
  {
    key: "walmart_marketplace",
    name: "Walmart Marketplace",
    category: "marketplace",
    categoryLabel: "Place de marché",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Articles", "Inventaire", "Rapports"],
    description: "Synchronisation multi-canal avec Walmart US & Canada via l'API Marketplace Partner.",
    authMethod: "api_key",
    envVars: ["WALMART_CLIENT_ID", "WALMART_CLIENT_SECRET"],
    docLink: "https://developer.walmart.com/",
    setupInstructions: [
      "Obtenir les identifiants d'API dans Walmart Developer Portal",
      "Renseigner les clés Client ID et Client Secret de production",
    ],
  },
  {
    key: "tiktok_shop",
    name: "TikTok Shop",
    category: "marketplace",
    categoryLabel: "Place de marché",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Catalogue", "Fulfillment", "Social Commerce"],
    description: "Connecteur TikTok Shop Open API pour synchroniser les ventes de commerce social et créateurs.",
    authMethod: "oauth2",
    envVars: ["TIKTOK_SHOP_APP_KEY", "TIKTOK_SHOP_APP_SECRET"],
    docLink: "https://partner.tiktokshop.com/",
    setupInstructions: [
      "Enregistrer une application partenaire sur TikTok Shop Partner Center",
      "Sélectionner la région ciblée (Amérique du Nord / Europe) et demander les scopes Orders & Products",
    ],
  },
  {
    key: "square_pos",
    name: "Square POS",
    category: "pos",
    categoryLabel: "Point de vente",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Points de vente", "Commandes", "Paiements", "Catalogue articles"],
    description: "Intégration directe des caisses et terminaux Square pour unifier magasins physiques et boutique en ligne.",
    authMethod: "oauth2",
    envVars: ["SQUARE_APPLICATION_ID", "SQUARE_APPLICATION_SECRET"],
    docLink: "https://developer.squareup.com/",
    setupInstructions: [
      "Créer une application dans Square Developer Dashboard",
      "Activer les autorisations OAuth pour ORDERS_READ, ITEMS_READ, PAYMENTS_READ",
      "Ajouter le webhook de synchronisation des tickets de caisse en temps réel",
    ],
  },
  {
    key: "clover_pos",
    name: "Clover POS",
    category: "pos",
    categoryLabel: "Point de vente",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Inventaire", "Marchands", "Paiements"],
    description: "Connecteur Clover REST API pour synchronisation des terminaux de vente de commerce de détail.",
    authMethod: "oauth2",
    envVars: ["CLOVER_APP_ID", "CLOVER_APP_SECRET"],
    docLink: "https://docs.clover.com/",
    setupInstructions: [
      "Créer un compte sur Clover Developer Platform",
      "Créer une application marchande avec permissions d'accès aux ventes",
    ],
  },
  {
    key: "lightspeed_retail",
    name: "Lightspeed Retail",
    category: "pos",
    categoryLabel: "Point de vente",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Ventes", "Inventaire multi-boutiques", "Clients"],
    description: "Intégration omnicanale pour détaillants utilisant Lightspeed Retail (X-Series / R-Series).",
    authMethod: "oauth2",
    envVars: ["LIGHTSPEED_CLIENT_ID", "LIGHTSPEED_CLIENT_SECRET"],
    docLink: "https://developers.lightspeedhq.com/",
    setupInstructions: [
      "Générer une clé API ou application OAuth dans le portail Lightspeed Developers",
    ],
  },
  {
    key: "google_calendar",
    name: "Google Calendar",
    category: "crm",
    categoryLabel: "CRM & Calendrier",
    availability: "available",
    route: "/crm",
    capabilities: ["Événements", "Synchronisation bidirectionnelle", "Rappels", "Prise de RDV"],
    description: "Synchronisation en temps réel des rendez-vous clients, plannings d'équipe et rappels automatisés Avenqo CRM.",
    authMethod: "oauth2",
    docLink: "https://developers.google.com/calendar",
    setupInstructions: [
      "Disponible immédiatement via le module CRM",
      "Authentification Google OAuth 2.0 sécurisée par utilisateur / entreprise",
    ],
  },
  {
    key: "outlook_calendar",
    name: "Outlook Calendar",
    category: "crm",
    categoryLabel: "CRM & Calendrier",
    availability: "available",
    route: "/crm",
    capabilities: ["Événements", "Calendriers partagés", "Réunions Teams"],
    description: "Intégration Microsoft 365 Graph API pour synchroniser les rendez-vous professionnels Outlook.",
    authMethod: "oauth2",
    docLink: "https://learn.microsoft.com/en-us/graph/api/resources/calendar",
    setupInstructions: [
      "Accessible depuis le module CRM",
      "Connexion via compte professionnel Microsoft Azure AD / Entra ID",
    ],
  },
  {
    key: "google_ads",
    name: "Google Ads",
    category: "marketing",
    categoryLabel: "Marketing & Publicité",
    availability: "configuration_required",
    route: "/marketing",
    capabilities: ["Campagnes", "Conversions", "Performances", "Dépenses ROAS"],
    description: "Analyse prédictive des campagnes publicitaires Google Ads avec calcul du ROAS et optimisation par l'IA Centrale.",
    authMethod: "oauth2",
    envVars: ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET"],
    docLink: "https://developers.google.com/google-ads/api/docs/first-call/overview",
    setupInstructions: [
      "Renseigner le Developer Token approuvé par Google dans les paramètres de production",
      "Associer le compte administrateur (MCC) de votre agence ou entreprise",
    ],
  },
  {
    key: "meta_ads",
    name: "Meta Ads (Facebook & Instagram)",
    category: "marketing",
    categoryLabel: "Marketing & Publicité",
    availability: "configuration_required",
    route: "/marketing",
    capabilities: ["Campagnes", "Ensembles de pubs", "Insights", "Audiences personnalisées"],
    description: "Suivi des performances des publicités Meta Ads (Facebook & Instagram) et corrélation directe avec les ventes réelles.",
    authMethod: "oauth2",
    envVars: ["META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"],
    docLink: "https://developers.facebook.com/docs/marketing-apis",
    setupInstructions: [
      "Créer une application d'entreprise sur Meta for Developers avec la permission ads_read",
      "Générer un System User Token avec accès au compte publicitaire",
    ],
  },
  {
    key: "telnyx",
    name: "Telnyx Voice AI",
    category: "voice",
    categoryLabel: "Voix & Téléphonie",
    availability: "available",
    route: "/voice",
    capabilities: ["Appels entrants", "Contrôle d'appel", "WebRTC", "Trunk SIP", "Transcription temps réel"],
    description: "Agent vocal IA d'entreprise pour accueil téléphonique 24/7, qualification de prospects et réservation de rendez-vous.",
    authMethod: "sip_webrtc",
    docLink: "https://developers.telnyx.com/docs/voice",
    setupInstructions: [
      "Gérer vos numéros de téléphone et paramètres vocaux directement dans le module Voix IA",
      "Attribution automatique des numéros locaux ou sans frais",
    ],
  },
  {
    key: "stripe",
    name: "Stripe Facturation & Paiements",
    category: "billing",
    categoryLabel: "Facturation & Paiements",
    availability: "available",
    route: "/billing",
    capabilities: ["Abonnements", "Portail client sécurisé", "Factures PDF", "Crédits IA", "Webhooks"],
    description: "Gestion complète des abonnements SaaS, portail client en libre-service, paiements sécurisés et factures conformes.",
    authMethod: "api_key",
    docLink: "https://stripe.com/docs/billing",
    setupInstructions: [
      "Module de facturation natif Avenqo disponible sous /billing",
      "Gérez votre formule, téléchargez vos reçus et modifiez vos moyens de paiement sans friction",
    ],
  },
  {
    key: "shipstation",
    name: "ShipStation",
    category: "fulfillment",
    categoryLabel: "Logistique & Expédition",
    availability: "configuration_required",
    route: "/connections",
    capabilities: ["Commandes", "Expéditions", "Numéros de suivi", "Étiquettes d'envoi"],
    description: "Automatisation logistique : envoi des commandes aux transporteurs (Postes Canada, FedEx, UPS) et mise à jour des suivis.",
    authMethod: "api_key",
    envVars: ["SHIPSTATION_API_KEY", "SHIPSTATION_API_SECRET"],
    docLink: "https://www.shipstation.com/docs/api/",
    setupInstructions: [
      "Dans ShipStation, aller dans Paramètres > Compte > Clés API",
      "Générer une clé API et une clé secrète",
      "Enregistrer les clés pour la synchronisation automatique des expéditions",
    ],
  },
];

interface DatasetItem {
  id: string;
  name: string;
  type: string;
  module_code?: string;
  rows_count?: number;
  columns_count?: number;
  quality_score?: number;
  missing_values?: number;
  duplicates?: number;
  status: string;
  pipeline_status?: string;
  source_missing?: boolean;
  source_missing_message?: string | null;
  uploaded_at: string;
  columns?: Array<{ name: string; type?: string }>;
}

interface CommerceConnectionItem {
  id: string;
  provider: string;
  store_name?: string;
  store_url?: string;
  status: string;
  is_active: boolean;
  connection_status?: string;
  last_synced_at?: string | null;
  records_count?: number;
  sync_orders?: boolean;
  sync_products?: boolean;
  sync_customers?: boolean;
  sync_inventory?: boolean;
}

interface RetailSourceItem {
  source_type: "dataset" | "connector";
  source_id: string;
  dataset_id?: string | null;
  connection_id?: string | null;
  display_name: string;
  provider?: string | null;
  status: string;
  enabled: boolean;
  active?: boolean;
}

interface SyncLogItem {
  id: string;
  timestamp: string;
  provider: string;
  status: string;
  records_synced: number;
  records_updated: number;
  records_failed: number;
  message?: string;
}

export function ConnectionsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const company = getApplicationCatalog(locale).company;
  const connector = company.connectorHub;
  const session = useOptionalSession();
  const currentPlan = session?.identity?.company.subscription_plan?.toLowerCase() || "base";
  const planMaxMb = 250;
  const maxFileBytes = planMaxMb * 1024 * 1024;

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiRequestError | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);

  // Datasets & Files
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStage, setUploadStage] = useState<string | null>(null);
  const [uploadBytes, setUploadBytes] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Connectors
  const [connections, setConnections] = useState<CommerceConnectionItem[]>([]);
  const [retailSources, setRetailSources] = useState<RetailSourceItem[]>([]);
  const [syncHistory, setSyncHistory] = useState<SyncLogItem[]>([]);
  const loadRevision = useRef(0);

  // Preview & Delete Modals
  const [previewDataset, setPreviewDataset] = useState<DatasetItem | null>(null);
  const [deleteModalDataset, setDeleteModalDataset] = useState<DatasetItem | null>(null);

  // WooCommerce manual connection form modal
  const [selectedConnectorDetails, setSelectedConnectorDetails] = useState<CanonicalConnector | null>(null);
  const [connectorSearchQuery, setConnectorSearchQuery] = useState("");
  const [connectorCategoryFilter, setConnectorCategoryFilter] = useState<string>("all");
  const [platformCredentials, setPlatformCredentials] = useState<Record<string, { oauth_ready?: boolean; missing?: string[] }>>({});
  const [apiAccount, setApiAccount] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [isWooModalOpen, setIsWooModalOpen] = useState(false);
  const [wooStoreUrl, setWooStoreUrl] = useState("");
  const [wooKey, setWooKey] = useState("");
  const [wooSecret, setWooSecret] = useState("");

  const loadData = useCallback(async () => {
    const revision = ++loadRevision.current;
    setLoading(true);
    setLoadError(null);
    try {
      const headers = getAuthHeaders();
      const [dsRes, connRes, syncRes, sourceRes, platformRes] = await Promise.all([
        apiFetch("/api/v1/datasets", { headers }),
        apiFetch("/api/v1/connectors/connections", { headers }),
        apiFetch("/api/v1/connectors/sync/history?limit=10", { headers }),
        apiFetch("/api/v1/retail/sources", { headers }),
        apiFetch("/api/v1/connectors/platform-credentials", { headers }).catch(() => null),
      ]);
      if (revision !== loadRevision.current) return;

      if (dsRes && dsRes.ok) {
        const dsData = await dsRes.json();
        if (revision !== loadRevision.current) return;
        if (Array.isArray(dsData)) {
          setDatasets(dsData);
        }
      }

      if (connRes && connRes.ok) {
        const connData = await connRes.json();
        if (revision !== loadRevision.current) return;
        if (Array.isArray(connData)) {
          setConnections(connData.map((item) => ({
            ...item,
            store_name: item.display_name || item.store_name,
            store_url: item.external_account_id || item.store_url,
            connection_status: item.connection_status,
            is_active: item.connection_status === "CONNECTED",
            last_synced_at: item.last_successful_sync || item.last_synced_at,
          })));
        }
      }

      if (syncRes && syncRes.ok) {
        const sData = await syncRes.json();
        if (revision !== loadRevision.current) return;
        if (Array.isArray(sData)) {
          setSyncHistory(sData);
        }
      }
      if (sourceRes && sourceRes.ok) {
        const sourceData = await sourceRes.json();
        if (revision !== loadRevision.current) return;
        if (Array.isArray(sourceData)) setRetailSources(sourceData);
      }
      if (platformRes && platformRes.ok) {
        const platformData = await platformRes.json();
        if (revision !== loadRevision.current) return;
        if (platformData && typeof platformData === "object") setPlatformCredentials(platformData);
      }
    } catch (error) {
      if (revision === loadRevision.current) setLoadError(error instanceof ApiRequestError ? error : new ApiRequestError("backend_error"));
    } finally {
      if (revision === loadRevision.current) setLoading(false);
    }
  }, []);

  const setRetailSourceEnabled = async (source: RetailSourceItem, enabled: boolean) => {
    setActionLoading(true);
    setAlertError(null);
    try {
      const response = await fetch("/api/v1/retail/sources/enabled", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          source_type: source.source_type,
          source_id: source.source_id,
          enabled,
        }),
      });
      if (!response.ok) throw new Error(connector.unavailable);
      const persisted = (await response.json()) as RetailSourceItem;
      setRetailSources((items) => items.map((item) =>
        item.source_type === persisted.source_type && item.source_id === persisted.source_id
          ? persisted
          : item,
      ));
    } catch (error) {
      setAlertError(error instanceof Error ? error.message : connector.unavailable);
    } finally {
      setActionLoading(false);
    }
  };

  const selectRetailSource = async (source: RetailSourceItem) => {
    setActionLoading(true);
    setAlertError(null);
    try {
      const response = await fetch("/api/v1/retail/sources/active", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ source_type: source.source_type, source_id: source.source_id }),
      });
      if (!response.ok) throw new Error(connector.unavailable);
      const selected = (await response.json()) as RetailSourceItem;
      setRetailSources((items) => items.map((item) => ({
        ...item,
        active: item.source_type === selected.source_type && item.source_id === selected.source_id,
      })));
    } catch (error) {
      setAlertError(error instanceof Error ? error.message : connector.unavailable);
    } finally {
      setActionLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const clear = () => { loadRevision.current++; setConnections([]); setDatasets([]); setRetailSources([]); setSyncHistory([]); setAlertSuccess(null); };
    const changed = () => { clear(); void loadData(); };
    const expired = () => { clear(); setLoadError(new ApiRequestError("session_expired")); setLoading(false); };
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("avenqo-session") : null;
    if (channel) channel.onmessage = changed;
    window.addEventListener("avenqo:session-expired", expired);
    return () => { loadRevision.current++; channel?.close(); window.removeEventListener("avenqo:session-expired", expired); };
  }, [loadData]);

  // Auto-poll while any connection is syncing or processing until ready
  useEffect(() => {
    const isAnySyncing = connections.some(
      (c) => c.status === "syncing" || c.status === "processing"
    );
    if (!isAnySyncing) return;
    const timer = setInterval(() => {
      void loadData();
    }, 2500);
    return () => clearInterval(timer);
  }, [connections, loadData]);


  // File Upload Handlers
  const handleFiles = async (files: FileList | File[]) => {
    const validExtensions = [".csv", ".tsv", ".xls", ".xlsx", ".json", ".pdf", ".txt", ".parquet"];
    const fileList = Array.from(files);

    if (fileList.length === 0) return;

    for (const file of fileList) {
      const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
      if (!validExtensions.includes(ext)) {
        setAlertError(`Format de fichier non pris en charge pour "${file.name}". Formats acceptés : CSV, TSV, XLS, XLSX, PDF, JSON, TXT et Parquet.`);
        return;
      }
      if (file.size > maxFileBytes) {
        setAlertError(`Le fichier "${file.name}" dépasse la limite autorisée de ${planMaxMb} Mo pour votre forfait (${currentPlan.toUpperCase()}).`);
        return;
      }
    }

    setUploadProgress(0);
    setUploadStage(null);
    setUploadBytes(null);
    setAlertError(null);
    setAlertSuccess(null);

    try {
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        const formData = new FormData();
        formData.append("file", file);
        formData.append("module_code", "retail");

        setUploadStage(`Téléversement de "${file.name}" en cours...`);

        await new Promise<void>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open("POST", "/api/v1/datasets/upload");
          const headers = getAuthHeaders();
          for (const [key, value] of Object.entries(headers)) {
            xhr.setRequestHeader(key, value);
          }

          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable && event.total > 0) {
              const fileFraction = event.loaded / event.total;
              const totalPercent = Math.min(99, Math.round(((i + fileFraction) / fileList.length) * 100));
              const loadedMb = (event.loaded / (1024 * 1024)).toFixed(1);
              const totalMb = (event.total / (1024 * 1024)).toFixed(1);
              setUploadProgress(totalPercent);
              setUploadBytes(`${loadedMb} Mo / ${totalMb} Mo`);
              if (event.loaded >= event.total) {
                setUploadStage(`Traitement et analyse du jeu de données "${file.name}"...`);
              }
            }
          };

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve();
            } else {
              let detail = `Erreur lors de l'import de ${file.name}`;
              try {
                const data = JSON.parse(xhr.responseText);
                detail = data.detail || data.error?.message || detail;
              } catch {}
              reject(new Error(`${detail} (HTTP ${xhr.status})`));
            }
          };

          xhr.onerror = () => {
            reject(new Error(`Échec réseau lors du téléversement de "${file.name}".`));
          };

          xhr.ontimeout = () => {
            reject(new Error(`Délai d'attente dépassé lors du téléversement de "${file.name}".`));
          };

          xhr.send(formData);
        });
      }

      setUploadProgress(100);
      setUploadStage("Import et analyse terminés avec succès !");
      setAlertSuccess(`${fileList.length} ${fileList.length === 1 ? company.connectionsUploadCountOne : company.connectionsUploadCountOther}`);
      setTimeout(() => {
        setUploadProgress(null);
        setUploadStage(null);
        setUploadBytes(null);
      }, 2000);
      setTimeout(() => setAlertSuccess(null), 5000);
      loadData();
    } catch (err: any) {
      setUploadProgress(null);
      setUploadStage(null);
      setUploadBytes(null);
      setAlertError(err.message || company.connectionsProcessingError);
    }
  };

  // Sync Trigger
  const handleTriggerSync = async (connId?: string) => {
    setActionLoading(true);
    setAlertError(null);
    try {
      const url = connId
        ? `/api/v1/connectors/connections/${connId}/sync`
        : `/api/v1/connectors/sync`;
      const res = await fetch(url, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        throw new Error("Impossible de déclencher la synchronisation.");
      }
      setAlertSuccess(connector.syncing);
      if (connId) {
        setConnections((prev) =>
          prev.map((c) => (c.id === connId ? { ...c, status: "syncing" } : c))
        );
      } else {
        setConnections((prev) => prev.map((c) => ({ ...c, status: "syncing" })));
      }
      setTimeout(() => setAlertSuccess(null), 4000);
      loadData();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Connect WooCommerce
  const handleConnectWooCommerce = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    setAlertError(null);
    try {
      let formattedUrl = wooStoreUrl.trim();
      if (!formattedUrl.startsWith("http://") && !formattedUrl.startsWith("https://")) {
        formattedUrl = `https://${formattedUrl}`;
      }
      const res = await fetch("/api/v1/connectors/woocommerce/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          store_url: formattedUrl,
          consumer_key: wooKey.trim(),
          consumer_secret: wooSecret.trim(),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Échec de connexion WooCommerce.");
      }

      setIsWooModalOpen(false);
      setWooStoreUrl("");
      setWooKey("");
      setWooSecret("");
      setAlertSuccess(connector.connected);
      loadData();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Download Dataset
  const handleDownloadDataset = async (dataset: DatasetItem, format: "original" | "csv" | "xlsx" | "json") => {
    try {
      const endpoint = format === "original"
        ? `/api/v1/datasets/${dataset.id}/export/csv`
        : `/api/v1/datasets/${dataset.id}/export/${format}`;

      const res = await fetch(endpoint, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(connector.unavailable);

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${dataset.name.replace(/\.[^/.]+$/, "")}-${format}.${format === "original" ? "csv" : format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      setAlertError(connector.unavailable);
    }
  };

  // Delete Dataset
  const handleConfirmDelete = async () => {
    if (!deleteModalDataset) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/api/v1/datasets/${deleteModalDataset.id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(company.connectionsDeleteFailure);

      setDatasets((prev) => prev.filter((d) => d.id !== deleteModalDataset.id));
      setDeleteModalDataset(null);
      setAlertSuccess(company.connectionsDeleteSuccess);
      setTimeout(() => setAlertSuccess(null), 4000);
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const failedDatasets = datasets.filter(
    (d) => d.status === "failed" || d.pipeline_status === "failed" || d.status === "invalid"
  );

  if (loadError) return <RequestFailure error={loadError} retry={() => { void loadData(); }} />;
  if (loading) return <div role="status">{company.connectionsLoading}</div>;

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF]">
              <Database size={22} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {t.navigation.connections}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                {company.navConnectionsDescription}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-[#0076FF]" : ""} />
            <span>{connector.refresh}</span>
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
          >
            <Plus size={14} />
            <span>{company.connectionsAddFiles}</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".csv,.tsv,.xls,.xlsx,.json,.pdf,.doc,.docx,.parquet"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) handleFiles(e.target.files);
            }}
          />
        </div>
      </div>

      {/* Alerts */}
      {alertError && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={16} className="text-amber-600 dark:text-amber-400 shrink-0" />
            <span>{alertError}</span>
          </div>
          <button onClick={() => setAlertError(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      {alertSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span>{alertSuccess}</span>
          </div>
          <button onClick={() => setAlertSuccess(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Active tenant-owned Retail sources; state is read from and written to the API. */}
      <section className="p-5 bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4" aria-labelledby="active-retail-sources">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 id="active-retail-sources" className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">{t.integrations.activeSources}</h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">{t.integrations.activeSourcesDescription}</p>
          </div>
          <button onClick={loadData} disabled={loading} aria-label={connector.refresh} className="p-2 text-slate-500 hover:text-[#0076FF] disabled:opacity-50">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        {retailSources.filter((source) => source.source_type === "dataset").length === 0 ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">{t.integrations.noUploadedRetailSources}</p>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-white/[0.06]">
            {retailSources.filter((source) => source.source_type === "dataset").map((source) => {
              const dataset = datasets.find((item) => item.id === (source.dataset_id || source.source_id));
              return (
                <div key={`dataset:${source.source_id}`} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                      <Database size={15} className="shrink-0 text-[#0076FF]" />
                      <span className="truncate">{dataset?.name || source.display_name}</span>
                      <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${source.status === "ready" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/40" : source.status === "processing" ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border border-amber-200 dark:border-amber-800/40" : "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400 border border-red-200 dark:border-red-800/40"}`}>
                        {source.status === "ready" ? "Prêt (Ingéré)" : source.status === "processing" ? "En cours d'ingestion" : source.status}
                      </span>
                    </div>
                    <div className="ml-[23px] mt-1 text-[11px] text-slate-500">{t.integrations.uploadedRetailSource} · {source.enabled ? "Accessible IA" : "Désactivé pour l'IA"}</div>
                  </div>
                  {source.enabled && (source.active ? (
                    <span className="shrink-0 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-[11px] font-bold text-[#0076FF] border border-blue-200 dark:border-blue-800/50">{t.integrations.currentRetailSource}</span>
                  ) : (
                    <button
                      type="button"
                      disabled={actionLoading}
                      onClick={() => void selectRetailSource(source)}
                      className="shrink-0 px-2.5 py-1 rounded-lg text-xs font-semibold text-[#0076FF] hover:bg-blue-50 dark:hover:bg-blue-950/40 border border-blue-200/60 dark:border-blue-800/30 transition-colors disabled:opacity-50"
                    >
                      {t.integrations.selectSource}
                    </button>
                  ))}
                  <label className="flex shrink-0 items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span className="text-[11px] font-medium">{source.enabled ? "Accessible IA" : "Non accessible"}</span>
                    <input
                      type="checkbox"
                      role="switch"
                      aria-label={`Activer ${dataset?.name || source.display_name}`}
                      checked={source.enabled}
                      disabled={actionLoading || source.status !== "ready"}
                      onChange={(event) => void setRetailSourceEnabled(source, event.target.checked)}
                      className="h-4 w-4 accent-[#087CF0]"
                    />
                  </label>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Section A: Files from computer (Dropzone & Multi-upload) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <UploadCloud size={18} className="text-[#0076FF]" />
              <span>{connector.fileImportTitle}</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              {connector.fileImportSubtitle}
            </p>
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`p-8 border-2 border-dashed rounded-2xl text-center cursor-pointer transition-colors ${
            isDragging
              ? "border-[#0076FF] bg-blue-50/50 dark:bg-blue-950/20"
              : "border-slate-200 dark:border-white/[0.12] hover:border-slate-300 dark:hover:border-white/[0.2] bg-slate-50/50 dark:bg-[#060B13]/30"
          }`}
        >
          <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] flex items-center justify-center mx-auto mb-3">
            <UploadCloud size={24} />
          </div>
          <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
            {company.connectionsImportButton}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {company.connectionsNoDataFormats}
          </div>
        </div>

        {uploadProgress !== null && (
          <div className="space-y-1.5 pt-2">
            <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-semibold">
              <span>{uploadStage || company.connectionsPreparingData}</span>
              <span>{uploadBytes ? `${uploadBytes} · ` : ""}{uploadProgress}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden">
              <div
                className="h-full rounded-full bg-[#0076FF] transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Section B: Écosystème des 22 connecteurs Avenqo */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
                <Store size={18} className="text-[#0076FF]" />
                <span>{connector.commerceSources}</span>
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-[#00D4FF] border border-blue-200/50 dark:border-blue-800/40">
                22 connecteurs au catalogue
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">
              Plateformes e-commerce, places de marché, points de vente, CRM, marketing et voix IA intégrés à l'architecture Avenqo.
            </p>
          </div>

          {/* Search bar */}
          <div className="relative min-w-[240px] sm:w-72">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={connectorSearchQuery}
              onChange={(e) => setConnectorSearchQuery(e.target.value)}
              placeholder="Rechercher un connecteur..."
              className="w-full pl-9 pr-3 py-1.5 rounded-xl text-xs bg-slate-50 dark:bg-white/[0.04] border border-slate-200 dark:border-white/[0.08] text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:border-[#0076FF]"
            />
            {connectorSearchQuery && (
              <button
                onClick={() => setConnectorSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Category Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 pb-1">
          {[
            { id: "all", label: "Tous (22)" },
            { id: "commerce", label: "E-Commerce (7)" },
            { id: "marketplace", label: "Places de marché (5)" },
            { id: "pos", label: "Points de vente (3)" },
            { id: "crm_marketing", label: "CRM & Marketing (4)" },
            { id: "voice_billing", label: "Voix & Facturation (3)" },
          ].map((cat) => {
            const isActive = connectorCategoryFilter === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setConnectorCategoryFilter(cat.id)}
                className={`px-3 py-1 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  isActive
                    ? "bg-[#0076FF] text-white shadow-xs"
                    : "bg-slate-100 hover:bg-slate-200/80 dark:bg-white/[0.05] dark:hover:bg-white/[0.08] text-slate-600 dark:text-slate-300"
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* Connectors Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CANONICAL_22_CONNECTORS.filter((item) => {
            // Filter by category
            if (connectorCategoryFilter === "commerce" && item.category !== "commerce") return false;
            if (connectorCategoryFilter === "marketplace" && item.category !== "marketplace") return false;
            if (connectorCategoryFilter === "pos" && item.category !== "pos") return false;
            if (connectorCategoryFilter === "crm_marketing" && item.category !== "crm" && item.category !== "marketing") return false;
            if (connectorCategoryFilter === "voice_billing" && item.category !== "voice" && item.category !== "billing" && item.category !== "fulfillment") return false;

            // Filter by search query
            if (connectorSearchQuery.trim()) {
              const q = connectorSearchQuery.toLowerCase();
              return (
                item.name.toLowerCase().includes(q) ||
                item.categoryLabel.toLowerCase().includes(q) ||
                item.description.toLowerCase().includes(q) ||
                item.capabilities.some((c) => c.toLowerCase().includes(q))
              );
            }
            return true;
          }).map((item) => {
            const conn = connections.find((c) => c.provider.toLowerCase() === item.key.toLowerCase());
            const state = conn?.status?.toUpperCase();
            const isSyncing = state === "SYNCING" || state === "PROCESSING";
            const isError = conn && (state === "ERROR" || state === "FAILED" || state === "REAUTH_REQUIRED");
            const isConnected = conn?.connection_status === "CONNECTED";
            const missingSandbox = platformCredentials[item.key]?.missing?.length
              ? platformCredentials[item.key].missing
              : item.envVars;
            const tenantKeyProvider = ["adobe_commerce", "squarespace_commerce", "prestashop", "shipstation"].includes(item.key);

            return (
              <div
                key={item.key}
                className="p-5 rounded-2xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200/60 dark:border-white/[0.06] flex flex-col justify-between hover:border-slate-300 dark:hover:border-white/[0.12] transition-colors"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-extrabold text-sm text-slate-900 dark:text-[#F4F7FB]">{item.name}</span>
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-slate-200/80 dark:bg-white/[0.08] text-slate-600 dark:text-slate-300">
                          {item.categoryLabel}
                        </span>
                      </div>
                    </div>

                    {/* Status Pill */}
                    {isSyncing ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-blue-400 animate-pulse shrink-0">
                        <RefreshCw size={10} className="animate-spin" />
                        <span>{connector.syncing}</span>
                      </span>
                    ) : isError ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400 shrink-0">
                        <AlertTriangle size={10} />
                        <span>{connector.error}</span>
                      </span>
                    ) : isConnected ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 shrink-0">
                        <CheckCircle2 size={10} />
                        <span>{connector.connected}</span>
                      </span>
                    ) : item.availability === "available" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 shrink-0">
                        <CheckCircle2 size={10} />
                        <span>{connector.available}</span>
                      </span>
                    ) : item.availability === "partner_approval_pending" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border border-purple-200/60 dark:border-purple-800/40 shrink-0">
                        <Clock size={10} />
                        <span>Approbation requise</span>
                      </span>
                    ) : item.availability === "configuration_required" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200/60 dark:border-amber-800/40 shrink-0">
                        <AlertCircle size={10} />
                        <span>Config requise</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200/70 dark:bg-white/[0.08] text-slate-500 dark:text-slate-400 shrink-0">
                        <Lock size={10} />
                        <span>{connector.comingSoon}</span>
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-2 line-clamp-2">
                    {isConnected && conn?.store_name ? conn.store_name : item.description}
                  </p>
                  {isConnected && conn?.store_url && (
                    <p className="mt-1 break-all text-[11px] text-[#0076FF] font-medium">{conn.store_url}</p>
                  )}

                  {/* Capabilities Tags */}
                  <div className="flex flex-wrap gap-1 mt-3">
                    {item.capabilities.slice(0, 3).map((cap) => (
                      <span
                        key={cap}
                        className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-white dark:bg-white/[0.04] border border-slate-200/60 dark:border-white/[0.06] text-slate-600 dark:text-slate-300"
                      >
                        {cap}
                      </span>
                    ))}
                    {item.capabilities.length > 3 && (
                      <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 dark:bg-white/[0.03] text-slate-400">
                        +{item.capabilities.length - 3}
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-white/[0.06] flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">
                    {item.authMethod === "oauth2"
                      ? "OAuth 2.0"
                      : item.authMethod === "oauth2_pkce"
                      ? "OAuth PKCE"
                      : item.authMethod === "sip_webrtc"
                      ? "WebRTC / SIP"
                      : "Clé d'API"}
                  </span>

                  {isConnected && conn ? (
                    <button
                      onClick={() => handleTriggerSync(conn.id)}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-xl bg-blue-50 text-[#0076FF] hover:bg-blue-100 dark:bg-white/[0.08] dark:text-[#00D4FF] text-xs font-semibold transition-colors cursor-pointer"
                    >
                      {connector.sync}
                    </button>
                  ) : item.key === "shopify" ? (
                    <button
                      onClick={async () => {
                        const knownShop = (isError && conn?.store_url) ? conn.store_url : "";
                        const shop = knownShop || prompt(connector.shopDomainTitle);
                        if (!shop) return;
                        setActionLoading(true);
                        try {
                          const res = await apiFetch("/api/v1/connectors/shopify/authorize", {
                            method: "POST",
                            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
                            body: JSON.stringify({ shop_domain: shop.trim() }),
                          });
                          if (!res.ok) {
                            const err = await res.json().catch(() => ({}));
                            throw new Error(err.detail || connector.launchFailed);
                          }
                          const data = await res.json();
                          if (data.authorization_url) {
                            window.location.href = data.authorization_url;
                          }
                        } catch (err: any) {
                          setAlertError(err.message || connector.launchFailed);
                        } finally {
                          setActionLoading(false);
                        }
                      }}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                    >
                      {connector.connect}
                    </button>
                  ) : item.key === "woocommerce" ? (
                    <button
                      onClick={() => setIsWooModalOpen(true)}
                      className="px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                    >
                      {connector.connect}
                    </button>
                  ) : item.route && item.route !== "/connections" ? (
                    <Link
                      href={item.route}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200/80 dark:bg-white/[0.08] dark:hover:bg-white/[0.12] text-[#0076FF] dark:text-[#00D4FF] text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <span>Module</span>
                      <ArrowUpRight size={12} />
                    </Link>
                  ) : (
                    <button
                      onClick={() => {
                        setApiAccount("");
                        setApiKey("");
                        setApiSecret("");
                        setSelectedConnectorDetails(item);
                      }}
                      className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-slate-700 dark:text-slate-300 text-xs font-semibold transition-colors cursor-pointer"
                    >
                      {tenantKeyProvider
                        ? "Enregistrer la clé"
                        : missingSandbox && missingSandbox.length > 0
                          ? `Sandbox : ${missingSandbox[0]}`
                          : "Détails & API"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
{/* Section C: Connected sources */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-500" />
              <span>{connector.connectedStores}</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              {connector.commerceSources}
            </p>
          </div>

          {connections.length > 0 && (
            <button
              onClick={() => handleTriggerSync()}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            >
              <RefreshCw size={13} className={actionLoading ? "animate-spin" : ""} />
              <span>{connector.sync}</span>
            </button>
          )}
        </div>

        {connections.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            {company.connectionsNoDataTitle}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connections.map((conn) => (
              (() => {
                const source = retailSources.find((item) =>
                  item.source_type === "connector" && item.connection_id === conn.id,
                );
                const connected = conn.connection_status === "CONNECTED";
                return <div
                key={conn.id}
                className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06] space-y-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="font-bold text-xs text-slate-900 dark:text-white capitalize flex items-center gap-2">
                    <Store size={14} className="text-[#0076FF]" />
                    <span>{conn.provider} — {conn.store_name || conn.store_url || "Boutique"}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${connected ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400" : "bg-slate-200 text-slate-600 dark:bg-white/[0.08] dark:text-slate-300"}`}>
                    {connected ? t.integrations.statusConnected : conn.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                  <div>
                    {connector.lastSync}: {conn.last_synced_at ? new Date(conn.last_synced_at).toLocaleString(locale) : connector.neverSynced}
                  </div>
                  <div className="text-right font-semibold text-slate-700 dark:text-slate-300">
                    {conn.records_count || 0} {t.integrations.recordsCount}
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200/60 dark:border-white/[0.06]">
                  {source && (
                    <label className="mr-auto flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                      <span>{source.enabled ? t.integrations.sourceEnabled : t.integrations.sourceDisabled}</span>
                      <input
                        type="checkbox"
                        role="switch"
                        aria-label={`Activer ${conn.provider} ${conn.store_name || conn.store_url || ""}`}
                        checked={source.enabled}
                        disabled={actionLoading || !connected}
                        onChange={(event) => void setRetailSourceEnabled(source, event.target.checked)}
                        className="h-4 w-4 accent-[#087CF0]"
                      />
                    </label>
                  )}
                  <button
                    onClick={() => handleTriggerSync(conn.id)}
                    disabled={actionLoading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 text-[#0076FF] dark:bg-white/[0.08] dark:text-[#00D4FF] text-[11px] font-semibold transition-colors cursor-pointer"
                  >
                    <RefreshCw size={12} className={actionLoading ? "animate-spin" : ""} />
                    <span>{connector.sync}</span>
                  </button>
                </div>
              </div>;
              })()
            ))}
          </div>
        )}
      </div>

      {/* Section D: Synchronization history */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
            <Clock size={18} className="text-[#0076FF]" />
            <span>{t.integrations.drawerLogsTitle}</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
            {connector.sync}
          </p>
        </div>

        {syncHistory.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            {connector.neverSynced}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">{connector.lastSync}</th>
                  <th className="py-3 px-4">{connector.connection}</th>
                  <th className="py-3 px-4">{connector.records}</th>
                  <th className="py-3 px-4">{connector.sync}</th>
                  <th className="py-3 px-4">{connector.error}</th>
                  <th className="py-3 px-4 text-right">{t.integrations.statusConnected}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {syncHistory.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02]">
                    <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                      {new Date(log.timestamp).toLocaleString(locale)}
                    </td>
                    <td className="py-3 px-4 font-bold capitalize text-slate-800 dark:text-white">
                      {log.provider}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-300">
                      {log.records_synced}
                    </td>
                    <td className="py-3 px-4 font-mono text-emerald-600 dark:text-emerald-400">
                      +{log.records_updated}
                    </td>
                    <td className="py-3 px-4 font-mono text-rose-600">
                      {log.records_failed}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 size={12} />
                        <span>{connector.ready}</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Section E: Imported datasets */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <Layers size={18} className="text-[#0076FF]" />
              <span>{connector.fileImportTitle} ({datasets.length})</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              {connector.capabilities}
            </p>
          </div>
        </div>

        {datasets.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-400 dark:text-slate-500">
            {company.connectionsNoDataTitle}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">{connector.fileImportTitle}</th>
                  <th className="py-3 px-4">{company.connectionsStatRowsLabel}</th>
                  <th className="py-3 px-4">{company.connectionsStatColumnsLabel}</th>
                  <th className="py-3 px-4">{locale.startsWith("fr") ? "Qualité des données" : "Data Quality"}</th>
                  <th className="py-3 px-4">{company.connectionsStatUpdatedLabel}</th>
                  <th className="py-3 px-4">{t.integrations.statusConnected}</th>
                  <th className="py-3 px-4 text-right">{connector.connection}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {datasets.map((ds) => (
                  <tr key={ds.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02]">
                    <td className="py-3 px-4 font-bold text-slate-900 dark:text-white">
                      <div className="flex items-center gap-2">
                        <FileText size={15} className="text-[#0076FF] shrink-0" />
                        <span className="truncate max-w-xs">{ds.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                      {ds.rows_count?.toLocaleString() || "—"}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                      {ds.columns_count || ds.columns?.length || "—"}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 text-[10px] font-bold font-mono">
                        {ds.quality_score != null
                          ? `${Math.round(ds.quality_score > 1 ? ds.quality_score : ds.quality_score * 100)} %`
                          : "100 %"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                      {ds.uploaded_at
                        ? new Date(ds.uploaded_at).toLocaleDateString(locale, {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })
                        : "—"}
                    </td>
                    <td className="py-3 px-4">
                      {ds.source_missing || ds.pipeline_status === "source_missing" ? (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 text-[10px] font-bold"
                          title={ds.source_missing_message || "Fichier source indisponible"}
                        >
                          <AlertTriangle size={12} className="shrink-0 text-amber-500" />
                          <span>{company.connectionsFileEmptyError}</span>
                        </span>
                      ) : ds.pipeline_status === "analyzing" || ds.status === "analyzing" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-600 dark:text-blue-400">
                          <RefreshCw size={12} className="animate-spin" />
                          <span>{connector.processing}</span>
                        </span>
                      ) : ds.status === "failed" || ds.pipeline_status === "failed" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-600 dark:text-rose-400">
                          <AlertCircle size={12} />
                          <span>{connector.error}</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 size={12} />
                          <span>{connector.ready}</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {ds.source_missing || ds.pipeline_status === "source_missing" ? (
                          <button
                            onClick={() => fileInputRef.current?.click()}
                            title={company.connectionsImportAnother}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 text-amber-700 dark:text-amber-300 text-[11px] font-semibold transition-colors cursor-pointer"
                          >
                            <UploadCloud size={12} />
                            <span>{company.connectionsImportAnother}</span>
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => setPreviewDataset(ds)}
                              title={connector.capabilities}
                              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-slate-400 cursor-pointer"
                            >
                              <Eye size={14} />
                            </button>
                            <button
                              onClick={() => handleDownloadDataset(ds, "csv")}
                              title={connector.records}
                              className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-[#0076FF] cursor-pointer"
                            >
                              <Download size={14} />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => setDeleteModalDataset(ds)}
                          title={company.connectionsDeleteData}
                          className="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/20 text-slate-400 hover:text-rose-600 cursor-pointer"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Section F: Failed imports requiring attention */}
      {failedDatasets.length > 0 && (
        <div className="p-6 rounded-2xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-800/40 shadow-xs space-y-3">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-bold text-sm">
            <AlertTriangle size={18} />
            <span>{company.connectionsAttentionRequired} ({failedDatasets.length})</span>
          </div>
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {company.connectionsProcessingError}
          </p>
          <div className="space-y-2">
            {failedDatasets.map((fd) => (
              <div
                key={fd.id}
                className="p-3 rounded-xl bg-white dark:bg-[#0B132B] border border-amber-200/60 dark:border-amber-800/40 flex items-center justify-between text-xs"
              >
                <div className="font-semibold text-slate-800 dark:text-white">
                  {fd.name}
                </div>
                <button
                  onClick={() => setDeleteModalDataset(fd)}
                  className="px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 text-[11px] font-semibold cursor-pointer"
                >
                  {t.common.deletePermanently}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal: Preview Dataset */}
      {previewDataset && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/[0.06]">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {connector.capabilities}: {previewDataset.name}
                </h3>
                <div className="text-xs text-slate-400 mt-0.5">
                  {previewDataset.rows_count || 0} {company.connectionsStatRowsLabel} {String.fromCharCode(0xB7)} {previewDataset.columns_count || 0} {company.connectionsStatColumnsLabel}
                </div>
              </div>
              <button
                onClick={() => setPreviewDataset(null)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-400 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3">
              {(previewDataset.source_missing || previewDataset.pipeline_status === "source_missing") && (
                <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-800/50 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2.5">
                  <AlertTriangle size={16} className="shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                  <div>
                    <div className="font-bold">{company.connectionsFileEmptyError}</div>
                    <div className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5">
                      {previewDataset.source_missing_message ||
                        "Le fichier original n'est plus accessible sur le stockage. Utilisez le bouton Réimporter pour recharger ce fichier et relancer l'analyse."}
                    </div>
                  </div>
                </div>
              )}
              <div className="text-xs font-bold text-slate-700 dark:text-slate-300">
                {company.connectionsStatColumnsLabel}:
              </div>
              <div className="flex flex-wrap gap-2 max-h-60 overflow-y-auto">
                {previewDataset.columns && previewDataset.columns.length > 0 ? (
                  previewDataset.columns.map((col, idx) => (
                    <div
                      key={idx}
                      className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#111D3D] text-xs text-slate-800 dark:text-[#F4F7FB] border border-slate-200/60 dark:border-white/[0.06]"
                    >
                      <span className="font-semibold">{col.name}</span>
                      {col.type && (
                        <span className="ml-1.5 text-[10px] text-slate-400 uppercase font-mono">
                          ({col.type})
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-400">{connector.ready}</div>
                )}
              </div>
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-100 dark:border-white/[0.06]">
              <button
                onClick={() => setPreviewDataset(null)}
                className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.1] text-xs font-semibold text-slate-800 dark:text-white cursor-pointer"
              >
                {t.common.close}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Delete Dataset Confirmation */}
      {deleteModalDataset && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="p-2 rounded-xl bg-rose-50 dark:bg-rose-950/40">
                <Trash2 size={20} />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                {company.connectionsDeleteTitle}
              </h3>
            </div>

            <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
              <p>
                {company.connectionsDeleteWarning}{" "}
                <strong>"{deleteModalDataset.name}"</strong> ?
              </p>
              <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/40 text-[11px] text-amber-800 dark:text-amber-300">
                <strong>{company.connectionsDeleteWarning}</strong>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-white/[0.06]">
              <button
                onClick={() => setDeleteModalDataset(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
              >
                {company.connectionsDeleteCancel}
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
              >
                {company.connectionsDeletePermanently}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Connect WooCommerce */}
      {isWooModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.12] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Store size={18} className="text-[#0076FF]" />
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {connector.wooTitle}
                </h3>
              </div>
              <button
                onClick={() => setIsWooModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-400 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleConnectWooCommerce} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  {connector.wooStoreUrl}
                </label>
                <input
                  type="text"
                  required
                  value={wooStoreUrl}
                  onChange={(e) => setWooStoreUrl(e.target.value)}
                  placeholder={connector.wooStoreUrlHint}
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  {connector.wooConsumerKey}
                </label>
                <input
                  type="text"
                  required
                  value={wooKey}
                  onChange={(e) => setWooKey(e.target.value)}
                  placeholder="ck_..."
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  {connector.wooConsumerSecret}
                </label>
                <input
                  type="password"
                  required
                  value={wooSecret}
                  onChange={(e) => setWooSecret(e.target.value)}
                  placeholder="cs_..."
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.08] text-xs text-slate-800 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-[#0076FF]"
                />
              </div>

              <div className="text-[11px] text-slate-400">
                {connector.wooManualDescription}
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setIsWooModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                >
                  {actionLoading ? connector.connecting : connector.wooConnectManual}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    
      {/* Modal: Connector Specifications & Developer Setup */}
      {selectedConnectorDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.08] shadow-2xl p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-extrabold text-slate-900 dark:text-[#F4F7FB]">
                    {selectedConnectorDetails.name}
                  </h3>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-[#00D4FF]">
                    {selectedConnectorDetails.categoryLabel}
                  </span>
                </div>
                <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">
                  {selectedConnectorDetails.description}
                </p>
              </div>
              <button
                onClick={() => setSelectedConnectorDetails(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 pt-2 text-xs">
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200/60 dark:border-white/[0.06] space-y-1.5">
                <div className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                  <Info size={14} className="text-[#0076FF]" />
                  <span>Protocole d'authentification & Capacités</span>
                </div>
                <div className="text-slate-600 dark:text-slate-400">
                  Méthode : <strong className="text-slate-900 dark:text-white uppercase">{selectedConnectorDetails.authMethod}</strong>
                </div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {selectedConnectorDetails.capabilities.map((c) => (
                    <span key={c} className="px-2 py-0.5 rounded bg-white dark:bg-white/[0.05] border border-slate-200 dark:border-white/[0.08] text-[10px]">
                      {c}
                    </span>
                  ))}
                </div>
              </div>

              {selectedConnectorDetails.envVars && selectedConnectorDetails.envVars.length > 0 && (
                <div className="p-3 rounded-xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40 space-y-1.5">
                  <div className="font-bold text-amber-900 dark:text-amber-200 flex items-center gap-1.5">
                    <AlertCircle size={14} className="text-amber-600" />
                    <span>Identifiants Sandbox manquants — aucun état Connecté</span>
                  </div>
                  <ul className="list-disc list-inside text-amber-800 dark:text-amber-300 font-mono text-[11px] space-y-0.5">
                    {selectedConnectorDetails.envVars.map((v) => (
                      <li key={v}>{v}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedConnectorDetails.setupInstructions && (
                <div className="space-y-1.5">
                  <div className="font-bold text-slate-800 dark:text-slate-200">
                    Étapes de configuration du compte développeur :
                  </div>
                  <ol className="list-decimal list-inside space-y-1 text-slate-600 dark:text-slate-400 pl-1 leading-relaxed">
                    {selectedConnectorDetails.setupInstructions.map((step, idx) => (
                      <li key={idx}>{step.replaceAll("{origin}", typeof window === "undefined" ? "" : window.location.origin)}</li>
                    ))}
                  </ol>
                </div>
              )}
              {["adobe_commerce", "squarespace_commerce", "prestashop", "shipstation"].includes(selectedConnectorDetails.key) ? (
                <form
                  className="space-y-2"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    setActionLoading(true);
                    setAlertError(null);
                    try {
                      await apiFetch("/api/v1/connectors/tenant-api-credentials", {
                        method: "POST",
                        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
                        body: JSON.stringify({
                          provider: selectedConnectorDetails.key,
                          account_id: apiAccount,
                          api_key: apiKey,
                          api_secret: apiSecret || undefined,
                        }),
                      });
                      setApiKey("");
                      setApiSecret("");
                      setAlertSuccess("Clé enregistrée pour cette entreprise. Le connecteur n'est pas marqué Connecté.");
                      setSelectedConnectorDetails(null);
                      await loadData();
                    } catch (error: any) {
                      setAlertError(error?.publicMessage || "Enregistrement impossible.");
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                >
                  <p className="text-xs text-slate-500">La clé reste liée à cette entreprise et n'affiche pas Connecté tant qu'elle n'est pas vérifiée.</p>
                  <input value={apiAccount} onChange={(event) => setApiAccount(event.target.value)} required minLength={3} placeholder="Identifiant de la boutique sandbox" className="w-full rounded-xl border border-slate-200 dark:border-white/10 bg-transparent px-3 py-2 text-xs" />
                  <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} required type="password" autoComplete="off" placeholder="Clé API" className="w-full rounded-xl border border-slate-200 dark:border-white/10 bg-transparent px-3 py-2 text-xs" />
                  <input value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} type="password" autoComplete="off" placeholder="Secret API, si le fournisseur en exige un" className="w-full rounded-xl border border-slate-200 dark:border-white/10 bg-transparent px-3 py-2 text-xs" />
                  <button type="submit" disabled={actionLoading} className="px-3 py-2 rounded-xl bg-[#0076FF] text-white text-xs font-semibold disabled:opacity-50">Enregistrer pour cette entreprise</button>
                </form>
              ) : selectedConnectorDetails.envVars && selectedConnectorDetails.envVars.length > 0 ? (
                <p className="text-xs text-amber-800 dark:text-amber-200">
                  OAuth ne démarre pas : l'application Sandbox n'est pas configurée. Le connecteur n'est pas marqué Connecté.
                </p>
              ) : null}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-white/[0.06]">
              {selectedConnectorDetails.docLink ? (
                <a
                  href={selectedConnectorDetails.docLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-[#0076FF] hover:underline"
                >
                  <span>Documentation développeur</span>
                  <ExternalLink size={12} />
                </a>
              ) : <div />}

              <button
                onClick={() => setSelectedConnectorDetails(null)}
                className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-white/[0.08] dark:hover:bg-white/[0.12] text-xs font-semibold text-slate-700 dark:text-white cursor-pointer"
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

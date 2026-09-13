import type { LocaleCode } from "./types";

export type AppTranslations = {
  brand: {
    name: string;
    tagline: string;
  };
  navigation: {
    dashboard: string;
    retailAi: string;
    crmAi: string;
    accountingAi: string;
    marketingAi: string;
    voiceAi: string;
    ocrAi: string;
    chatbotsAi: string;
    automations: string;
    agentsAi: string;
    integrations: string;
    dataHub: string;
    settings: string;
    support: string;
    team: string;
    billing: string;
  };
  shell: {
    searchPlaceholder: string;
    commandPaletteShortcut: string;
    activeTenant: string;
    switchTenant: string;
    notifications: string;
    noNotifications: string;
    allNotificationsRead: string;
    themeToggle: string;
    copilotButton: string;
    aiCredits: string;
    aiCreditsUsed: string;
    upgradePlan: string;
    profile: string;
    signOut: string;
    company: string;
    role: string;
    collapseSidebar: string;
    expandSidebar: string;
  };
  commandPalette: {
    title: string;
    placeholder: string;
    pagesGroup: string;
    actionsGroup: string;
    integrationsGroup: string;
    noResults: string;
    navigateHint: string;
    selectHint: string;
    closeHint: string;
    actionSync: string;
    actionCleanData: string;
    actionGenerateReport: string;
    actionAskCopilot: string;
  };
  copilot: {
    title: string;
    subtitle: string;
    statusActive: string;
    statusThinking: string;
    contextBadge: string;
    quickPills: {
      analyzeSales: string;
      forecastDemand: string;
      detectAnomalies: string;
      generateReport: string;
    };
    inputPlaceholder: string;
    sendButton: string;
    confidenceLabel: string;
    groundedBadge: string;
    disclaimer: string;
    emptyPrompt: string;
    errorPrompt: string;
    retry: string;
  };
  dashboard: {
    greetingMorning: string;
    greetingAfternoon: string;
    greetingEvening: string;
    dateRange7d: string;
    dateRange30d: string;
    dateRangeQuarter: string;
    dateRangeCustom: string;
    revenue: string;
    orders: string;
    customers: string;
    aov: string;
    conversionRate: string;
    trendTitle: string;
    trendSubtitle: string;
    categorySplitTitle: string;
    regionalSalesTitle: string;
    aiInsightTitle: string;
    aiInsightEmpty: string;
    aiInsightInsufficient: string;
    aiInsightConfidence: string;
    recommendationAction: string;
  };
  retail: {
    overview: string;
    sales: string;
    products: string;
    customers: string;
    inventory: string;
    forecasts: string;
    anomalies: string;
    recommendations: string;
    rawVsCleaned: string;
    rawTitle: string;
    cleanedTitle: string;
    qualityScore: string;
    completeness: string;
    consistency: string;
    validity: string;
    freshness: string;
    demandForecastTitle: string;
    forecastDisclaimer: string;
    overstockAlert: string;
    stockoutRiskAlert: string;
  };
  integrations: {
    title: string;
    subtitle: string;
    categoryAll: string;
    categoryEcommerce: string;
    categoryMarketing: string;
    categoryCrm: string;
    categoryAccounting: string;
    categoryData: string;
    categoryAutomation: string;
    syncNow: string;
    syncing: string;
    lastSynced: string;
    recordsCount: string;
    statusConnected: string;
    statusSyncing: string;
    statusNeedsAttention: string;
    statusDisconnected: string;
    drawerTitle: string;
    drawerLogsTitle: string;
    noLogs: string;
  };
};

const frApp: AppTranslations = {
  brand: {
    name: "AVENQO",
    tagline: "AI FOR A SMARTER TOMORROW",
  },
  navigation: {
    dashboard: "Tableau de bord",
    retailAi: "Retail AI",
    crmAi: "CRM AI",
    accountingAi: "Comptabilité AI",
    marketingAi: "Marketing AI",
    voiceAi: "Voice AI",
    ocrAi: "OCR AI",
    chatbotsAi: "Chatbots IA",
    automations: "Automations",
    agentsAi: "Agents IA",
    integrations: "Intégrations",
    dataHub: "Données & Nettoyage",
    settings: "Paramètres",
    support: "Support & SLA",
    team: "Équipe & Accès",
    billing: "Facturation & Plans",
  },
  shell: {
    searchPlaceholder: "Rechercher ou exécuter (Ctrl+K)...",
    commandPaletteShortcut: "Ctrl+K",
    activeTenant: "Organisation active",
    switchTenant: "Changer d'organisation",
    notifications: "Notifications",
    noNotifications: "Aucune alerte non lue",
    allNotificationsRead: "Toutes les alertes sont traitées",
    themeToggle: "Basculer le thème",
    copilotButton: "Avenqo Copilot",
    aiCredits: "Crédits IA",
    aiCreditsUsed: "consommés ce mois-ci",
    upgradePlan: "Augmenter le quota",
    profile: "Profil & Sécurité",
    signOut: "Déconnexion",
    company: "Entreprise",
    role: "Rôle",
    collapseSidebar: "Réduire le menu",
    expandSidebar: "Agrandir le menu",
  },
  commandPalette: {
    title: "Palette de Commandes Rapides",
    placeholder: "Tapez une commande, une page ou une action...",
    pagesGroup: "Modules & Vues",
    actionsGroup: "Actions Rapides",
    integrationsGroup: "Connecteurs & Sources",
    noResults: "Aucun résultat trouvé pour votre recherche.",
    navigateHint: "pour naviguer",
    selectHint: "pour ouvrir",
    closeHint: "pour quitter",
    actionSync: "Déclencher une synchronisation manuelle",
    actionCleanData: "Lancer le pipeline de nettoyage IA",
    actionGenerateReport: "Exporter le rapport exécutif en PDF",
    actionAskCopilot: "Poser une question à Avenqo Copilot",
  },
  copilot: {
    title: "Avenqo Copilot",
    subtitle: "Intelligence Opérationnelle Contextuelle",
    statusActive: "En ligne & connecté aux sources réelles",
    statusThinking: "Analyse des flux et calcul des projections...",
    contextBadge: "Contexte actif",
    quickPills: {
      analyzeSales: "Analyser mes ventes",
      forecastDemand: "Prévoir ma demande",
      detectAnomalies: "Détecter les anomalies",
      generateReport: "Générer un rapport",
    },
    inputPlaceholder: "Posez une question sur vos ventes, stocks ou marges...",
    sendButton: "Envoyer",
    confidenceLabel: "Indice de certitude statistique",
    groundedBadge: "Grounding certifié sur données normalisées",
    disclaimer: "Les suggestions IA reposent sur les données réelles consolidées. Vérifiez avant toute décision réglementaire.",
    emptyPrompt: "Sélectionnez une action rapide ou saisissez une question pour obtenir une analyse instantanée de vos flux.",
    errorPrompt: "Impossible de contacter l'agent Copilot. Veuillez vérifier votre connexion ou vos crédits d'API.",
    retry: "Réessayer l'analyse",
  },
  dashboard: {
    greetingMorning: "Bonjour",
    greetingAfternoon: "Bon après-midi",
    greetingEvening: "Bonsoir",
    dateRange7d: "7 derniers jours",
    dateRange30d: "30 derniers jours",
    dateRangeQuarter: "Ce trimestre",
    dateRangeCustom: "Plage personnalisée",
    revenue: "Chiffre d'affaires",
    orders: "Commandes",
    customers: "Clients actifs",
    aov: "Panier moyen (AOV)",
    conversionRate: "Taux de conversion",
    trendTitle: "Tendance Combinée : Revenus & Commandes",
    trendSubtitle: "Évolution temporelle consolidée multi-sources",
    categorySplitTitle: "Répartition des ventes par catégorie",
    regionalSalesTitle: "Performance des ventes régionales",
    aiInsightTitle: "Avenqo AI Insight",
    aiInsightEmpty: "Aucun flux de données disponible pour générer une analyse.",
    aiInsightInsufficient: "Données insuffisantes pour analyse. Veuillez synchroniser un connecteur e-commerce.",
    aiInsightConfidence: "Niveau de confiance IA",
    recommendationAction: "Appliquer la recommandation",
  },
  retail: {
    overview: "Vue d'ensemble",
    sales: "Ventes",
    products: "Produits",
    customers: "Clients",
    inventory: "Inventaire",
    forecasts: "Prévisions",
    anomalies: "Anomalies",
    recommendations: "Recommandations",
    rawVsCleaned: "Comparatif Données Brutes vs Données Nettoyées IA",
    rawTitle: "Données Brutes (Multi-sources)",
    cleanedTitle: "Données Normalisées par IA (AVENQO Engine)",
    qualityScore: "Score de Qualité des Données (DQS)",
    completeness: "Complétude",
    consistency: "Cohérence",
    validity: "Validité",
    freshness: "Fraîcheur",
    demandForecastTitle: "Prévisions de Demande & Réapprovisionnement",
    forecastDisclaimer: "Modèle prédictif basé sur l'historique de ventes. Ne constitue pas une garantie contractuelle de vente.",
    overstockAlert: "Alerte Surstock Détecté",
    stockoutRiskAlert: "Risque de Rupture Imminente",
  },
  integrations: {
    title: "Hub d'Intégrations & Connecteurs",
    subtitle: "Synchronisez et unifiez l'ensemble de vos flux en temps réel",
    categoryAll: "Tous les connecteurs",
    categoryEcommerce: "E-commerce",
    categoryMarketing: "Marketing",
    categoryCrm: "CRM",
    categoryAccounting: "Comptabilité",
    categoryData: "Bases de données",
    categoryAutomation: "Automatisation",
    syncNow: "Synchroniser maintenant",
    syncing: "Synchronisation...",
    lastSynced: "Dernière synchro",
    recordsCount: "enregistrements",
    statusConnected: "Connecté",
    statusSyncing: "En cours",
    statusNeedsAttention: "Attention requise",
    statusDisconnected: "Déconnecté",
    drawerTitle: "Configuration & Synchronisation Manuelle",
    drawerLogsTitle: "Journal d'audit de synchronisation",
    noLogs: "Aucune synchronisation récente enregistrée.",
  },
};

const enApp: AppTranslations = {
  brand: {
    name: "AVENQO",
    tagline: "AI FOR A SMARTER TOMORROW",
  },
  navigation: {
    dashboard: "Dashboard",
    retailAi: "Retail AI",
    crmAi: "CRM AI",
    accountingAi: "Accounting AI",
    marketingAi: "Marketing AI",
    voiceAi: "Voice AI",
    ocrAi: "OCR AI",
    chatbotsAi: "AI Chatbots",
    automations: "Automations",
    agentsAi: "AI Agents",
    integrations: "Integrations",
    dataHub: "Data & Cleaning",
    settings: "Settings",
    support: "Support & SLA",
    team: "Team & Roles",
    billing: "Billing & Plans",
  },
  shell: {
    searchPlaceholder: "Search or execute command (Ctrl+K)...",
    commandPaletteShortcut: "Ctrl+K",
    activeTenant: "Active Organization",
    switchTenant: "Switch organization",
    notifications: "Notifications",
    noNotifications: "No unread notifications",
    allNotificationsRead: "All notifications reviewed",
    themeToggle: "Toggle theme",
    copilotButton: "Avenqo Copilot",
    aiCredits: "AI Credits",
    aiCreditsUsed: "used this cycle",
    upgradePlan: "Upgrade quota",
    profile: "Profile & Security",
    signOut: "Sign out",
    company: "Company",
    role: "Role",
    collapseSidebar: "Collapse sidebar",
    expandSidebar: "Expand sidebar",
  },
  commandPalette: {
    title: "Command Palette",
    placeholder: "Type a command, page name or quick action...",
    pagesGroup: "Modules & Views",
    actionsGroup: "Quick Actions",
    integrationsGroup: "Connectors & Sources",
    noResults: "No results found for your query.",
    navigateHint: "to navigate",
    selectHint: "to select",
    closeHint: "to exit",
    actionSync: "Trigger manual data synchronization",
    actionCleanData: "Run AI data cleaning pipeline",
    actionGenerateReport: "Export executive report as PDF",
    actionAskCopilot: "Query Avenqo Copilot",
  },
  copilot: {
    title: "Avenqo Copilot",
    subtitle: "Contextual Operational Intelligence",
    statusActive: "Online & grounded on live business records",
    statusThinking: "Reasoning over multi-source feeds...",
    contextBadge: "Active context",
    quickPills: {
      analyzeSales: "Analyze sales performance",
      forecastDemand: "Forecast demand",
      detectAnomalies: "Detect anomalies",
      generateReport: "Generate report",
    },
    inputPlaceholder: "Ask anything regarding your revenue, stock, or margins...",
    sendButton: "Send",
    confidenceLabel: "Statistical confidence score",
    groundedBadge: "Grounded on normalized ledger",
    disclaimer: "AI insights rely on consolidated actual records. Always verify before making compliance commitments.",
    emptyPrompt: "Select a quick prompt or type a question to get instant intelligence from your real business data.",
    errorPrompt: "Unable to reach Copilot agent. Please check your network connection or API credits.",
    retry: "Retry query",
  },
  dashboard: {
    greetingMorning: "Good morning",
    greetingAfternoon: "Good afternoon",
    greetingEvening: "Good evening",
    dateRange7d: "Last 7 days",
    dateRange30d: "Last 30 days",
    dateRangeQuarter: "This quarter",
    dateRangeCustom: "Custom range",
    revenue: "Gross Revenue",
    orders: "Total Orders",
    customers: "Active Customers",
    aov: "Average Order Value (AOV)",
    conversionRate: "Conversion Rate",
    trendTitle: "Combined Trend: Revenue & Orders",
    trendSubtitle: "Multi-source consolidated timeline",
    categorySplitTitle: "Sales breakdown by category",
    regionalSalesTitle: "Regional sales distribution",
    aiInsightTitle: "Avenqo AI Insight",
    aiInsightEmpty: "No data stream available to produce insights.",
    aiInsightInsufficient: "Insufficient data for analysis. Please connect an e-commerce integration.",
    aiInsightConfidence: "AI Confidence Level",
    recommendationAction: "Apply recommendation",
  },
  retail: {
    overview: "Overview",
    sales: "Sales",
    products: "Products",
    customers: "Customers",
    inventory: "Inventory",
    forecasts: "Forecasts",
    anomalies: "Anomalies",
    recommendations: "Recommendations",
    rawVsCleaned: "Comparative View: Raw Data vs AI-Cleaned Data",
    rawTitle: "Raw Stream (Multi-Format)",
    cleanedTitle: "AI Normalized Ledger (AVENQO Engine)",
    qualityScore: "Data Quality Score (DQS)",
    completeness: "Completeness",
    consistency: "Consistency",
    validity: "Validity",
    freshness: "Freshness",
    demandForecastTitle: "Demand Forecast & Replenishment Planning",
    forecastDisclaimer: "Predictive model based on historical sales velocity. Does not constitute a contractual sales guarantee.",
    overstockAlert: "Excess Inventory Detected",
    stockoutRiskAlert: "Imminent Stockout Risk",
  },
  integrations: {
    title: "Integrations Hub & Connectors",
    subtitle: "Sync, normalize and orchestrate all data feeds in real time",
    categoryAll: "All connectors",
    categoryEcommerce: "E-commerce",
    categoryMarketing: "Marketing",
    categoryCrm: "CRM",
    categoryAccounting: "Accounting",
    categoryData: "Databases",
    categoryAutomation: "Automation",
    syncNow: "Sync now",
    syncing: "Syncing...",
    lastSynced: "Last synced",
    recordsCount: "records",
    statusConnected: "Connected",
    statusSyncing: "Syncing",
    statusNeedsAttention: "Needs Attention",
    statusDisconnected: "Disconnected",
    drawerTitle: "Manual Sync & Connector Settings",
    drawerLogsTitle: "Sync Audit Log",
    noLogs: "No recent synchronization entries recorded.",
  },
};

export function getAppTranslations(locale: LocaleCode | string): AppTranslations {
  if (locale === "fr" || locale === "fr-FR") {
    return frApp;
  }
  return enApp;
}

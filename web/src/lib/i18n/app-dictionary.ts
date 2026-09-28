import type { LocaleCode } from "./types";
import { APP_LOCALE_WORDS } from "./app-locale-overrides";
import { getTranslations } from "./dictionary";
import { getApplicationCatalog } from "./generated-app-catalogs";

export type AppTranslations = {
  common: {
    close: string;
    insufficientData: string;
  };
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
    connections: string;
    admin: string;
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
    stripeNotLinked: string;
    collapseSidebar: string;
    expandSidebar: string;
    mainOperations: string;
    artificialIntelligence: string;
    platformData: string;
    workspace: string;
    quickSearch: string;
    markAllRead: string;
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
    activeSourcesLabel: string;
    noActiveSources: string;
    disclaimer: string;
    emptyPrompt: string;
    errorPrompt: string;
    retry: string;
  };
  dashboard: {
    greetingMorning: string;
    greetingAfternoon: string;
    greetingEvening: string;
    dateRangeAll: string;
    dateRange7d: string;
    dateRange30d: string;
    dateRangeQuarter: string;
    dateRangeCustom: string;
    noTransactionsForPeriod: string;
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
    aiInsightNoPriority: string;
    aiInsightConfidence: string;
    recommendationAction: string;
  };
  retail: {
    overview: string;
    sales: string;
    products: string;
    customers: string;
    noData: string;
    email: string;
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
    activeSources: string;
    activeSourcesDescription: string;
    uploadedRetailSource: string;
    sourceEnabled: string;
    sourceDisabled: string;
    sourceOn: string;
    sourceOff: string;
    selectSource: string;
    currentRetailSource: string;
    noUploadedRetailSources: string;
    drawerTitle: string;
    drawerLogsTitle: string;
    noLogs: string;
    googleCalendar: string;
    googleCalendarDescription: string;
    googleCalendarConnect: string;
    googleCalendarManage: string;
    googleCalendarDisconnect: string;
    googleCalendarConnected: string;
    googleCalendarDisconnected: string;
    googleCalendarConnecting: string;
  };
  crm: {
    title: string;
    headerTitle: string;
    headerSubtitle: string;
    newAppointment: string;
    searchPlaceholder: string;
    header: {
      newAppointment: string;
    };
    tabs: {
      overview: string;
      clients: string;
      appointments: string;
      pipelines: string;
      automations: string;
      campaigns: string;
      reports: string;
      calendarSync: string;
      connections: string;
    };
    kpis: {
      activeClients: string;
      appointmentsThisMonth: string;
      attendanceRate: string;
      revenueGenerated: string;
    };
    calendarModes: {
      day: string;
      week: string;
      month: string;
      agenda: string;
      kanban: string;
      list: string;
    };
    calendar: {
      today: string;
      day: string;
      week: string;
      month: string;
      agenda: string;
      kanban: string;
      list: string;
      connected: string;
      disconnected: string;
      connectGoogle: string;
      disconnect: string;
      allServices: string;
      allEmployees: string;
      allStatuses: string;
      filterPlaceholder: string;
      loadingAppointments: string;
      noAppointments: string;
      previous: string;
      next: string;
    };
    appointmentStatuses: {
      confirmed: string;
      pending: string;
      completed: string;
      cancelled: string;
      noShow: string;
    };
    status: {
      confirmed: string;
      pending: string;
      completed: string;
      cancelled: string;
      noShow: string;
    };
    filters: {
      service: string;
      employee: string;
      status: string;
    };
    modal: {
      newAppointmentTitle: string;
      editAppointmentTitle: string;
      subtitle: string;
      dateRequired: string;
      clientRequired: string;
    };
    clients: {
      client: string;
    };
    actions: {
      modify: string;
      reschedule: string;
      cancel: string;
      deletePermanent: string;
      confirmCancel: string;
      confirmDelete: string;
      cancelSuccess: string;
      deleteSuccess: string;
      mutationError: string;
      markCompleted: string;
      save: string;
      close: string;
      addNote: string;
      connectGoogle: string;
      disconnect: string;
      syncNow: string;
    };
  };
};

const frApp: AppTranslations = {
  common: {
    close: "Fermer",
    insufficientData: "Données insuffisantes pour afficher cette analyse.",
  },
  brand: {
    name: "AVENQO",
    tagline: "L'IA POUR UN AVENIR PLUS INTELLIGENT",
  },
  navigation: {
    dashboard: "Tableau de bord",
    retailAi: "Retail IA",
    crmAi: "CRM IA",
    accountingAi: "Comptabilité IA",
    marketingAi: "Marketing IA",
    voiceAi: "Voice IA",
    ocrAi: "OCR IA",
    chatbotsAi: "Chatbots IA",
    automations: "Automations",
    agentsAi: "Agents IA",
    integrations: "Intégrations",
    dataHub: "Données & Nettoyage",
    settings: "Paramètres",
    support: "Support & SLA",
    team: "Équipe & Accès",
    billing: "Facturation & Plans",
    connections: "Connexions",
    admin: "Administration",
  },
  shell: {
    searchPlaceholder: "Rechercher un client, un rendez-vous, une note...",
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
    stripeNotLinked: "Abonnement Stripe non lié",
    collapseSidebar: "Réduire le menu",
    expandSidebar: "Agrandir le menu",
    mainOperations: "Opérations principales",
    artificialIntelligence: "Intelligence artificielle",
    platformData: "Plateforme et données",
    workspace: "Mon espace",
    quickSearch: "Recherche rapide",
    markAllRead: "Tout marquer comme lu",
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
    activeSourcesLabel: "Sources actives",
    noActiveSources: "Aucune source activée",
    disclaimer: "Les suggestions IA reposent sur les données réelles consolidées. Vérifiez avant toute décision réglementaire.",
    emptyPrompt: "Sélectionnez une action rapide ou saisissez une question pour obtenir une analyse instantanée de vos flux.",
    errorPrompt: "Impossible de contacter l'agent Copilot. Veuillez vérifier votre connexion ou vos crédits d'API.",
    retry: "Réessayer l'analyse",
  },
  dashboard: {
    greetingMorning: "Bonjour",
    greetingAfternoon: "Bon après-midi",
    greetingEvening: "Bonsoir",
    dateRangeAll: "Tout",
    dateRange7d: "7 derniers jours",
    dateRange30d: "30 derniers jours",
    dateRangeQuarter: "Ce trimestre",
    dateRangeCustom: "Plage personnalisée",
    noTransactionsForPeriod: "Aucune transaction dans la période sélectionnée : {period}.",
    revenue: "Chiffre d'affaires",
    orders: "Commandes",
    customers: "Clients actifs",
    aov: "Panier moyen (AOV)",
    conversionRate: "Taux de conversion",
    trendTitle: "Tendance Combinée : Revenus & Commandes",
    trendSubtitle: "Évolution temporelle consolidée multi-sources",
    categorySplitTitle: "Répartition des ventes par catégorie",
    regionalSalesTitle: "Performance des ventes régionales",
    aiInsightTitle: "Insight IA Avenqo",
    aiInsightEmpty: "Aucun flux de données disponible pour générer une analyse.",
    aiInsightInsufficient: "Données insuffisantes. Activez un jeu de données ou une source connectée.",
    aiInsightNoPriority: "Aucune priorité nécessitant votre attention n’a été détectée pour cette période.",
    aiInsightConfidence: "Niveau de confiance IA",
    recommendationAction: "Appliquer la recommandation",
  },
  retail: {
    overview: "Vue d'ensemble",
    sales: "Ventes",
    products: "Produits",
    customers: "Clients",
    noData: "Aucune donnée connectée",
    email: "E-mail",
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
    activeSources: "Sources de données actives",
    activeSourcesDescription: "Fichiers importés et boutiques qui alimentent Retail. Désactiver une source ne la supprime pas.",
    uploadedRetailSource: "Fichier importé",
    sourceEnabled: "Activée",
    sourceDisabled: "Désactivée",
    sourceOn: "Connecté · ON",
    sourceOff: "Connecté · OFF",
    selectSource: "Utiliser cette source",
    currentRetailSource: "Source courante",
    noUploadedRetailSources: "Aucun fichier de vente prêt n’est connecté à Retail.",
    drawerTitle: "Configuration & Synchronisation Manuelle",
    drawerLogsTitle: "Journal d'audit de synchronisation",
    noLogs: "Aucune synchronisation récente enregistrée.",
    googleCalendar: "Google Calendar",
    googleCalendarDescription: "Synchronisez vos rendez-vous Avenqo avec Google Calendar en temps réel.",
    googleCalendarConnect: "Connecter",
    googleCalendarManage: "Gérer",
    googleCalendarDisconnect: "Déconnecter",
    googleCalendarConnected: "Connecté",
    googleCalendarDisconnected: "Déconnecté",
    googleCalendarConnecting: "Connexion...",
  },
  crm: {
    title: "CRM IA & Planification Intelligente",
    headerTitle: "CRM IA & Relations Clients",
    headerSubtitle: "Planification intelligente, gestion des clients 360° et synchronisation multi-calendriers",
    newAppointment: "Nouveau rendez-vous",
    searchPlaceholder: "Rechercher un client, un rendez-vous, une note...",
    header: {
      newAppointment: "Nouveau rendez-vous",
    },
    tabs: {
      overview: "Aperçu",
      clients: "Clients",
      appointments: "Rendez-vous",
      pipelines: "Pipelines & Deals",
      automations: "Automatisations",
      campaigns: "Campagnes",
      reports: "Rapports",
      calendarSync: "Connexions calendrier",
      connections: "Connexions calendrier",
    },
    kpis: {
      activeClients: "Clients Actifs",
      appointmentsThisMonth: "Rendez-vous ce mois",
      attendanceRate: "Taux de présence",
      revenueGenerated: "Chiffre d'affaires généré",
    },
    calendarModes: {
      day: "Jour",
      week: "Semaine",
      month: "Mois",
      agenda: "Agenda",
      kanban: "Kanban",
      list: "Liste",
    },
    calendar: {
      today: "Aujourd'hui",
      day: "Jour",
      week: "Semaine",
      month: "Mois",
      agenda: "Agenda",
      kanban: "Kanban",
      list: "Liste",
      connected: "Connecté",
      disconnected: "Non connecté",
      connectGoogle: "Connecter Google Calendar",
      disconnect: "Déconnecter",
      allServices: "Tous les services",
      allEmployees: "Tous les employés",
      allStatuses: "Tous les statuts",
      filterPlaceholder: "Filtrer client, service, titre...",
      loadingAppointments: "Chargement des rendez-vous...",
      noAppointments: "Aucun rendez-vous",
      previous: "Précédent",
      next: "Suivant",
    },
    appointmentStatuses: {
      confirmed: "Confirmé",
      pending: "En attente",
      completed: "Terminé",
      cancelled: "Annulé",
      noShow: "Absent (No-show)",
    },
    status: {
      confirmed: "Confirmé",
      pending: "En attente",
      completed: "Terminé",
      cancelled: "Annulé",
      noShow: "Absent (No-show)",
    },
    filters: {
      service: "Service / Prestation",
      employee: "Employé / Collaborateur",
      status: "Statut du rendez-vous",
    },
    modal: {
      newAppointmentTitle: "Nouveau rendez-vous",
      editAppointmentTitle: "Modifier le rendez-vous",
      subtitle: "Planification intelligente & synchronisation Google Calendar",
      dateRequired: "Date et heure requises.",
      clientRequired: "Veuillez sélectionner un client.",
    },
    clients: {
      client: "Client",
    },
    actions: {
      modify: "Modifier",
      reschedule: "Déplacer / Reporter",
      cancel: "Annuler le rendez-vous",
      deletePermanent: "Supprimer définitivement",
      confirmCancel: "Voulez-vous vraiment annuler ce rendez-vous ?",
      confirmDelete: "Voulez-vous vraiment supprimer définitivement ce rendez-vous ? Cette action est irréversible.",
      cancelSuccess: "Rendez-vous annulé.",
      deleteSuccess: "Rendez-vous supprimé définitivement.",
      mutationError: "L'opération n'a pas pu être terminée.",
      markCompleted: "Marquer comme terminé",
      save: "Enregistrer",
      close: "Fermer",
      addNote: "Ajouter une note",
      connectGoogle: "Connecter Google Calendar",
      disconnect: "Déconnecter",
      syncNow: "Synchroniser maintenant",
    },
  },
};

const enApp: AppTranslations = {
  common: {
    close: "Close",
    insufficientData: "This analysis is not available with your current data.",
  },
  brand: {
    name: "AVENQO",
    tagline: "AI FOR A SMARTER FUTURE",
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
    connections: "Connections",
    admin: "Administration",
  },
  shell: {
    searchPlaceholder: "Search client, appointment, note...",
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
    stripeNotLinked: "Stripe subscription not linked",
    collapseSidebar: "Collapse sidebar",
    expandSidebar: "Expand sidebar",
    mainOperations: "Core operations",
    artificialIntelligence: "Artificial intelligence",
    platformData: "Platform and data",
    workspace: "My workspace",
    quickSearch: "Quick search",
    markAllRead: "Mark all as read",
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
    activeSourcesLabel: "Active sources",
    noActiveSources: "No enabled sources",
    disclaimer: "AI insights rely on consolidated actual records. Always verify before making compliance commitments.",
    emptyPrompt: "Select a quick prompt or type a question to get instant intelligence from your real business data.",
    errorPrompt: "Unable to reach Copilot agent. Please check your network connection or API credits.",
    retry: "Retry query",
  },
  dashboard: {
    greetingMorning: "Good morning",
    greetingAfternoon: "Good afternoon",
    greetingEvening: "Good evening",
    dateRangeAll: "All",
    dateRange7d: "Last 7 days",
    dateRange30d: "Last 30 days",
    dateRangeQuarter: "This quarter",
    dateRangeCustom: "Custom range",
    noTransactionsForPeriod: "No transactions in the selected period: {period}.",
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
    aiInsightInsufficient: "Insufficient data. Enable a dataset or connected source to continue.",
    aiInsightNoPriority: "No priority requiring your attention was detected for this period.",
    aiInsightConfidence: "AI Confidence Level",
    recommendationAction: "Apply recommendation",
  },
  retail: {
    overview: "Overview",
    sales: "Sales",
    products: "Products",
    customers: "Customers",
    noData: "No data connected yet",
    email: "Email",
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
    activeSources: "Active data sources",
    activeSourcesDescription: "Uploaded files and stores powering Retail. Turning a source off does not delete it.",
    uploadedRetailSource: "Uploaded file",
    sourceEnabled: "Enabled",
    sourceDisabled: "Disabled",
    sourceOn: "Connected · ON",
    sourceOff: "Connected · OFF",
    selectSource: "Use this source",
    currentRetailSource: "Current source",
    noUploadedRetailSources: "No ready sales files are connected to Retail.",
    drawerTitle: "Manual Sync & Connector Settings",
    drawerLogsTitle: "Sync Audit Log",
    noLogs: "No recent synchronization entries recorded.",
    googleCalendar: "Google Calendar",
    googleCalendarDescription: "Synchronize your Avenqo appointments with Google Calendar in real time.",
    googleCalendarConnect: "Connect",
    googleCalendarManage: "Manage",
    googleCalendarDisconnect: "Disconnect",
    googleCalendarConnected: "Connected",
    googleCalendarDisconnected: "Disconnected",
    googleCalendarConnecting: "Connecting...",
  },
  crm: {
    title: "CRM AI & Intelligent Scheduling",
    headerTitle: "CRM AI & Customer Operations",
    headerSubtitle: "Intelligent scheduling, 360° client profiles and multi-calendar synchronization",
    newAppointment: "New Appointment",
    searchPlaceholder: "Search client, appointment, note...",
    header: {
      newAppointment: "New Appointment",
    },
    tabs: {
      overview: "Overview",
      clients: "Clients",
      appointments: "Appointments",
      pipelines: "Pipelines & Deals",
      automations: "Automations",
      campaigns: "Campaigns",
      reports: "Reports",
      calendarSync: "Calendar Connections",
      connections: "Calendar Connections",
    },
    kpis: {
      activeClients: "Active Clients",
      appointmentsThisMonth: "Appointments this month",
      attendanceRate: "Attendance Rate",
      revenueGenerated: "Revenue Generated",
    },
    calendarModes: {
      day: "Day",
      week: "Week",
      month: "Month",
      agenda: "Agenda",
      kanban: "Kanban",
      list: "List",
    },
    calendar: {
      today: "Today",
      day: "Day",
      week: "Week",
      month: "Month",
      agenda: "Agenda",
      kanban: "Kanban",
      list: "List",
      connected: "Connected",
      disconnected: "Disconnected",
      connectGoogle: "Connect Google Calendar",
      disconnect: "Disconnect",
      allServices: "All services",
      allEmployees: "All staff",
      allStatuses: "All statuses",
      filterPlaceholder: "Filter client, service, title...",
      loadingAppointments: "Loading appointments...",
      noAppointments: "No appointments",
      previous: "Previous",
      next: "Next",
    },
    appointmentStatuses: {
      confirmed: "Confirmed",
      pending: "Pending",
      completed: "Completed",
      cancelled: "Cancelled",
      noShow: "No-show",
    },
    status: {
      confirmed: "Confirmed",
      pending: "Pending",
      completed: "Completed",
      cancelled: "Cancelled",
      noShow: "No-show",
    },
    filters: {
      service: "Service",
      employee: "Employee",
      status: "Appointment Status",
    },
    modal: {
      newAppointmentTitle: "New Appointment",
      editAppointmentTitle: "Edit Appointment",
      subtitle: "Intelligent scheduling & Google Calendar synchronization",
      dateRequired: "Date and time are required.",
      clientRequired: "Please select a client.",
    },
    clients: {
      client: "Client",
    },
    actions: {
      modify: "Modify",
      reschedule: "Reschedule",
      cancel: "Cancel Appointment",
      deletePermanent: "Delete permanently",
      confirmCancel: "Are you sure you want to cancel this appointment?",
      confirmDelete: "Are you sure you want to permanently delete this appointment? This action cannot be undone.",
      cancelSuccess: "Appointment cancelled.",
      deleteSuccess: "Appointment permanently deleted.",
      mutationError: "The operation could not be completed.",
      markCompleted: "Mark as Completed",
      save: "Save",
      close: "Close",
      addNote: "Add note",
      connectGoogle: "Connect Google Calendar",
      disconnect: "Disconnect",
      syncNow: "Sync now",
    },
  },
};

const esApp: AppTranslations = {
  ...enApp,
  navigation: {
    ...enApp.navigation,
    dashboard: "Panel",
    crmAi: "CRM IA",
    accountingAi: "Contabilidad IA",
    integrations: "Integraciones",
    settings: "Configuración",
  },
  crm: {
    ...enApp.crm,
    title: "CRM IA y agenda inteligente",
    headerTitle: "CRM IA y operaciones de clientes",
    headerSubtitle: "Agenda inteligente, perfiles 360 y sincronización de calendarios",
    newAppointment: "Nueva cita",
    tabs: {
      ...enApp.crm.tabs,
      overview: "Resumen",
      clients: "Clientes",
      appointments: "Citas",
      pipelines: "Embudo y oportunidades",
      automations: "Automatizaciones",
      campaigns: "Campañas",
      reports: "Informes",
      connections: "Conexiones de calendario",
    },
    kpis: {
      ...enApp.crm.kpis,
      activeClients: "Clientes activos",
      appointmentsThisMonth: "Citas este mes",
      attendanceRate: "Tasa de asistencia",
      revenueGenerated: "Ingresos generados",
    },
    calendar: {
      ...enApp.crm.calendar,
      today: "Hoy",
      day: "Día",
      week: "Semana",
      month: "Mes",
      agenda: "Agenda",
      list: "Lista",
      connected: "Conectado",
      disconnected: "Desconectado",
      connectGoogle: "Conectar Google Calendar",
      disconnect: "Desconectar",
      allServices: "Todos los servicios",
      allEmployees: "Todos los profesionales",
      allStatuses: "Todos los estados",
      filterPlaceholder: "Filtrar cliente, servicio o título...",
      loadingAppointments: "Cargando citas...",
      noAppointments: "Sin citas",
      previous: "Anterior",
      next: "Siguiente",
    },
    appointmentStatuses: {
      confirmed: "Confirmada",
      pending: "Pendiente",
      completed: "Completada",
      cancelled: "Cancelada",
      noShow: "No presentada",
    },
    status: {
      confirmed: "Confirmada",
      pending: "Pendiente",
      completed: "Completada",
      cancelled: "Cancelada",
      noShow: "No presentada",
    },
    filters: {
      service: "Servicio",
      employee: "Profesional",
      status: "Estado de la cita",
    },
    modal: {
      ...enApp.crm.modal,
      newAppointmentTitle: "Nueva cita",
      editAppointmentTitle: "Editar cita",
      subtitle: "Agenda inteligente y sincronización con Google Calendar",
      dateRequired: "La fecha y la hora son obligatorias.",
      clientRequired: "Selecciona un cliente.",
    },
    clients: { client: "Cliente" },
    actions: {
      ...enApp.crm.actions,
      modify: "Modificar",
      reschedule: "Reprogramar",
      cancel: "Cancelar cita",
      deletePermanent: "Eliminar definitivamente",
      confirmCancel: "¿Quieres cancelar esta cita?",
      confirmDelete: "¿Quieres eliminar definitivamente esta cita? Esta acción no se puede deshacer.",
      cancelSuccess: "Cita cancelada.",
      deleteSuccess: "Cita eliminada definitivamente.",
      mutationError: "No se pudo completar la operación.",
      markCompleted: "Marcar como completada",
      save: "Guardar",
      close: "Cerrar",
    },
  },
};

export function getAppTranslations(locale: LocaleCode | string): AppTranslations {
  const base = locale === "fr" || locale === "fr-FR"
    ? frApp
    : locale === "es"
      ? esApp
      : enApp;
  const words = APP_LOCALE_WORDS[locale as LocaleCode] ?? APP_LOCALE_WORDS.en;
  const catalog = getTranslations(locale as LocaleCode);
  const application = getApplicationCatalog(locale);
  const company = application.company;
  const dashboardHome = application.dashboardHome;
  const assistant = application.assistant;
  const connector = company.connectorHub;
  const usesWebProductTerms = ["fr", "fr-FR", "en", "es"].includes(locale);
  const retailItems = Object.fromEntries(catalog.modulesSection.items.map((item) => [item.name.toLowerCase(), item]));
  const retailItem = Object.values(retailItems).find((item) => item.name.toLowerCase().includes("retail"));
  return {
    ...base,
    common: {
      ...base.common,
      close: connector.close,
      insufficientData: company.analyticsUnavailable,
    },
    navigation: {
      ...base.navigation,
      dashboard: usesWebProductTerms ? base.navigation.dashboard : company.navOverviewLabel,
      retailAi: words.retail,
      crmAi: words.crm,
      accountingAi: words.accounting,
      integrations: words.integrations,
      settings: company.navSettingsLabel,
      support: company.navSupportLabel,
      team: company.navTeamLabel,
      billing: usesWebProductTerms ? base.navigation.billing : company.navBillingLabel,
      connections: company.navConnectionsLabel,
    },
    shell: {
      ...base.shell,
      themeToggle: company.settingsThemeLabel,
      copilotButton: assistant.avenqoAi,
      signOut: company.settingsLogout,
      company: company.settingsCompanySection,
    },
    commandPalette: {
      ...base.commandPalette,
      actionAskCopilot: dashboardHome.askAvenqoCta,
    },
    copilot: {
      ...base.copilot,
      title: assistant.avenqoAi,
      subtitle: assistant.subtitle,
      statusThinking: assistant.thinking,
      activeSourcesLabel: assistant.sourcesLabel,
      errorPrompt: assistant.requestUnavailable,
      retry: assistant.retry,
    },
    integrations: {
      ...base.integrations,
      title: connector.title,
      subtitle: connector.subtitle,
      syncNow: connector.sync,
      syncing: connector.syncing,
      lastSynced: connector.lastSync,
      recordsCount: connector.records,
      statusConnected: connector.connected,
      statusSyncing: connector.syncing,
      statusNeedsAttention: connector.error,
      statusDisconnected: connector.disconnected,
      drawerLogsTitle: connector.connection,
      noLogs: connector.neverSynced,
    },
    crm: {
      ...base.crm,
      title: `${words.crm} ${words.overview}`,
      newAppointment: words.newAppointment ?? base.crm.newAppointment,
      header: {
        ...base.crm.header,
        newAppointment: words.newAppointment ?? base.crm.header.newAppointment,
      },
      tabs: {
        ...base.crm.tabs,
        overview: words.overview,
        clients: words.clients,
        appointments: words.appointments,
      },
      kpis: {
        ...base.crm.kpis,
        activeClients: words.activeClients,
        appointmentsThisMonth: words.appointmentsThisMonth,
        attendanceRate: words.attendanceRate ?? base.crm.kpis.attendanceRate,
        revenueGenerated: words.revenueGenerated,
      },
      calendarModes: words.calendar ? {
        day: words.calendar.day,
        week: words.calendar.week,
        month: words.calendar.month,
        agenda: words.calendar.agenda,
        kanban: words.calendar.kanban,
        list: words.calendar.list,
      } : base.crm.calendarModes,
      calendar: words.calendar ? {
        ...base.crm.calendar,
        today: words.calendar.today,
        day: words.calendar.day,
        week: words.calendar.week,
        month: words.calendar.month,
        agenda: words.calendar.agenda,
        kanban: words.calendar.kanban,
        list: words.calendar.list,
        allServices: words.calendar.allServices,
        allEmployees: words.calendar.allEmployees,
        allStatuses: words.calendar.allStatuses,
        filterPlaceholder: words.calendar.searchPlaceholder,
        loadingAppointments: words.calendar.loadingAppointments,
        noAppointments: words.calendar.noAppointments,
        previous: words.calendar.previous,
        next: words.calendar.next,
      } : base.crm.calendar,
      status: {
        ...base.crm.status,
      },
      appointmentStatuses: {
        ...base.crm.appointmentStatuses,
      },
    },
    dashboard: {
      ...base.dashboard,
      dateRangeAll: dashboardHome.periodAll,
      dateRange7d: dashboardHome.period7Days,
      dateRange30d: dashboardHome.period30Days,
      dateRangeQuarter: dashboardHome.periodQuarter,
      revenue: dashboardHome.salesLabel,
      orders: dashboardHome.ordersLabel,
      customers: dashboardHome.customersLabel,
      aov: dashboardHome.avgOrderLabel,
      aiInsightTitle: dashboardHome.prioritiesTitle,
      aiInsightEmpty: dashboardHome.prioritiesEmpty,
      recommendationAction: catalog.dashboard.recommendationAction,
    },
    retail: {
      ...base.retail,
      overview: company.navOverviewLabel,
      sales: company.navSalesLabel,
      products: company.navProductsLabel,
      customers: company.navCustomersLabel,
      noData: dashboardHome.connectionsEmpty,
      email: company.employeesColumnEmail,
      recommendations: company.navRecommendationsLabel,
      forecastDisclaimer: retailItem?.description ?? base.retail.forecastDisclaimer,
    },
  };
}

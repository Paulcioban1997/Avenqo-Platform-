import { notFound } from "next/navigation";
import { ModuleDetailView } from "./module-detail-view";

const MODULES_DATA: Record<
  string,
  {
    nameFr: string;
    nameEn: string;
    taglineFr: string;
    taglineEn: string;
    descriptionFr: string;
    descriptionEn: string;
    featuresFr: string[];
    featuresEn: string[];
    metricsFr: { label: string; value: string }[];
    metricsEn: { label: string; value: string }[];
    dashboardRoute: string;
  }
> = {
  retail: {
    nameFr: "Avenqo Retail",
    nameEn: "Avenqo Retail",
    taglineFr: "Intelligence omnicanale pour le commerce et la distribution",
    taglineEn: "Omnichannel intelligence for commerce and retail",
    descriptionFr:
      "Pilotez vos ventes en temps réel, unifiez les données de vos boutiques Shopify, WooCommerce et Etsy, et laissez les algorithmes prédictifs anticiper vos ruptures de stock et votre réapprovisionnement.",
    descriptionEn:
      "Drive sales in real-time, unify data from your Shopify, WooCommerce, and Etsy stores, and let predictive intelligence forecast stockouts and replenishment schedules.",
    featuresFr: [
      "Synchronisation multi-boutiques automatique (Shopify, WooCommerce, Etsy)",
      "Prévisions de demande et alertes intelligentes de réassort",
      "Calcul des marges nettes par canal et par variante de produit",
      "Recommandations de réapprovisionnement exploitables en 1 clic",
    ],
    featuresEn: [
      "Multi-store auto-sync (Shopify, WooCommerce, Etsy)",
      "Demand forecasting & automated replenishment triggers",
      "Net margin analytics per sales channel and SKU variant",
      "Actionable replenishment recommendations in one click",
    ],
    metricsFr: [
      { label: "Réduction des ruptures", value: "-42%" },
      { label: "Gain de temps hebdomadaire", value: "8h / sem." },
      { label: "Précision des prévisions", value: "94.6%" },
    ],
    metricsEn: [
      { label: "Stockout reduction", value: "-42%" },
      { label: "Time saved per week", value: "8h / wk" },
      { label: "Forecast accuracy", value: "94.6%" },
    ],
    dashboardRoute: "/retail",
  },
  crm: {
    nameFr: "Avenqo CRM",
    nameEn: "Avenqo CRM",
    taglineFr: "Priorisation des opportunités et intelligence relationnelle",
    taglineEn: "Opportunity prioritization and customer relationship AI",
    descriptionFr:
      "Transformez chaque interaction en opportunité. Centralisez vos contacts, automatisez les relances et identifiez immédiatement les clients à fort potentiel de rétention.",
    descriptionEn:
      "Turn every interaction into revenue. Centralize customer contacts, automate follow-ups, and instantly identify accounts with high retention potential.",
    featuresFr: [
      "Scoring intelligent des prospects et opportunités",
      "Historique complet des communications et des transactions",
      "Génération assistée de propositions et suivis par IA",
      "Segmentation dynamique selon la valeur client (LTV)",
    ],
    featuresEn: [
      "AI-driven lead scoring and pipeline management",
      "Complete transaction and communication timeline",
      "AI-assisted follow-ups and custom pitch proposals",
      "Dynamic customer segmentation based on lifetime value",
    ],
    metricsFr: [
      { label: "Taux de conversion", value: "+28%" },
      { label: "Délai de réponse", value: "< 15 min" },
      { label: "Rétention client", value: "+35%" },
    ],
    metricsEn: [
      { label: "Conversion lift", value: "+28%" },
      { label: "Response latency", value: "< 15 min" },
      { label: "Customer retention", value: "+35%" },
    ],
    dashboardRoute: "/crm",
  },
  accounting: {
    nameFr: "Avenqo Accounting",
    nameEn: "Avenqo Accounting",
    taglineFr: "Préparation comptable et réconciliation automatisée",
    taglineEn: "Automated accounting prep and financial ledger reconciliation",
    descriptionFr:
      "Rapprochez automatiquement vos encaissements Stripe, vos règlements bancaires et vos factures. Générez vos écritures prêtes pour votre comptable sans ressaisie.",
    descriptionEn:
      "Automatically reconcile Stripe payouts, bank deposits, and client invoices. Generate accountant-ready ledgers with zero manual double entry.",
    featuresFr: [
      "Rapprochement automatique des flux bancaires et passerelles",
      "Détection des anomalies de TVA et conformité fiscale canadienne",
      "Exportation grand livre et balances au format comptable",
      "Suivi de trésorerie prévisionnel à 30/60/90 jours",
    ],
    featuresEn: [
      "Automated bank ledger & payment gateway reconciliation",
      "Tax anomaly detection & Canadian tax compliance checks",
      "General ledger and trial balance export in standard formats",
      "30/60/90-day predictive cash flow projection",
    ],
    metricsFr: [
      { label: "Temps de clôture mensuelle", value: "-60%" },
      { label: "Erreurs de réconciliation", value: "0" },
      { label: "Rapprochement automatisé", value: "98.5%" },
    ],
    metricsEn: [
      { label: "Month-end close time", value: "-60%" },
      { label: "Reconciliation discrepancies", value: "0" },
      { label: "Automated matching", value: "98.5%" },
    ],
    dashboardRoute: "/accounting",
  },
  documents: {
    nameFr: "Avenqo Documents & OCR",
    nameEn: "Avenqo Documents & OCR",
    taglineFr: "Extraction et structuration intelligente de documents",
    taglineEn: "Intelligent document extraction and invoice OCR",
    descriptionFr:
      "Déposez vos PDF, scans et photos de reçus. Le moteur OCR extrait immédiatement les montants, taxes, numéros de factures et fournisseurs.",
    descriptionEn:
      "Drop your PDFs, scanned receipts, and bills. The OCR engine parses totals, line items, taxes, and supplier details in seconds.",
    featuresFr: [
      "Extraction OCR haute précision multilingue",
      "Ventilation automatique des taxes TPS / TVQ",
      "Archivage sécurisé et recherche plein texte",
      "Validation automatique avant injection comptable",
    ],
    featuresEn: [
      "High-accuracy multilingual OCR parsing",
      "Automatic breakdown of Canadian sales taxes (GST/QST)",
      "Secure encrypted storage & full-text search",
      "One-click audit verification before accounting entry",
    ],
    metricsFr: [
      { label: "Temps de saisie", value: "-85%" },
      { label: "Précision de lecture", value: "99.1%" },
      { label: "Traitement par document", value: "< 3s" },
    ],
    metricsEn: [
      { label: "Data entry time", value: "-85%" },
      { label: "Extraction accuracy", value: "99.1%" },
      { label: "Processing speed", value: "< 3s" },
    ],
    dashboardRoute: "/ocr",
  },
  analytics: {
    nameFr: "Avenqo Analytics",
    nameEn: "Avenqo Analytics",
    taglineFr: "Tableaux de bord stratégiques et décisions prédictives",
    taglineEn: "Strategic business dashboards and predictive insights",
    descriptionFr:
      "Visualisez la performance globale de votre entreprise en un coup d'œil. Croisez vos ventes, vos dépenses et vos prévisions dans une interface unifiée.",
    descriptionEn:
      "Monitor corporate performance at a glance. Correlate revenues, operational costs, and growth projections in a single executive cockpit.",
    featuresFr: [
      "Indicateurs clés de performance (KPI) en temps réel",
      "Alertes proactives en cas de déviation anormale",
      "Analyses de rentabilité par gamme et par client",
      "Rapports exécutifs exportables en PDF",
    ],
    featuresEn: [
      "Real-time corporate KPI executive cockpit",
      "Proactive alerts for anomalous financial shifts",
      "Granular profitability analysis per business unit",
      "One-click exportable executive PDF briefings",
    ],
    metricsFr: [
      { label: "Visibilité décisionnelle", value: "100%" },
      { label: "Temps de reporting", value: "-75%" },
      { label: "Alertes anticipées", value: "24/7" },
    ],
    metricsEn: [
      { label: "Decision visibility", value: "100%" },
      { label: "Reporting overhead", value: "-75%" },
      { label: "Proactive alerting", value: "24/7" },
    ],
    dashboardRoute: "/dashboard",
  },
  marketing: {
    nameFr: "Avenqo Marketing",
    nameEn: "Avenqo Marketing",
    taglineFr: "Orchestration de campagnes et rétention ciblée",
    taglineEn: "Campaign orchestration and hyper-targeted retention",
    descriptionFr:
      "Créez des campagnes omnicanales ciblées basées sur le comportement d'achat réel de vos clients pour maximiser le retour sur investissement.",
    descriptionEn:
      "Launch personalized campaigns informed by purchase behavior to increase repeat sales and maximize marketing ROI.",
    featuresFr: [
      "Segmentation avancée basée sur l'historique d'achat",
      "Déclencheurs d'emails et SMS automatiques",
      "Attribution précise du chiffre d'affaires généré",
      "Recommandations de contenu générées par IA",
    ],
    featuresEn: [
      "Behavioral segmentation based on transaction history",
      "Automated post-purchase triggers via email & SMS",
      "Accurate multi-touch revenue attribution",
      "AI-crafted marketing copy and product suggestions",
    ],
    metricsFr: [
      { label: "Re-commandes clients", value: "+31%" },
      { label: "Taux d'ouverture", value: "48%" },
      { label: "ROAS mesurable", value: "4.8x" },
    ],
    metricsEn: [
      { label: "Repeat purchases", value: "+31%" },
      { label: "Open rates", value: "48%" },
      { label: "Measured ROAS", value: "4.8x" },
    ],
    dashboardRoute: "/marketing",
  },
  voice: {
    nameFr: "Avenqo Voice",
    nameEn: "Avenqo Voice",
    taglineFr: "Agents vocaux interactifs et transcription intelligente",
    taglineEn: "Interactive voice agents and intelligent call logging",
    descriptionFr:
      "Automatisez les prises de commandes, confirmations et suivis téléphoniques avec des voix naturelles connectées directement à votre CRM.",
    descriptionEn:
      "Automate phone orders, appointment confirmations, and inquiries with natural conversational voice bots connected to your CRM.",
    featuresFr: [
      "Agents vocaux conversationnels à faible latence",
      "Transcription et résumé automatique des appels",
      "Mise à jour instantanée du dossier client après chaque appel",
      "Bilingue français / anglais natif québécois et international",
    ],
    featuresEn: [
      "Low-latency conversational voice agent pipelines",
      "Automatic audio transcription and key takeaway summaries",
      "Instant CRM customer record updates post-call",
      "Native bilingual French and English voice synthesis",
    ],
    metricsFr: [
      { label: "Appels manqués", value: "0" },
      { label: "Satisfaction client", value: "96%" },
      { label: "Disponibilité", value: "24/7" },
    ],
    metricsEn: [
      { label: "Missed incoming calls", value: "0" },
      { label: "Caller CSAT", value: "96%" },
      { label: "Agent availability", value: "24/7" },
    ],
    dashboardRoute: "/voice",
  },
  workflow: {
    nameFr: "Avenqo Workflow",
    nameEn: "Avenqo Workflow",
    taglineFr: "Automatisation de processus métier sans code",
    taglineEn: "No-code business process automation and routing",
    descriptionFr:
      "Connectez vos départements : dès qu'une commande ou un devis arrive, Avenqo déclenche automatiquement les tâches appropriées.",
    descriptionEn:
      "Bridge your departmental workflows: from orders to fulfillment and invoicing, trigger the next step automatically without manual handoffs.",
    featuresFr: [
      "Déclencheurs multi-sources (webhooks, email, changements d'état)",
      "Règles conditionnelles et validations hiérarchiques",
      "Audit trail complet et traçabilité des opérations",
      "Bibliothèque de flux prêts à l'emploi",
    ],
    featuresEn: [
      "Multi-source triggers (webhooks, state changes, emails)",
      "Conditional business rules and role approvals",
      "Comprehensive compliance audit trails",
      "Pre-built automation blueprints for SMBs",
    ],
    metricsFr: [
      { label: "Tâches manuelles", value: "-70%" },
      { label: "Temps d'exécution", value: "< 1s" },
      { label: "Fiabilité des flux", value: "99.9%" },
    ],
    metricsEn: [
      { label: "Manual work reduction", value: "-70%" },
      { label: "Execution speed", value: "< 1s" },
      { label: "Workflow uptime", value: "99.9%" },
    ],
    dashboardRoute: "/automations",
  },
  media: {
    nameFr: "Avenqo Media",
    nameEn: "Avenqo Media",
    taglineFr: "Génération et organisation de contenus marketing visuels",
    taglineEn: "AI visual asset generation and media asset management",
    descriptionFr:
      "Centralisez et produisez vos visuels de produits, bannières et fiches techniques grâce aux modèles génératifs haute fidélité.",
    descriptionEn:
      "Centralize and generate catalog visuals, banners, and marketing photography using high-fidelity generative pipelines.",
    featuresFr: [
      "Détourage et optimisation automatique des photos produits",
      "Génération de déclinaisons de visuels pour réseaux sociaux",
      "Organisation des actifs numériques par collection",
      "Stockage sécurisé et distribution CDN rapide",
    ],
    featuresEn: [
      "Automated product background removal and enhancement",
      "Social media banner and multi-format variations",
      "Digital asset management organized by catalog collection",
      "Encrypted cloud storage with high-speed CDN delivery",
    ],
    metricsFr: [
      { label: "Coût de production visuelle", value: "-65%" },
      { label: "Délai de mise en ligne", value: "Divisé par 3" },
      { label: "Formats prêts à l'emploi", value: "100%" },
    ],
    metricsEn: [
      { label: "Visual production cost", value: "-65%" },
      { label: "Time-to-market", value: "3x faster" },
      { label: "Channel-ready formats", value: "100%" },
    ],
    dashboardRoute: "/agents",
  },
  support: {
    nameFr: "Avenqo Support",
    nameEn: "Avenqo Support",
    taglineFr: "Gestion des tickets et résolution assistée par IA",
    taglineEn: "AI-assisted ticket management and resolution",
    descriptionFr:
      "Résolvez les requêtes de vos clients plus rapidement en suggérant des réponses vérifiées issues de votre documentation et de l'historique.",
    descriptionEn:
      "Resolve customer support tickets faster by surfacing verified resolutions from your knowledge base and historical interactions.",
    featuresFr: [
      "Boîte de réception unifiée (email, chat, formulaires)",
      "Suggestions de réponses précises et contextualisées",
      "Détection de l'urgence et du sentiment client",
      "Escalade automatique vers vos conseillers experts",
    ],
    featuresEn: [
      "Unified omnichannel inbox (email, chat, web forms)",
      "Context-aware verified resolution suggestions",
      "Sentiment and urgency classification",
      "Automated tier-2 escalation routing",
    ],
    metricsFr: [
      { label: "Délai de 1ère réponse", value: "< 2 min" },
      { label: "Résolution au 1er contact", value: "78%" },
      { label: "Satisfaction support", value: "4.9 / 5" },
    ],
    metricsEn: [
      { label: "First response time", value: "< 2 min" },
      { label: "First-contact resolution", value: "78%" },
      { label: "Support CSAT", value: "4.9 / 5" },
    ],
    dashboardRoute: "/chatbots",
  },
  chat: {
    nameFr: "Avenqo Chat",
    nameEn: "Avenqo Chat",
    taglineFr: "Assistant conversationnel autonome pour vos clients",
    taglineEn: "Autonomous 24/7 conversational assistant for clients",
    descriptionFr:
      "Offrez à vos visiteurs un assistant qui répond à leurs questions de disponibilité, suit leurs commandes et guide leurs décisions d'achat 24/7.",
    descriptionEn:
      "Deliver 24/7 client guidance: answer product questions, check shipping status, and drive conversion directly on your store or site.",
    featuresFr: [
      "Widget web personnalisable aux couleurs de votre marque",
      "Réponses alimentées par le catalogue et l'inventaire en temps réel",
      "Prise de rendez-vous et qualification de leads intégrée",
      "Passation fluide vers un agent humain en cas de besoin",
    ],
    featuresEn: [
      "Customizable brand-matched chat widget",
      "Real-time catalog and inventory-grounded answers",
      "Automated lead capture & meeting scheduling",
      "Seamless human agent handoff when requested",
    ],
    metricsFr: [
      { label: "Questions résolues sans humain", value: "82%" },
      { label: "Conversion sur le site", value: "+22%" },
      { label: "Disponibilité", value: "24/7" },
    ],
    metricsEn: [
      { label: "Autonomous answers", value: "82%" },
      { label: "On-site conversion lift", value: "+22%" },
      { label: "Availability", value: "24/7" },
    ],
    dashboardRoute: "/chatbots",
  },
};

export function generateStaticParams() {
  return Object.keys(MODULES_DATA).map((slug) => ({ slug }));
}

export default async function ModulePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const moduleData = MODULES_DATA[slug];

  if (!moduleData) {
    notFound();
  }

  return <ModuleDetailView slug={slug} data={moduleData} />;
}

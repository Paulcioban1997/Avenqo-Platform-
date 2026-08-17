/** Forme complète des chaînes traduisibles ; chaque locale doit fournir exactement ces clés. */
export type Translations = {
  common: {
    login: string;
    tryFree: string;
    watchDemo: string;
    noCreditCard: string;
    guidedSetup: string;
    isolatedData: string;
  };
  nav: {
    features: string;
    modules: string;
    pricing: string;
    enterprise: string;
    docs: string;
  };
  hero: {
    eyebrow: string;
    titleLine1: string;
    titleLine2: string;
    subtitle: string;
    trustLabel: string;
    trustSell: string;
    trustUnderstand: string;
    trustAutomate: string;
    trustDecide: string;
  };
  dashboard: {
    greeting: string;
    subtitle: string;
    askAvenqo: string;
    salesLabel: string;
    activeClientsLabel: string;
    opportunitiesLabel: string;
    opportunitiesHint: string;
    performanceLabel: string;
    performancePeriod: string;
    recommendationLabel: string;
    recommendationTitle: string;
    recommendationText: string;
    recommendationAction: string;
    quickModulesLabel: string;
    quickModules: { key: string; label: string }[];
  };
  features: {
    kicker: string;
    title: string;
    subtitle: string;
    assistantLabel: string;
    assistantTitle: string;
    assistantText: string;
    demoQuestion: string;
    demoAnswer: string;
    demoAction1: string;
    demoAction2: string;
    actionsTitle: string;
    actionsText: string;
    actionsPriority: string;
    actionsLine: string;
    securityTitle: string;
    securityText: string;
    securityItem1: string;
    securityItem2: string;
    securityItem3: string;
  };
  modulesSection: {
    kicker: string;
    title: string;
    subtitle: string;
    discover: string;
    items: { name: string; description: string }[];
  };
  steps: {
    kicker: string;
    title: string;
    ctaLabel: string;
    ctaButton: string;
    items: { number: string; title: string; text: string }[];
  };
  usecases: {
    kicker: string;
    title: string;
    subtitle: string;
    direction: { title: string; text: string };
    finance: { title: string; text: string };
    commerce: { title: string; text: string };
    operations: { title: string; text: string };
  };
  why: {
    kicker: string;
    title: string;
    items: { number: string; title: string; text: string }[];
  };
  pricing: {
    kicker: string;
    title: string;
    subtitle: string;
    popular: string;
    priceLabel: string;
    plans: { tier: string; title: string; items: string[]; action: string }[];
  };
  faq: {
    kicker: string;
    title: string;
    subtitle: string;
    contactCta: string;
    items: { question: string; answer: string }[];
  };
  finalCta: {
    label: string;
    title: string;
    tryFree: string;
    scheduleDemo: string;
  };
  footer: {
    tagline: string;
    platformTitle: string;
    platformLinks: string[];
    companyTitle: string;
    companyLinks: string[];
    resourcesTitle: string;
    resourcesLinks: string[];
    copyright: string;
  };
};

export type LocaleCode =
  | "fr"
  | "en"
  | "es"
  | "pt"
  | "ro"
  | "ar"
  | "ar-EG"
  | "zh"
  | "ja"
  | "ko"
  | "de"
  | "it"
  | "nl"
  | "pl"
  | "ru"
  | "uk"
  | "el"
  | "sv"
  | "tr"
  | "cs"
  | "he"
  | "fa"
  | "sw"
  | "am"
  | "af"
  | "ha"
  | "hi"
  | "bn"
  | "ur"
  | "ta"
  | "pa"
  | "ne"
  | "vi"
  | "th"
  | "id"
  | "ms"
  | "tl"
  | "my"
  | "km"
  | "mn"
  | "ka"
  | "hy";

export type RegionCode =
  | "americas"
  | "europe"
  | "middle-east-africa"
  | "asia-pacific";

export type LocaleDefinition = {
  code: LocaleCode;
  region: RegionCode;
  flag: string;
  nativeName: string;
  englishName: string;
  direction: "ltr" | "rtl";
};

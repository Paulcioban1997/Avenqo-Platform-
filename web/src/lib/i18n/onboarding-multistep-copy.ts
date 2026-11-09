import type { LocaleCode } from "./types";

export interface OnboardingMultistepCopy {
  steps: {
    company: string;
    modules: string;
    design: string;
    preview: string;
    contracts: string;
    subscription: string;
    checkout: string;
    complete: string;
  };
  navigation: {
    back: string;
    continue: string;
    saveAndContinue: string;
    saving: string;
    saved: string;
    stepOf: string; // "Étape {current} sur {total}"
    goToDashboard: string;
  };
  company: {
    title: string;
    subtitle: string;
    commercialName: string;
    legalName: string;
    country: string;
    region: string;
    timezone: string;
    industry: string;
    teamSize: string;
    website: string;
    description: string;
    repFirstName: string;
    repLastName: string;
    repTitle: string;
  };
  modules: {
    title: string;
    subtitle: string;
    centralAiNotice: string;
    limitNoticeBase: string;
    limitNoticePro: string;
    selectedCount: string;
  };
  design: {
    title: string;
    subtitle: string;
    candidateThemesTitle: string;
    approvedPresetsTitle: string;
    customColors: string;
    primaryColor: string;
    secondaryColor: string;
    accentColor: string;
    modeDark: string;
    modeLight: string;
    uploadLogo: string;
    uploadEmblem: string;
    resetTheme: string;
  };
  preview: {
    title: string;
    subtitle: string;
    bannerNotice: string;
    editDesign: string;
    proceedToContracts: string;
  };
  contracts: {
    title: string;
    subtitle: string;
    tos: string;
    saasAgreement: string;
    privacyDpa: string;
    nda: string;
    acceptLabel: string;
    marketingConsent: string;
  };
  subscription: {
    title: string;
    subtitle: string;
    planBase: string;
    planPro: string;
    planEnterprise: string;
    priceCad: string;
    priceUsd: string;
    monthlyCredits: string;
    modulesIncluded: string;
    contactSales: string;
  };
  checkout: {
    title: string;
    subtitle: string;
    secureStripeNotice: string;
    payWithStripe: string;
    simulatedSuccessNotice: string;
  };
  complete: {
    title: string;
    subtitle: string;
    readyNotice: string;
    recapTitle: string;
  };
}

export const ONBOARDING_MULTISTEP_COPY: Record<string, OnboardingMultistepCopy> = {
  fr: {
    steps: {
      company: "Entreprise",
      modules: "Modules",
      design: "Personnalisation",
      preview: "Aperçu",
      contracts: "Contrats",
      subscription: "Abonnement",
      checkout: "Paiement",
      complete: "Activation",
    },
    navigation: {
      back: "Précédent",
      continue: "Continuer",
      saveAndContinue: "Enregistrer & Continuer",
      saving: "Enregistrement…",
      saved: "Enregistré automatiquement",
      stepOf: "Étape {current} sur {total}",
      goToDashboard: "Accéder à mon espace Avenqo",
    },
    company: {
      title: "Bienvenue sur Avenqo — Identité de l'entreprise",
      subtitle: "Configurez l'environnement exclusif et sécurisé de votre société en quelques minutes.",
      commercialName: "Nom commercial de l'entreprise",
      legalName: "Dénomination légale officielle (si différente)",
      country: "Pays du siège social",
      region: "Province / Région",
      timezone: "Fuseau horaire d'exploitation",
      industry: "Secteur d'activité principal",
      teamSize: "Taille de l'équipe",
      website: "Site Web (facultatif)",
      description: "Description et objectifs stratégiques",
      repFirstName: "Prénom du représentant autorisé",
      repLastName: "Nom de famille",
      repTitle: "Fonction / Titre (ex. Président, Directeur)",
    },
    modules: {
      title: "Choix de vos Modules & Intelligence Métier",
      subtitle: "Sélectionnez les capacités opérationnelles actives pour votre organisation.",
      centralAiNotice: "Central AI est inclus sans frais additionnels comme socle transversal d'intelligence.",
      limitNoticeBase: "Plan Base : jusqu'à 2 modules inclus.",
      limitNoticePro: "Plan Professional : jusqu'à 5 modules inclus avec crédits étendus.",
      selectedCount: "modules sélectionnés",
    },
    design: {
      title: "Personnalisation Visuelle & Identité de Marque",
      subtitle: "Choisissez l'apparence de votre espace parmi nos styles d'exception ou ajustez vos couleurs.",
      candidateThemesTitle: "Concepts Visuels Professionnels (15 styles disponibles)",
      approvedPresetsTitle: "Styles Recommandés & Approuvés",
      customColors: "Ajustement des Couleurs & Thème",
      primaryColor: "Couleur principale",
      secondaryColor: "Couleur secondaire",
      accentColor: "Couleur d'accentuation",
      modeDark: "Mode Sombre",
      modeLight: "Mode Clair",
      uploadLogo: "Téléverser le Logo officiel (PNG, SVG, max 5 Mo)",
      uploadEmblem: "Téléverser l'Emblème / Favicon",
      resetTheme: "Réinitialiser le style",
    },
    preview: {
      title: "Aperçu Interactif de votre Futur Espace",
      subtitle: "Visualisez votre environnement sur mesure avant l'activation finale.",
      bannerNotice: "Mode Aperçu — Données de démonstration sécurisées et isolées pour votre entreprise.",
      editDesign: "Modifier l'apparence",
      proceedToContracts: "Continuer vers les contrats",
    },
    contracts: {
      title: "Accords d'Entreprise & Acceptation Légale",
      subtitle: "Consultez et acceptez les documents contractuels officiels d'Avenqo et PMC Solutions AI.",
      tos: "Conditions Générales d'Utilisation",
      saasAgreement: "Contrat d'Abonnement SaaS d'Entreprise",
      privacyDpa: "Politique de Confidentialité & Addenda Protection des Données (Loi 25 / RGPD)",
      nda: "Accord de Confidentialité Mutuel (NDA)",
      acceptLabel: "J'ai lu, compris et j'accepte les termes exécutoires de cet accord.",
      marketingConsent: "J'accepte de recevoir des communications informatives et des mises à jour produits d'Avenqo (facultatif).",
    },
    subscription: {
      title: "Choix de votre Abonnement Professionnel",
      subtitle: "Tarification transparente, sans frais cachés, adaptée à l'envergure de votre société.",
      planBase: "Base",
      planPro: "Professional",
      planEnterprise: "Enterprise Sur Devis",
      priceCad: "29,99 $ CAD / mois",
      priceUsd: "21,99 $ USD / mois",
      monthlyCredits: "crédits IA inclus chaque mois",
      modulesIncluded: "modules métier inclus",
      contactSales: "Contacter l'équipe commerciale",
    },
    checkout: {
      title: "Paiement Sécurisé de votre Abonnement",
      subtitle: "Transactions chiffrées de bout en bout et protégées par Stripe.",
      secureStripeNotice: "Vos coordonnées de paiement sont directement transmises à Stripe avec chiffrement bancaire TLS 1.3.",
      payWithStripe: "Procéder au règlement via Stripe Checkout",
      simulatedSuccessNotice: "En environnement Sandbox / Test Mode, la validation s'effectue automatiquement.",
    },
    complete: {
      title: "Félicitations ! Votre Espace Avenqo est Prêt",
      subtitle: "Votre compte entreprise a été validé, vos modules configurés et votre environnement activé.",
      readyNotice: "Toutes les étapes d'onboarding ont été complétées avec succès.",
      recapTitle: "Récapitulatif de votre organisation",
    },
  },
};

// Fallback to fr for any other language if not explicitly mapped
export function getOnboardingCopy(locale: string): OnboardingMultistepCopy {
  return ONBOARDING_MULTISTEP_COPY[locale] || ONBOARDING_MULTISTEP_COPY["fr"];
}

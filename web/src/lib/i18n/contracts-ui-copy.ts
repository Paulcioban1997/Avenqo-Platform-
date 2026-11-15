import { getApplicationCatalog } from "./generated-app-catalogs";
import { APP_COMMON_WORDS } from "./app-locale-overrides";
import type { LocaleCode } from "./types";

export type ContractsUiCopy = {
  pageTitle: string;
  pageSubtitle: string;
  refresh: string;
  tabOnboarding: string;
  tabArchive: string;
  stepLegal: string;
  stepOrder: string;
  stepReview: string;
  stepSign: string;
  stateCompleted: string;
  stateCurrent: string;
  stateBlocked: string;
  stateUpcoming: string;
  stepperLabel: string;
  step1Title: string;
  step1Description: string;
  legalName: string;
  tradeName: string;
  country: string;
  province: string;
  registration: string;
  neq: string;
  address: string;
  city: string;
  postalCode: string;
  phone: string;
  billingEmail: string;
  signatorySection: string;
  firstName: string;
  lastName: string;
  professionalEmail: string;
  jobTitle: string;
  legalCapacity: string;
  capacityOwner: string;
  capacityPresident: string;
  capacityCeo: string;
  capacityDirector: string;
  capacityOfficer: string;
  capacityRepresentative: string;
  authorityAttestation: string;
  saving: string;
  saveProfile: string;
  step2Title: string;
  step2Description: string;
  commercialBlocked: string;
  commercialVerified: string;
  mismatchTitle: string;
  mismatchSummary: string;
  planLabel: string;
  moduleCap: string;
  creditsLabel: string;
  cycleLabel: string;
  optionalTopups: string;
  freeCancellation: string;
  baseAccess: string;
  unlimited: string;
  perMonth: string;
  taxLabel: string;
  renewalLabel: string;
  editProfile: string;
  reviewAgreements: string;
  step3Title: string;
  step3Description: string;
  step4Title: string;
  step4Description: string;
  testIndicator: string;
  testDetailsSummary: string;
  testDetailsBody: string;
  incorporationSummary: string;
  incorporationBody: string;
  optionalSaas: string;
  consult: string;
  download: string;
  sign: string;
  typeNda: string;
  typeMsa: string;
  typeDpa: string;
  typeLicense: string;
  statusAwaiting: string;
  statusCustomerSigned: string;
  statusExecuted: string;
  statusPilot: string;
  lastModified: string;
  signedOn: string;
  versionLabel: string;
  archiveAgreement: string;
  archiveStatus: string;
  archiveSignatory: string;
  archiveHash: string;
  archiveDownload: string;
  signatoryPending: string;
  close: string;
  challengePrompt: string;
  requestCode: string;
  generatingCode: string;
  challengeDelivered: string;
  challengeTtl: string;
  signatoryTitle: string;
  verificationCode: string;
  authorityConsent: string;
  termsConsent: string;
  downloadDraft: string;
  signing: string;
  signAction: string;
  profileSaved: string;
  loadError: string;
  codeNotSent: string;
  codeNotDelivered: string;
  authorityRequired: string;
  consentRequired: string;
  signFailed: string;
  pilotSaved: string;
  signedPendingCountersign: string;
  manuscriptSaved: string;
  uploadFailed: string;
  validationError: string;
  governingNotice: string;
  pdfPreview: string;
  readableHeading: string;
  noContracts: string;
  dismiss: string;
  legalReviewBanner: string;
  approvalNotFinal: string;
  codeWhy: string;
  pdfLoading: string;
  pdfFailed: string;
  pdfPage: string;
  pdfOf: string;
  zoomIn: string;
  zoomOut: string;
  gateTitle: string;
  gateBody: string;
  gateContracts: string;
  gateCheckout: string;
};

const fr: ContractsUiCopy = {
  pageTitle: "Contrats et parcours juridique",
  pageSubtitle: "Profil juridique, bordereau commercial, revue des accords et signature sécurisée.",
  refresh: "Actualiser",
  tabOnboarding: "Parcours contractuel",
  tabArchive: "Registre des accords",
  stepLegal: "Profil juridique",
  stepOrder: "Bordereau commercial",
  stepReview: "Revue des accords",
  stepSign: "Signature sécurisée",
  stateCompleted: "Terminé",
  stateCurrent: "En cours",
  stateBlocked: "Bloqué",
  stateUpcoming: "À venir",
  stepperLabel: "Étapes du parcours contractuel",
  step1Title: "Identité et représentant autorisé",
  step1Description: "Ces renseignements figurent sur les accords. Ils ne remplacent pas le texte du contrat.",
  legalName: "Dénomination légale",
  tradeName: "Nom commercial, si différent",
  country: "Pays d'immatriculation",
  province: "Province, État ou région",
  registration: "Numéro d'enregistrement",
  neq: "NEQ (10 chiffres)",
  address: "Adresse du siège",
  city: "Ville",
  postalCode: "Code postal",
  phone: "Téléphone professionnel",
  billingEmail: "Courriel de facturation",
  signatorySection: "Signataire autorisé",
  firstName: "Prénom",
  lastName: "Nom de famille",
  professionalEmail: "Courriel professionnel",
  jobTitle: "Fonction",
  legalCapacity: "Qualité pour engager l'entreprise",
  capacityOwner: "Propriétaire",
  capacityPresident: "Président",
  capacityCeo: "Directeur général",
  capacityDirector: "Administrateur autorisé",
  capacityOfficer: "Dirigeant autorisé",
  capacityRepresentative: "Mandataire autorisé",
  authorityAttestation: "J'atteste avoir le pouvoir d'engager l'entreprise pour les accords Avenqo présentés ici.",
  saving: "Enregistrement…",
  saveProfile: "Enregistrer et continuer",
  step2Title: "Bordereau commercial",
  step2Description: "Le forfait, les modules et le prix affichés proviennent de l'abonnement configuré.",
  commercialBlocked: "Écart commercial",
  commercialVerified: "Concordance vérifiée",
  mismatchTitle: "Signature bloquée",
  mismatchSummary: "Un écart entre le forfait et la configuration commerciale empêche la signature. Le détail est ci-dessous.",
  planLabel: "Forfait",
  moduleCap: "Modules",
  creditsLabel: "Crédits IA mensuels",
  cycleLabel: "Cycle",
  optionalTopups: "Recharges optionnelles",
  freeCancellation: "Sans pénalité, selon le contrat",
  baseAccess: "Accès de base",
  unlimited: "Selon le contrat",
  perMonth: "par mois",
  taxLabel: "Conditions fiscales",
  renewalLabel: "Renouvellement",
  editProfile: "Modifier le profil juridique",
  reviewAgreements: "Examiner les accords",
  step3Title: "Revue des accords",
  step3Description: "Lisez chaque document avant tout consentement. Le texte affiché est celui enregistré, sans traduction juridique automatique.",
  step4Title: "Vérification et signature",
  step4Description: "La signature exige le code à usage unique, l'attestation de pouvoir et le consentement exprès.",
  testIndicator: "Essai",
  testDetailsSummary: "Statut d'essai et d'incorporation",
  testDetailsBody: "Une signature pilote d'essai n'est pas une signature juridiquement finalisée et n'est pas une contresignature. Elle ne constate pas l'incorporation de PMC Solutions AI.",
  incorporationSummary: "Statut d'incorporation du fournisseur",
  incorporationBody: "Ce dossier ne présente pas PMC Solutions AI comme une société incorporée. Aucun certificat d'incorporation n'est affirmé ici.",
  optionalSaas: "Optionnel. Non requis pour un abonnement SaaS standard.",
  consult: "Lire",
  download: "Télécharger le PDF",
  sign: "Signer électroniquement",
  typeNda: "Accord de confidentialité",
  typeMsa: "Contrat-cadre SaaS",
  typeDpa: "Accord de traitement des données",
  typeLicense: "Licence logicielle privée Avenqo",
  statusAwaiting: "En attente de signature",
  statusCustomerSigned: "Signé par le client, contresignature non enregistrée",
  statusExecuted: "Exécuté selon le dossier",
  statusPilot: "Signature pilote d'essai, non finalisée",
  lastModified: "Dernière modification",
  signedOn: "Signé le",
  versionLabel: "Version",
  archiveAgreement: "Document",
  archiveStatus: "Statut",
  archiveSignatory: "Signataire",
  archiveHash: "Empreinte SHA-256",
  archiveDownload: "Téléchargement",
  signatoryPending: "En attente",
  close: "Fermer",
  challengePrompt: "Un code à usage unique est requis avant la signature. Il n'est pas affiché ici.",
  requestCode: "Recevoir le code",
  generatingCode: "Envoi…",
  challengeDelivered: "Le code a été déposé dans la boîte d'essai de l'entreprise. Aucun courriel n'a quitté l'environnement d'essai. Ouvrez Équipe pour le lire, puis saisissez-le ici.",
  challengeTtl: "Usage unique, 15 minutes",
  signatoryTitle: "Titre du signataire",
  verificationCode: "Code à 8 chiffres",
  authorityConsent: "Je confirme avoir le pouvoir légal d'engager l'entreprise.",
  termsConsent: "J'ai lu ce document et je consens à le signer par voie électronique.",
  downloadDraft: "Télécharger le PDF",
  signing: "Envoi de la signature…",
  signAction: "Signer ce document",
  profileSaved: "Profil juridique enregistré.",
  loadError: "Le document n'a pas pu être chargé.",
  codeNotSent: "Le code n'a pas été transmis. La signature reste désactivée.",
  codeNotDelivered: "La livraison du code a échoué. Aucun code n'a été affiché.",
  authorityRequired: "Vous devez attester avoir le pouvoir d'engager l'entreprise.",
  consentRequired: "Le consentement exprès au document est obligatoire.",
  signFailed: "La signature n'a pas été enregistrée.",
  pilotSaved: "Signature pilote enregistrée pour {title}. Ce n'est pas une contresignature et PMC Solutions AI n'est pas déclaré incorporé.",
  signedPendingCountersign: "Le document {title} a été signé. La contresignature du fournisseur n'est pas enregistrée.",
  manuscriptSaved: "Le document manuscrit a été téléversé et placé en attente de vérification.",
  uploadFailed: "Le téléversement n'a pas abouti.",
  validationError: "Le profil juridique n'a pas pu être validé.",
  governingNotice: "Texte approuvé en {language}. Aucune traduction juridique de cette clause n'est substituée à l'original.",
  pdfPreview: "Aperçu PDF",
  readableHeading: "Texte du document",
  noContracts: "Aucun document n'est disponible pour cette entreprise.",
  dismiss: "Fermer l'alerte",
  legalReviewBanner: "Document en révision juridique — consultation seulement",
  approvalNotFinal: "Texte non finalisé juridiquement. Une signature pilote n'est pas un contrat exécuté.",
  codeWhy: "Ce code est envoyé à l'adresse de l'entreprise pour confirmer que la personne qui signe contrôle bien cette adresse. Il expire après 15 minutes, ne sert qu'une fois, et n'est pas demandé pour lire ou télécharger.",
  pdfLoading: "Préparation des pages…",
  pdfFailed: "Le PDF n'a pas pu être affiché. Le téléchargement utilise le même fichier.",
  pdfPage: "Page",
  pdfOf: "sur",
  zoomIn: "Agrandir",
  zoomOut: "Réduire",
  gateTitle: "L'espace n'est pas encore ouvert",
  gateBody: "Après l'inscription et le choix des modules, il faut accepter les accords SaaS requis, puis terminer le paiement d'essai Stripe. La licence de serveur privé n'est pas demandée. Le paiement n'est enregistré que lorsque Stripe le confirme.",
  gateContracts: "Lire et signer les accords",
  gateCheckout: "Paiement d'essai Stripe",
};

const en: ContractsUiCopy = {
  pageTitle: "Agreements and legal onboarding",
  pageSubtitle: "Legal profile, commercial schedule, agreement review, and secure signature.",
  refresh: "Refresh",
  tabOnboarding: "Contractual onboarding",
  tabArchive: "Agreement register",
  stepLegal: "Legal profile",
  stepOrder: "Commercial schedule",
  stepReview: "Agreement review",
  stepSign: "Secure signature",
  stateCompleted: "Completed",
  stateCurrent: "Current",
  stateBlocked: "Blocked",
  stateUpcoming: "Upcoming",
  stepperLabel: "Contract onboarding steps",
  step1Title: "Legal entity and authorized representative",
  step1Description: "These details are written into the agreements. They do not replace the contract text.",
  legalName: "Legal name",
  tradeName: "Trade name, if different",
  country: "Country of registration",
  province: "Province, state, or region",
  registration: "Registration number",
  neq: "NEQ (10 digits)",
  address: "Registered address",
  city: "City",
  postalCode: "Postal code",
  phone: "Business phone",
  billingEmail: "Billing email",
  signatorySection: "Authorized signatory",
  firstName: "First name",
  lastName: "Last name",
  professionalEmail: "Work email",
  jobTitle: "Title",
  legalCapacity: "Capacity to bind the company",
  capacityOwner: "Owner",
  capacityPresident: "President",
  capacityCeo: "Chief executive",
  capacityDirector: "Authorized director",
  capacityOfficer: "Authorized officer",
  capacityRepresentative: "Authorized representative",
  authorityAttestation: "I attest that I have authority to bind the company to the Avenqo agreements shown here.",
  saving: "Saving…",
  saveProfile: "Save and continue",
  step2Title: "Commercial schedule",
  step2Description: "The plan, modules, and price shown come from the configured subscription.",
  commercialBlocked: "Commercial mismatch",
  commercialVerified: "Schedule matches",
  mismatchTitle: "Signing blocked",
  mismatchSummary: "A mismatch between the plan and the commercial configuration blocks signing. Details are below.",
  planLabel: "Plan",
  moduleCap: "Modules",
  creditsLabel: "Monthly AI credits",
  cycleLabel: "Term",
  optionalTopups: "Optional top-ups",
  freeCancellation: "Without penalty, as the agreement states",
  baseAccess: "Base access",
  unlimited: "As stated in the agreement",
  perMonth: "per month",
  taxLabel: "Tax terms",
  renewalLabel: "Renewal",
  editProfile: "Edit legal profile",
  reviewAgreements: "Review agreements",
  step3Title: "Agreement review",
  step3Description: "Read each document before consenting. The text shown is the stored original, with no automatic legal translation.",
  step4Title: "Verification and signature",
  step4Description: "Signing requires the one-time code, the authority attestation, and express consent.",
  testIndicator: "Test",
  testDetailsSummary: "Test and incorporation status",
  testDetailsBody: "A pilot test signature is not a legally finalized signature and is not a countersignature. It does not establish that PMC Solutions AI is incorporated.",
  incorporationSummary: "Provider incorporation status",
  incorporationBody: "This record does not present PMC Solutions AI as an incorporated company. No certificate of incorporation is asserted here.",
  optionalSaas: "Optional. Not required for a standard SaaS subscription.",
  consult: "Read",
  download: "Download PDF",
  sign: "Sign electronically",
  typeNda: "Non-disclosure agreement",
  typeMsa: "SaaS master agreement",
  typeDpa: "Data processing agreement",
  typeLicense: "Avenqo private software license",
  statusAwaiting: "Awaiting signature",
  statusCustomerSigned: "Signed by the customer, countersignature not recorded",
  statusExecuted: "Executed on the record",
  statusPilot: "Pilot test signature, not finalized",
  lastModified: "Last modified",
  signedOn: "Signed on",
  versionLabel: "Version",
  archiveAgreement: "Document",
  archiveStatus: "Status",
  archiveSignatory: "Signatory",
  archiveHash: "SHA-256",
  archiveDownload: "Download",
  signatoryPending: "Pending",
  close: "Close",
  challengePrompt: "A one-time code is required before signing. It is not shown here.",
  requestCode: "Send the code",
  generatingCode: "Sending…",
  challengeDelivered: "The code was placed in the company test mailbox. No email left the test environment. Open Team to read it, then enter it here.",
  challengeTtl: "Single use, 15 minutes",
  signatoryTitle: "Signatory title",
  verificationCode: "8-digit code",
  authorityConsent: "I confirm that I have legal authority to bind the company.",
  termsConsent: "I have read this document and I consent to sign it electronically.",
  downloadDraft: "Download PDF",
  signing: "Submitting signature…",
  signAction: "Sign this document",
  profileSaved: "Legal profile saved.",
  loadError: "The document could not be loaded.",
  codeNotSent: "The code was not sent. Signing stays disabled.",
  codeNotDelivered: "The code could not be delivered. No code was shown.",
  authorityRequired: "You must attest that you have authority to bind the company.",
  consentRequired: "Express consent to the document is required.",
  signFailed: "The signature was not recorded.",
  pilotSaved: "Pilot signature recorded for {title}. This is not a countersignature and PMC Solutions AI is not marked incorporated.",
  signedPendingCountersign: "Document {title} was signed. A provider countersignature is not recorded.",
  manuscriptSaved: "The manuscript was uploaded and queued for review.",
  uploadFailed: "The upload did not complete.",
  validationError: "The legal profile could not be validated.",
  governingNotice: "Approved text in {language}. No legal translation of this clause is substituted for the original.",
  pdfPreview: "PDF preview",
  readableHeading: "Document text",
  noContracts: "No document is available for this company.",
  dismiss: "Dismiss alert",
  legalReviewBanner: "Document under legal review — consultation only",
  approvalNotFinal: "The text is not legally final. A pilot signature is not an executed contract.",
  codeWhy: "This code is sent to the company address to confirm that the person signing controls that address. It expires after 15 minutes, works once, and is not requested in order to read or download.",
  pdfLoading: "Preparing the pages…",
  pdfFailed: "The PDF could not be displayed. Download uses the same file.",
  pdfPage: "Page",
  pdfOf: "of",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  gateTitle: "The workspace is not open yet",
  gateBody: "After registration and module selection, the required SaaS agreements must be accepted and the Stripe test payment must be confirmed. The private-server license is not required. Payment is recorded only when Stripe confirms it.",
  gateContracts: "Read and sign the agreements",
  gateCheckout: "Stripe test payment",
};

/** Approved UI copy only. fr-FR and en-GB reuse the same language, not a new translation. */
export const CONTRACTS_UI_EXPLICIT: Partial<Record<LocaleCode, ContractsUiCopy>> = {
  fr,
  "fr-FR": fr,
  en,
  "en-GB": en,
};

/** Existing approved catalogs. These keys are not translated here. */
export const CONTRACTS_CATALOG_BACKED_KEYS = ["firstName", "lastName", "billingEmail", "refresh", "close"] as const;

function catalogContractLabels(locale: string): Pick<ContractsUiCopy, (typeof CONTRACTS_CATALOG_BACKED_KEYS)[number]> {
  const catalog = getApplicationCatalog(locale);
  const common = APP_COMMON_WORDS[locale as LocaleCode] ?? APP_COMMON_WORDS.en;
  return {
    firstName: catalog.auth.firstName,
    lastName: catalog.auth.lastName,
    billingEmail: catalog.auth.billingEmail,
    refresh: catalog.company.employeesRefreshTooltip,
    close: common.close,
  };
}

export function getContractsUi(locale: string): {
  copy: ContractsUiCopy;
  explicit: boolean;
  fallbackLocale: "fr" | "en";
  catalogBackedKeys: readonly string[];
} {
  const direct = CONTRACTS_UI_EXPLICIT[locale as LocaleCode];
  const fallbackLocale = locale.toLowerCase().startsWith("fr") ? "fr" : "en";
  const base = direct ?? (CONTRACTS_UI_EXPLICIT[fallbackLocale] as ContractsUiCopy);
  return {
    copy: { ...base, ...catalogContractLabels(locale) },
    explicit: Boolean(direct),
    fallbackLocale,
    catalogBackedKeys: CONTRACTS_CATALOG_BACKED_KEYS,
  };
}

export function fillContractCopy(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce((text, [key, value]) => text.replaceAll(`{${key}}`, value), template);
}

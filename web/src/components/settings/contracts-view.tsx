"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  FileText,
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertCircle,
  Download,
  Upload,
  Eye,
  RefreshCw,
  Lock,
  ArrowRight,
  ChevronRight,
  ExternalLink,
  X,
  FileCheck,
  Building,
  UserCheck,
  Calendar,
  AlertTriangle,
  Send,
  FileBadge,
} from "lucide-react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { RequestFailure } from "@/components/ui/request-failure";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { useOptionalSession } from "@/lib/session-context";

export interface ContractItem {
  id: string;
  company_id: string;
  contract_type: string;
  title: string;
  status: string;
  execution_state?: string;
  version: string;
  language: string;
  signature_mode: "ELECTRONIC" | "MANUSCRIPT_WET_INK" | null;
  signatory_name: string | null;
  signatory_title: string | null;
  signatory_email: string | null;
  signed_at: string | null;
  provider_signed_at?: string | null;
  sha256_hash: string;
  has_pdf: boolean;
}

export interface ContractDetail {
  id: string;
  contract_type: string;
  title: string;
  status: string;
  execution_state?: string;
  version: string;
  language: string;
  content_text: string;
  sha256_hash: string;
  signatory_name: string | null;
  signatory_title: string | null;
  signatory_email: string | null;
  signed_at: string | null;
  provider_signed_at?: string | null;
  signature_mode: string | null;
}

export function ContractsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const session = useOptionalSession();
  const isFrench = locale.startsWith("fr");

  const [activeMainTab, setActiveMainTab] = useState<"wizard" | "archive">("wizard");
  const [currentWizardStep, setCurrentWizardStep] = useState<1 | 2 | 3 | 4>(1);

  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiRequestError | null>(null);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);

  // Étape 1 : Formulaire Profil Juridique
  const [legalProfile, setLegalProfile] = useState<any>({
    legal_name: "",
    trade_name: "",
    country: "Canada",
    province_state: "Québec",
    registration_number: "",
    business_number: "",
    tax_id_gst: "",
    tax_id_qst: "",
    registered_address_street: "",
    registered_address_city: "",
    registered_address_state_province: "",
    registered_address_postal_code: "",
    registered_address_country: "Canada",
    phone: "",
    general_email: "",
    billing_email: "",
    authorized_representative_first_name: "",
    authorized_representative_last_name: "",
    authorized_representative_email: "",
    authorized_representative_title: "Président / CEO",
    authorized_representative_capacity: "President",
    authorized_representative_authority_confirmed: false,
  });
  const [profileSaving, setProfileSaving] = useState(false);

  // Étape 2 : Bordereau Commercial
  const [commercialSchedule, setCommercialSchedule] = useState<any>(null);

  // Étape 3 & 4 : Modal Review & Sign State
  const [selectedContract, setSelectedContract] = useState<ContractDetail | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [signatoryTitle, setSignatoryTitle] = useState("Président / CEO");
  const [declaredAuthority, setDeclaredAuthority] = useState(false);
  const [consentCheckbox, setConsentCheckbox] = useState(false);
  const [signSubmitting, setSignSubmitting] = useState(false);

  // Défi de signature à usage unique
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [challengeCode, setChallengeCode] = useState<string>("");
  const [challengeLoading, setChallengeLoading] = useState(false);

  // Wet-ink scan upload modal
  const [wetInkContract, setWetInkContract] = useState<ContractItem | null>(null);
  const [wetInkFile, setWetInkFile] = useState<File | null>(null);
  const [wetInkSubmitting, setWetInkSubmitting] = useState(false);
  const wetInkInputRef = useRef<HTMLInputElement | null>(null);

  const loadContractsAndWizard = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const headers = getAuthHeaders();
      const [resContracts, resWizard, resProfile, resOrder] = await Promise.all([
        apiFetch("/api/v1/contracts", { headers }),
        apiFetch("/api/v1/contracts/wizard/status", { headers }),
        apiFetch("/api/v1/contracts/legal-profile", { headers }),
        apiFetch("/api/v1/contracts/commercial-order", { headers }),
      ]);

      if (resContracts.ok) {
        const data = await resContracts.json();
        if (Array.isArray(data)) setContracts(data);
      }
      if (resWizard.ok) {
        const wizardData = await resWizard.json();
        if (wizardData.current_step) setCurrentWizardStep(wizardData.current_step);
      }
      if (resProfile.ok) {
        const prof = await resProfile.json();
        if (prof) setLegalProfile((prev: any) => ({ ...prev, ...prof }));
      }
      if (resOrder.ok) {
        const orderData = await resOrder.json();
        setCommercialSchedule(orderData);
      }
    } catch (err: any) {
      setLoadError(err instanceof ApiRequestError ? err : new ApiRequestError("backend_error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadContractsAndWizard();
  }, [loadContractsAndWizard]);

  const handleSaveLegalProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileSaving(true);
    setAlertError(null);
    try {
      const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
      const res = await apiFetch("/api/v1/contracts/legal-profile", {
        method: "POST",
        headers,
        body: JSON.stringify(legalProfile),
      });
      if (!res.ok) {
        const errJson = await res.json();
        const errDetail = Array.isArray(errJson.detail)
          ? errJson.detail.map((d: any) => d.message).join(" ")
          : errJson.detail || "Erreur de validation du profil juridique";
        throw new Error(errDetail);
      }
      setAlertSuccess(
        isFrench
          ? "Profil juridique et représentant légal enregistrés avec succès."
          : "Corporate legal profile and representative saved successfully."
      );
      void loadContractsAndWizard();
      setCurrentWizardStep(2);
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleOpenReview = async (item: ContractItem) => {
    setReviewLoading(true);
    setAlertError(null);
    try {
      const res = await apiFetch(`/api/v1/contracts/${item.contract_type}`, { headers: getAuthHeaders() });
      if (!res.ok) {
        throw new Error(isFrench ? "Erreur de chargement du contrat" : "Failed to load contract");
      }
      const detail: ContractDetail = await res.json();
      setSelectedContract(detail);
      setDeclaredAuthority(false);
      setConsentCheckbox(false);
      setChallengeId(null);
      setChallengeCode("");
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setReviewLoading(false);
    }
  };

  const handleRequestChallenge = async () => {
    if (!selectedContract) return;
    setChallengeLoading(true);
    try {
      const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
      const res = await apiFetch(`/api/v1/contracts/signing-challenge?contract_type=${selectedContract.contract_type}`, {
        method: "POST",
        headers,
      });
      const ch = await res.json();
      if ((ch.delivery !== "email" && ch.delivery !== "sandbox_mailbox") || !ch.challenge_id) {
        setAlertError(isFrench
          ? "Le code n'a pas été transmis. La signature reste désactivée."
          : "The code was not sent. Signing stays disabled.");
        return;
      }
      setChallengeId(ch.challenge_id);
      setChallengeCode("");
    } catch (e: any) {
      setAlertError(e?.publicMessage || (isFrench
        ? "Livraison du code impossible. Aucun code n'a été affiché."
        : "The code could not be delivered. No code was shown."));
    } finally {
      setChallengeLoading(false);
    }
  };

  const handleSubmitSignature = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContract) return;

    if (!declaredAuthority) {
      setAlertError(
        isFrench
          ? "Vous devez attester disposer du pouvoir d'engagement légal pour l'entreprise."
          : "You must declare having the legal authority to bind the company."
      );
      return;
    }
    if (!consentCheckbox) {
      setAlertError(
        isFrench
          ? "Le consentement exprès et explicite aux termes du contrat est obligatoire."
          : "Explicit consent to the contractual terms is required."
      );
      return;
    }

    setSignSubmitting(true);
    setAlertError(null);

    try {
      const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
      const body = {
        signatory_title: signatoryTitle,
        declared_authority: declaredAuthority,
        consent_checkbox: consentCheckbox,
        challenge_id: challengeId,
        challenge_code: challengeCode,
      };

      const res = await apiFetch(`/api/v1/contracts/${selectedContract.contract_type}/sign`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || (isFrench ? "Échec de signature" : "Signing failed"));
      }

      setAlertSuccess(
        isFrench
          ? `Le contrat ${selectedContract.title} a été signé avec succès (en attente de contreseing autorisée du fournisseur).`
          : `Agreement ${selectedContract.title} has been signed successfully (pending provider countersignature).`
      );
      setSelectedContract(null);
      void loadContractsAndWizard();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setSignSubmitting(false);
    }
  };

  const handleUploadWetInk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wetInkContract || !wetInkFile) return;

    setWetInkSubmitting(true);
    setAlertError(null);

    try {
      const formData = new FormData();
      formData.append("file", wetInkFile);
      formData.append("signatory_title", signatoryTitle);

      const headers = getAuthHeaders();
      const res = await apiFetch(`/api/v1/contracts/${wetInkContract.contract_type}/upload-manuscript`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || (isFrench ? "Échec du téléversement" : "Upload failed"));
      }

      setAlertSuccess(
        isFrench
          ? "Contrat manuscrit téléversé. Il a été placé en attente de vérification par l'administrateur."
          : "Manuscript agreement uploaded and queued for administrative review."
      );
      setWetInkContract(null);
      setWetInkFile(null);
      void loadContractsAndWizard();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setWetInkSubmitting(false);
    }
  };

  const signedCount = contracts.filter((c) => c.status === "CUSTOMER_SIGNED" || c.status === "SIGNED" || c.status === "FULLY_EXECUTED").length;
  const pendingCount = contracts.filter((c) => c.status === "PENDING_SIGNATURE" || c.status === "DRAFT").length;

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF]">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {isFrench ? "Contrats d'Entreprise & Onboarding Juridique" : "Enterprise Agreements & Legal Onboarding"}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                {isFrench
                  ? "Parcours contractuel 4 étapes certifié : identité corporative, bordereau commercial, revue légale et signature sécurisée."
                  : "4-step contractual onboarding journey: legal identity, commercial order, legal review, and secure execution."}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => void loadContractsAndWizard()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-[#0076FF]" : ""} />
            <span>{isFrench ? "Actualiser" : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Main Tab Switcher */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-white/[0.08] pb-1">
        <button
          onClick={() => setActiveMainTab("wizard")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            activeMainTab === "wizard"
              ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/20"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
          }`}
        >
          {isFrench ? "Parcours d'Onboarding Contractuel (4 Étapes)" : "Contractual Onboarding (4 Steps)"}
        </button>
        <button
          onClick={() => setActiveMainTab("archive")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            activeMainTab === "archive"
              ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/20"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
          }`}
        >
          {isFrench ? "Mes Contrats & Registre d'Achèvement" : "Executed Agreements & Archive"}
        </button>
      </div>

      {/* Alerts */}
      {alertError && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={16} className="text-amber-600 shrink-0" />
            <span>{alertError}</span>
          </div>
          <button onClick={() => setAlertError(null)}>
            <X size={14} />
          </button>
        </div>
      )}

      {alertSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            <span>{alertSuccess}</span>
          </div>
          <button onClick={() => setAlertSuccess(null)}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* WIZARD VIEW */}
      {activeMainTab === "wizard" && (
        <div className="space-y-6">
          {/* Progress Indicator */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { step: 1, label: isFrench ? "1. Profil Juridique" : "1. Business Info" },
              { step: 2, label: isFrench ? "2. Bordereau Commercial" : "2. Commercial Order" },
              { step: 3, label: isFrench ? "3. Revue des Accords" : "3. Review Agreements" },
              { step: 4, label: isFrench ? "4. Signature Sécurisée" : "4. Verify & Sign" },
            ].map((s) => {
              const isDone = s.step < currentWizardStep;
              const isCurr = s.step === currentWizardStep;
              return (
                <button
                  key={s.step}
                  onClick={() => setCurrentWizardStep(s.step as any)}
                  className={`p-3 rounded-2xl text-left border transition-all ${
                    isCurr
                      ? "bg-blue-50/70 dark:bg-[#111D3D] border-[#0076FF] text-[#0076FF]"
                      : isDone
                      ? "bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-300 dark:border-emerald-800 text-emerald-700"
                      : "bg-slate-50 dark:bg-white/[0.03] border-slate-200/80 dark:border-white/[0.08] text-slate-500"
                  }`}
                >
                  <div className="text-[10px] font-bold uppercase tracking-wider">
                    {isDone ? "✓ Terminé" : isCurr ? "En cours" : "À venir"}
                  </div>
                  <div className="text-xs font-extrabold mt-0.5">{s.label}</div>
                </button>
              );
            })}
          </div>

          {/* STEP 1: BUSINESS INFORMATION */}
          {currentWizardStep === 1 && (
            <div className="p-6 rounded-3xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-6">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {isFrench ? "Étape 1 : Identité Corporative & Représentant Légal" : "Step 1: Legal Entity & Signatory"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {isFrench
                    ? "Veuillez renseigner les coordonnées officielles exactes qui figureront sur vos contrats certifiés (Loi 25 et LCCJTI)."
                    : "Enter your official company details to be interpolated into your certified legal agreements."}
                </p>
              </div>

              <form onSubmit={handleSaveLegalProfile} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Dénomination légale complète *" : "Full Legal Entity Name *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.legal_name || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, legal_name: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="Ex: Acme Solutions Canada Inc."
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Nom commercial / Nom d'usage (si différent)" : "Trade Name (optional)"}
                    </label>
                    <input
                      type="text"
                      value={legalProfile.trade_name || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, trade_name: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="Ex: Acme AI"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Pays d'immatriculation *" : "Country *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.country || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, country: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Province / État / Région *" : "Province / State *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.province_state || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, province_state: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {legalProfile.country?.toLowerCase() === "canada" &&
                      legalProfile.province_state?.toLowerCase().includes("qu")
                        ? "NEQ (10 chiffres) *"
                        : isFrench
                        ? "N° d'enregistrement / Registre"
                        : "Registration / State Number"}
                    </label>
                    <input
                      type="text"
                      value={legalProfile.registration_number || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, registration_number: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white font-mono"
                      placeholder="Ex: 1178945612"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Adresse du siège légal *" : "Registered Street Address *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.registered_address_street || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, registered_address_street: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="Ex: 1250 Boulevard René-Lévesque O"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Ville *" : "City *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.registered_address_city || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, registered_address_city: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="Montréal"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Code Postal *" : "Postal Code *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.registered_address_postal_code || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, registered_address_postal_code: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="H3B 4W8"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Téléphone professionnel *" : "Phone *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={legalProfile.phone || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, phone: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="+1-514-555-0100"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Courriel de facturation *" : "Billing Email *"}
                    </label>
                    <input
                      type="email"
                      required
                      value={legalProfile.billing_email || ""}
                      onChange={(e) => setLegalProfile({ ...legalProfile, billing_email: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      placeholder="facturation@acme.ca"
                    />
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-100 dark:border-white/[0.06]">
                  <h4 className="text-xs font-black uppercase text-slate-500 mb-3">
                    {isFrench ? "Signataire & Représentant Autorisé" : "Authorized Signatory"}
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {isFrench ? "Prénom *" : "First Name *"}
                      </label>
                      <input
                        type="text"
                        required
                        value={legalProfile.authorized_representative_first_name || ""}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_first_name: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {isFrench ? "Nom de famille *" : "Last Name *"}
                      </label>
                      <input
                        type="text"
                        required
                        value={legalProfile.authorized_representative_last_name || ""}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_last_name: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {isFrench ? "Courriel professionnel *" : "Professional Email *"}
                      </label>
                      <input
                        type="email"
                        required
                        value={legalProfile.authorized_representative_email || ""}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_email: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {isFrench ? "Fonction / Titre *" : "Job Title *"}
                      </label>
                      <input
                        type="text"
                        required
                        value={legalProfile.authorized_representative_title || ""}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_title: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {isFrench ? "Qualité d'engagement légal *" : "Legal Capacity *"}
                      </label>
                      <select
                        value={legalProfile.authorized_representative_capacity || "Owner"}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_capacity: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      >
                        <option value="Owner">Owner / Propriétaire</option>
                        <option value="President">President / Président</option>
                        <option value="CEO">CEO / Directeur Général</option>
                        <option value="Authorized Director">Authorized Director / Administrateur</option>
                        <option value="Authorized Officer">Authorized Officer / Dirigeant</option>
                        <option value="Authorized Representative">Authorized Representative / Mandataire</option>
                      </select>
                    </div>
                  </div>

                  <div className="mt-4 p-3.5 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200 dark:border-white/[0.08]">
                    <label className="flex items-start gap-2.5 cursor-pointer text-xs font-semibold text-slate-800 dark:text-slate-200">
                      <input
                        type="checkbox"
                        checked={legalProfile.authorized_representative_authority_confirmed || false}
                        onChange={(e) =>
                          setLegalProfile({
                            ...legalProfile,
                            authorized_representative_authority_confirmed: e.target.checked,
                          })
                        }
                        className="mt-0.5 rounded text-[#0076FF]"
                      />
                      <span>
                        {isFrench
                          ? "J'atteste expressément disposer de l'autorité et du pouvoir d'engagement légal pour représenter et lier l'entreprise dans le cadre des accords commerciaux Avenqo."
                          : "I expressly declare that I possess the legal authority and binding power to represent the company in Avenqo enterprise agreements."}
                      </span>
                    </label>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={profileSaving}
                    className="px-6 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition-all"
                  >
                    {profileSaving
                      ? "Enregistrement..."
                      : isFrench
                      ? "Enregistrer & Passer à l'Étape 2 →"
                      : "Save & Proceed to Step 2 →"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* STEP 2: COMMERCIAL CONFIGURATION */}
          {currentWizardStep === 2 && commercialSchedule && (
            <div className="p-6 rounded-3xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                    {isFrench ? "Étape 2 : Bordereau de Commande Commerciale Dynamique" : "Step 2: Commercial Order Schedule"}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {isFrench
                      ? "Réconciliation stricte entre votre forfait souscrit, les modules activés et la tarification Stripe."
                      : "Strict reconciliation between plan, active modules, and configured Stripe price IDs."}
                  </p>
                </div>
                <div>
                  {commercialSchedule.is_blocked ? (
                    <span className="px-3 py-1 rounded-full bg-red-100 text-red-800 text-xs font-bold flex items-center gap-1.5">
                      <AlertTriangle size={14} /> COMMERCIAL_CONFIG_MISMATCH
                    </span>
                  ) : (
                    <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold flex items-center gap-1.5">
                      <CheckCircle2 size={14} /> CONCORDANCE VÉRIFIÉE
                    </span>
                  )}
                </div>
              </div>

              {commercialSchedule.is_blocked && (
                <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-300 dark:border-red-800/40 text-red-900 dark:text-red-200 text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5">
                    <AlertTriangle size={16} /> Signature bloquée (Divergence commerciale détectée) :
                  </div>
                  <ul className="list-disc pl-5 space-y-0.5">
                    {commercialSchedule.mismatches?.map((m: string, i: number) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06]">
                  <span className="text-xs text-slate-500">Forfait Souscrit</span>
                  <div className="text-lg font-black text-slate-900 dark:text-white mt-0.5 uppercase">
                    {commercialSchedule.plan_name}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    {commercialSchedule.monthly_price} {commercialSchedule.currency} / mois
                  </div>
                </div>
                <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06]">
                  <span className="text-xs text-slate-500">Plafond de Modules</span>
                  <div className="text-lg font-black text-slate-900 dark:text-white mt-0.5">
                    {commercialSchedule.selected_modules?.length || 0} / {commercialSchedule.max_selectable_modules || "∞"}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    {commercialSchedule.selected_modules?.join(", ") || "Accès socle"}
                  </div>
                </div>
                <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06]">
                  <span className="text-xs text-slate-500">Crédits IA Mensuels</span>
                  <div className="text-lg font-black text-slate-900 dark:text-white mt-0.5">
                    {commercialSchedule.included_ai_credits?.toLocaleString() || "Illimité"}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">Rechargements optionnels</div>
                </div>
                <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06]">
                  <span className="text-xs text-slate-500">Cycle & Résiliation</span>
                  <div className="text-lg font-black text-slate-900 dark:text-white mt-0.5">Libre</div>
                  <div className="text-xs text-slate-400 mt-1">Sans pénalité à tout moment</div>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.03] text-xs text-slate-600 dark:text-slate-300 space-y-1">
                <div>
                  <b>Conditions fiscales :</b> {commercialSchedule.applicable_taxes}
                </div>
                <div>
                  <b>Renouvellement :</b> {commercialSchedule.renewal_terms}
                </div>
              </div>

              <div className="flex justify-between items-center pt-2">
                <button
                  onClick={() => setCurrentWizardStep(1)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50"
                >
                  ← {isFrench ? "Modifier Profil Juridique" : "Edit Business Info"}
                </button>
                <button
                  disabled={commercialSchedule.is_blocked}
                  onClick={() => setCurrentWizardStep(3)}
                  className={`px-6 py-2.5 rounded-xl text-white font-bold text-xs shadow-md transition-all ${
                    commercialSchedule.is_blocked ? "bg-slate-400 cursor-not-allowed" : "bg-[#0076FF] hover:bg-blue-600"
                  }`}
                >
                  {isFrench ? "Examiner les Contrats (Étape 3) →" : "Review Agreements (Step 3) →"}
                </button>
              </div>
            </div>
          )}

          {/* STEP 3 & 4: REVIEW & SIGN */}
          {(currentWizardStep === 3 || currentWizardStep === 4) && (
            <div className="p-6 rounded-3xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-6">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {currentWizardStep === 3
                    ? isFrench
                      ? "Étape 3 : Revue Exhaustive des Accords Contractuels"
                      : "Step 3: Comprehensive Agreements Review"
                    : isFrench
                    ? "Étape 4 : Vérification, Défi Anti-Rejeu & Signature"
                    : "Step 4: Verify Identity & Sign"}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {isFrench
                    ? "Tous les documents ci-dessous intègrent votre profil juridique vérifié et les barèmes officiels."
                    : "The agreements below incorporate your verified corporate identity and official order schedule."}
                </p>
              </div>

              {/* Notice Bac à sable */}
              <div className="p-4 rounded-2xl bg-amber-50 dark:bg-amber-950/20 border border-amber-300 dark:border-amber-800/40 text-amber-900 dark:text-amber-300 text-xs leading-relaxed flex items-start gap-3">
                <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold">
                    {isFrench ? "Environnement Bac à Sable (Sandbox) :" : "Sandbox Environment Notice:"}
                  </span>
                  <p className="mt-0.5">
                    {isFrench
                      ? "PMC Solutions AI est actuellement en cours d'incorporation au Québec, Canada. Vos signatures apposées constituent une validation pilote d'entreprise dans l'environnement bac à sable. La contresignature finale sera effectuée dès publication du certificat officiel d'incorporation."
                      : "PMC Solutions AI is currently in the process of incorporation in Quebec, Canada. Contracts signed in this environment are sandbox-verified and await official corporate countersignature."}
                  </p>
                </div>
              </div>

              {/* Grid of Contracts to Review/Sign */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {contracts.map((item) => {
                  const isSigned = item.status === "CUSTOMER_SIGNED" || item.status === "SIGNED" || item.status === "FULLY_EXECUTED";
                  return (
                    <div
                      key={item.id}
                      className="p-5 rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] flex flex-col justify-between gap-4"
                    >
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-200/60 dark:bg-white/[0.06] text-slate-600 dark:text-slate-300 font-bold">
                            {item.contract_type} ({item.version})
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              isSigned
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {item.status}
                          </span>
                        </div>
                        <h4 className="text-sm font-bold text-slate-900 dark:text-white mt-2">{item.title}</h4>
                      </div>

                      <div className="flex items-center gap-2 pt-2 border-t border-slate-200/60 dark:border-white/[0.06]">
                        <button
                          onClick={() => handleOpenReview(item)}
                          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/[0.1] text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-50 shadow-xs"
                        >
                          <Eye size={13} />
                          {isFrench ? "Consulter & Signer" : "Review & Sign"}
                        </button>
                        <a
                          href={`/api/v1/contracts/${item.contract_type}/download`}
                          target="_blank"
                          rel="noreferrer"
                          className="p-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/[0.1] text-slate-600 hover:text-[#0076FF]"
                          title={isFrench ? "Télécharger le PDF" : "Download PDF"}
                        >
                          <Download size={15} />
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ARCHIVE VIEW */}
      {activeMainTab === "archive" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden bg-white dark:bg-[#0B132B]">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-white/[0.03] text-slate-500 border-b border-slate-200/80 dark:border-white/[0.08]">
                <tr>
                  <th className="p-3 font-bold">{isFrench ? "Contrat" : "Agreement"}</th>
                  <th className="p-3 font-bold">{isFrench ? "Statut" : "Status"}</th>
                  <th className="p-3 font-bold">{isFrench ? "Signataire" : "Signatory"}</th>
                  <th className="p-3 font-bold">{isFrench ? "Empreinte SHA-256" : "SHA-256"}</th>
                  <th className="p-3 font-bold">{isFrench ? "Téléchargement" : "Download"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {contracts.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                    <td className="p-3 font-semibold text-slate-900 dark:text-white">
                      <div>{c.title}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{c.contract_type}</div>
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          c.status === "FULLY_EXECUTED"
                            ? "bg-emerald-100 text-emerald-800"
                            : c.status === "CUSTOMER_SIGNED" || c.status === "SIGNED"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-300">
                      {c.signatory_name || "En attente"}
                      {c.signed_at && <div className="text-[10px] text-slate-400">{c.signed_at.slice(0, 10)}</div>}
                    </td>
                    <td className="p-3 font-mono text-[10px] text-slate-500">
                      {c.sha256_hash ? `${c.sha256_hash.slice(0, 16)}...` : "—"}
                    </td>
                    <td className="p-3">
                      <a
                        href={`/api/v1/contracts/${c.contract_type}/download`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[#0076FF] hover:underline font-bold"
                      >
                        <Download size={13} /> PDF
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODAL : CONSULTATION & SIGNATURE ÉLECTRONIQUE */}
      {selectedContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-white dark:bg-[#0B132B] rounded-3xl border border-slate-200 dark:border-white/[0.1] max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-5 border-b border-slate-200 dark:border-white/[0.08] flex items-center justify-between">
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">
                  {selectedContract.contract_type} • {selectedContract.version}
                </span>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white mt-0.5">
                  {selectedContract.title}
                </h3>
              </div>
              <button onClick={() => setSelectedContract(null)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>

            <div className="p-5 overflow-y-auto flex-1 font-mono text-xs leading-relaxed text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-[#060A17] whitespace-pre-wrap select-text">
              {selectedContract.content_text}
            </div>

            <div className="p-5 border-t border-slate-200 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] space-y-4">
              {/* Jeton / Défi de signature anti-rejeu */}
              {!challengeId ? (
                <div className="p-3.5 rounded-xl bg-blue-50 dark:bg-[#111D3D] border border-blue-200 dark:border-blue-900 flex items-center justify-between">
                  <div className="text-xs text-blue-900 dark:text-blue-200">
                    <b>Émission du jeton de sécurité :</b> Un code de signature à usage unique est requis.
                  </div>
                  <button
                    onClick={handleRequestChallenge}
                    disabled={challengeLoading}
                    className="px-3 py-1.5 rounded-xl bg-[#0076FF] text-white text-xs font-bold"
                  >
                    {challengeLoading ? "Génération..." : "Obtenir mon code"}
                  </button>
                </div>
              ) : (
                <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-300 text-xs text-emerald-900 dark:text-emerald-200 flex items-center justify-between">
                  <div>
                    <b>Code placé dans la boîte Sandbox de l'entreprise. Aucun courriel n'a quitté Sandbox. Ouvrez Équipe pour le lire, puis saisissez-le ici.</b>
                  </div>
                  <span className="text-[10px] text-slate-400">Usage unique • 15 min</span>
                </div>
              )}

              <form onSubmit={handleSubmitSignature} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Titre / Fonction légale *" : "Job Title *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={signatoryTitle}
                      onChange={(e) => setSignatoryTitle(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {isFrench ? "Code reçu par email à 8 chiffres *" : "8-digit email verification code *"}
                    </label>
                    <input
                      type="text"
                      required
                      value={challengeCode}
                      onChange={(e) => setChallengeCode(e.target.value)}
                      inputMode="numeric"
                      pattern="[0-9]{8}"
                      placeholder="Ex: 84920137"
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-mono font-bold text-slate-900 dark:text-white"
                    />
                  </div>
                </div>

                <div className="space-y-2 pt-1">
                  <label className="flex items-start gap-2 cursor-pointer text-xs font-medium text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={declaredAuthority}
                      onChange={(e) => setDeclaredAuthority(e.target.checked)}
                      className="mt-0.5 rounded text-[#0076FF]"
                    />
                    <span>
                      {isFrench
                        ? "Je confirme expressément avoir l'autorité légale et le pouvoir d'engagement pour lier l'entreprise."
                        : "I expressly confirm having the legal authority and binding power to commit the company."}
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer text-xs font-medium text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={consentCheckbox}
                      onChange={(e) => setConsentCheckbox(e.target.checked)}
                      className="mt-0.5 rounded text-[#0076FF]"
                    />
                    <span>
                      {isFrench
                        ? "J'accepte expressément les termes légaux et consens à l'utilisation de la signature électronique."
                        : "I expressly agree to the terms and consent to the use of electronic records and signatures."}
                    </span>
                  </label>
                </div>

                <div className="flex justify-between items-center pt-3 border-t border-slate-100 dark:border-white/[0.06]">
                  <a
                    href={`/api/v1/contracts/${selectedContract.contract_type}/download`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800"
                  >
                    <Download size={13} /> {isFrench ? "Télécharger le brouillon PDF" : "Download Draft PDF"}
                  </a>
                  <button
                    type="submit"
                    disabled={signSubmitting || !declaredAuthority || !consentCheckbox || !challengeId}
                    className="px-6 py-2 rounded-xl bg-[#0076FF] hover:bg-blue-600 disabled:bg-slate-300 text-white font-bold text-xs shadow-md transition-all"
                  >
                    {signSubmitting ? "Signature en cours..." : isFrench ? "Signer Numériquement (1-Clic)" : "Sign Digitally (1-Click)"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

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
import { useOptionalSession } from "@/lib/session-context";
import { AvenqoCard } from "@/components/ui/avenqo-card";
import { CompactStepper, type StepState } from "@/components/ui/compact-stepper";
import { StatusBadge } from "@/components/ui/status-badge";
import { fillContractCopy, getContractsUi } from "@/lib/i18n/contracts-ui-copy";
import { privateLicenseRequiredForPlan } from "@/lib/contracts/private-license";
import { isSandboxFrontend } from "@/lib/public-site";
import { ContractPdfReader } from "@/components/settings/contract-pdf-reader";

export interface ContractItem {
  id: string;
  company_id: string;
  contract_type: string;
  title: string;
  status: string;
  execution_state?: string;
  version: string;
  language: string;
  signature_mode: "ELECTRONIC" | "MANUSCRIPT_WET_INK" | "SANDBOX_PILOT" | null;
  signatory_name: string | null;
  signatory_title: string | null;
  signatory_email: string | null;
  signed_at: string | null;
  provider_signed_at?: string | null;
  sha256_hash: string;
  has_pdf: boolean;
  approval_status?: string;
  signable?: boolean;
  updated_at?: string | null;
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
  approval_status?: string;
  signable?: boolean;
}

function underReview(item: { approval_status?: string }) {
  const approval = (item.approval_status || "").toUpperCase();
  return approval.includes("LEGAL_REVIEW")
    || approval === "UNDER_REVIEW"
    || approval.startsWith("UNDER_REVIEW");
}

export function ContractsView() {
  const { locale } = useLocale();
  const session = useOptionalSession();
  const copy = getContractsUi(locale).copy;
  const sandboxUi = isSandboxFrontend();

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
  const [panelMode, setPanelMode] = useState<"read" | "sign" | null>(null);
  const [pdfBytes, setPdfBytes] = useState<ArrayBuffer | null>(null);
  const [pdfName, setPdfName] = useState("contrat.pdf");
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Défi de signature à usage unique
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [challengeCode, setChallengeCode] = useState<string>("");
  const [challengeLoading, setChallengeLoading] = useState(false);
  const [challengeDelivery, setChallengeDelivery] = useState<string | null>(null);
  const [challengeRecipientMasked, setChallengeRecipientMasked] = useState<string | null>(null);

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
          : errJson.detail || copy.validationError;
        throw new Error(errDetail);
      }
      setAlertSuccess(copy.profileSaved);
      void loadContractsAndWizard();
      setCurrentWizardStep(2);
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const savePdfFile = (bytes: ArrayBuffer, filename: string) => {
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const loadContractPdf = async (contractType: string) => {
    const response = await apiFetch(`/api/v1/contracts/${contractType}/download`, { headers: getAuthHeaders() });
    const disposition = response.headers.get("content-disposition") || "";
    const matched = disposition.match(/filename="([^"]+)"/);
    const bytes = await response.arrayBuffer();
    return { bytes, filename: matched?.[1] || `${contractType}.pdf` };
  };

  const handleDownload = async (contractType: string) => {
    setAlertError(null);
    try {
      if (selectedContract?.contract_type === contractType && pdfBytes) {
        savePdfFile(pdfBytes, pdfName);
        return;
      }
      const loaded = await loadContractPdf(contractType);
      savePdfFile(loaded.bytes, loaded.filename);
    } catch (err: any) {
      setAlertError(err?.publicMessage || err?.message || copy.loadError);
    }
  };

  const handleOpenReview = async (item: ContractItem, mode: "read" | "sign") => {
    if (mode === "sign" && underReview(item)) return;
    setReviewLoading(true);
    setAlertError(null);
    setPdfError(null);
    try {
      const res = await apiFetch(`/api/v1/contracts/${item.contract_type}`, { headers: getAuthHeaders() });
      if (!res.ok) {
        throw new Error(copy.loadError);
      }
      const detail: ContractDetail = await res.json();
      const loaded = await loadContractPdf(item.contract_type);
      setPdfBytes(loaded.bytes);
      setPdfName(loaded.filename);
      setPanelMode(mode);
      setSelectedContract(detail);
      setDeclaredAuthority(false);
      setConsentCheckbox(false);
      setChallengeId(null);
      setChallengeCode("");
      setChallengeDelivery(null);
      setChallengeRecipientMasked(null);
    } catch (err: any) {
      setPdfBytes(null);
      setPdfError(err?.publicMessage || err?.message || copy.pdfFailed);
      setAlertError(err?.publicMessage || err?.message || copy.loadError);
    } finally {
      setReviewLoading(false);
    }
  };

  const handleRequestChallenge = async () => {
    if (!selectedContract) return;
    setChallengeLoading(true);
    setAlertError(null);
    try {
      const headers = { ...getAuthHeaders(), "Content-Type": "application/json" };
      const res = await apiFetch(`/api/v1/contracts/signing-challenge?contract_type=${selectedContract.contract_type}`, {
        method: "POST",
        headers,
      });
      const ch = await res.json().catch(() => ({} as Record<string, unknown>));
      if (!res.ok) {
        const detail =
          typeof (ch as { detail?: unknown }).detail === "string"
            ? (ch as { detail: string }).detail
            : copy.codeNotDelivered;
        setAlertError(detail);
        setChallengeId(null);
        setChallengeDelivery(null);
        setChallengeRecipientMasked(null);
        return;
      }
      const delivery = typeof ch.delivery === "string" ? ch.delivery : "";
      const accepted =
        delivery === "email_accepted"
        || delivery === "sandbox_internal_capture"
        // Legacy labels from older sandbox builds — treat capture honestly, never as inbox delivery.
        || delivery === "sandbox_mailbox"
        || delivery === "email";
      if (!accepted || !ch.challenge_id) {
        setAlertError(copy.codeNotSent);
        setChallengeId(null);
        setChallengeDelivery(null);
        setChallengeRecipientMasked(null);
        return;
      }
      setChallengeId(String(ch.challenge_id));
      setChallengeDelivery(delivery === "email" ? "email_accepted" : delivery === "sandbox_mailbox" ? "sandbox_internal_capture" : delivery);
      setChallengeRecipientMasked(typeof ch.recipient_masked === "string" ? ch.recipient_masked : null);
      setChallengeCode("");
    } catch (e: any) {
      setAlertError(e?.publicMessage || copy.codeNotDelivered);
      setChallengeId(null);
      setChallengeDelivery(null);
      setChallengeRecipientMasked(null);
    } finally {
      setChallengeLoading(false);
    }
  };

  const challengeStatusMessage = () => {
    if (challengeDelivery === "email_accepted") {
      return fillContractCopy(copy.challengeDeliveredEmail, {
        email: challengeRecipientMasked || "***",
      });
    }
    if (challengeDelivery === "sandbox_internal_capture") {
      return copy.challengeDeliveredCapture;
    }
    return copy.challengeDeliveredPending;
  };

  const handleSubmitSignature = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContract) return;

    if (!declaredAuthority) {
      setAlertError(copy.authorityRequired);
      return;
    }
    if (!consentCheckbox) {
      setAlertError(copy.consentRequired);
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
        const detail = typeof errJson.detail === "string"
          ? errJson.detail
          : errJson.detail?.message || errJson.error?.message;
        throw new Error(detail || copy.signFailed);
      }
      const signed = await res.json();
      setAlertSuccess(
        signed.signature_mode === "SANDBOX_PILOT"
          ? fillContractCopy(copy.pilotSaved, { title: selectedContract.title })
          : fillContractCopy(copy.signedPendingCountersign, { title: selectedContract.title })
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
        throw new Error(errJson.detail || copy.uploadFailed);
      }

      setAlertSuccess(copy.manuscriptSaved);
      setWetInkContract(null);
      setWetInkFile(null);
      void loadContractsAndWizard();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setWetInkSubmitting(false);
    }
  };

  const planName = String(commercialSchedule?.plan_name || session?.identity?.company.subscription_plan || "");
  const licenseRequired = privateLicenseRequiredForPlan(planName);
  const commercialBlocked = Boolean(commercialSchedule?.is_blocked);
  const signedStatuses = new Set(["CUSTOMER_SIGNED", "SIGNED", "FULLY_EXECUTED"]);
  const documentSigned = (item: ContractItem) => signedStatuses.has(item.status);
  const canSignDocument = (item: ContractItem) => !documentSigned(item) && !commercialBlocked && !underReview(item) && item.signable !== false;
  const showTestMark = (item: ContractItem) => sandboxUi || item.signature_mode === "SANDBOX_PILOT";
  const statusText = (item: ContractItem) => {
    if (item.signature_mode === "SANDBOX_PILOT") return copy.statusPilot;
    if (item.status === "FULLY_EXECUTED") return copy.statusExecuted;
    if (documentSigned(item)) return copy.statusCustomerSigned;
    return copy.statusAwaiting;
  };
  const typeText = (type: string) => {
    if (type === "NDA" || type === "MUTUAL_NDA") return copy.typeNda;
    if (type === "MSA" || type === "SAAS_MSA" || type === "SAAS" || type === "SAAS_SUBSCRIPTION") return copy.typeMsa;
    if (type === "DPA" || type === "DATA_PROCESSING_ADDENDUM") return copy.typeDpa;
    if (type === "PRIVATE_LICENSE") return copy.typeLicense;
    return type;
  };
  const formatWhen = (value?: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date);
  };
  const stepState = (step: number): StepState => {
    if (step >= 2 && commercialBlocked) return "blocked";
    if (step < currentWizardStep) return "completed";
    if (step === currentWizardStep) return "current";
    return "upcoming";
  };
  const stepStateText = (state: StepState) => (
    state === "completed" ? copy.stateCompleted
      : state === "current" ? copy.stateCurrent
        : state === "blocked" ? copy.stateBlocked
          : copy.stateUpcoming
  );
  const money = (amount: unknown, currency: string) => {
    const value = typeof amount === "number" ? amount : Number(amount);
    if (!Number.isFinite(value)) return "—";
    try {
      return new Intl.NumberFormat(locale, { style: "currency", currency: currency || "CAD" }).format(value);
    } catch {
      return `${value} ${currency || ""}`.trim();
    }
  };

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl space-y-5 pb-16">
      <div className="flex flex-col gap-3 border-b border-slate-200/80 pb-4 sm:flex-row sm:items-center sm:justify-between dark:border-white/[0.08]">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="rounded-xl bg-blue-50 p-2 text-[#0076FF] dark:bg-[#111D3D] dark:text-[#00D4FF]">
            <ShieldCheck size={20} />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl dark:text-[#F4F7FB]">
              {copy.pageTitle}
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-[#C5D0E0]">{copy.pageSubtitle}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadContractsAndWizard()}
          disabled={loading}
          className="inline-flex h-9 items-center gap-1.5 self-start rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] disabled:opacity-60 dark:border-white/10 dark:text-[#F4F7FB] dark:hover:bg-white/[0.04]"
        >
          <RefreshCw size={14} className={loading ? "animate-spin text-[#0076FF]" : ""} />
          <span>{copy.refresh}</span>
        </button>
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
          {copy.tabOnboarding}
        </button>
        <button
          onClick={() => setActiveMainTab("archive")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
            activeMainTab === "archive"
              ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/20"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
          }`}
        >
          {copy.tabArchive}
        </button>
      </div>

      {loadError && <RequestFailure error={loadError} retry={() => { void loadContractsAndWizard(); }} />}
      {alertError && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={16} className="text-amber-600 shrink-0" />
            <span>{alertError}</span>
          </div>
          <button type="button" onClick={() => setAlertError(null)} aria-label={copy.dismiss}>
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
          <button type="button" onClick={() => setAlertSuccess(null)} aria-label={copy.dismiss}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* WIZARD VIEW */}
      {activeMainTab === "wizard" && (
        <div className="space-y-6">
          {/* Progress Indicator */}
          <CompactStepper
            label={copy.stepperLabel}
            onSelect={(id) => setCurrentWizardStep(Number(id) as 1 | 2 | 3 | 4)}
            steps={[
              { id: "1", label: copy.stepLegal, state: stepState(1), stateLabel: stepStateText(stepState(1)) },
              { id: "2", label: copy.stepOrder, state: stepState(2), stateLabel: stepStateText(stepState(2)) },
              { id: "3", label: copy.stepReview, state: stepState(3), stateLabel: stepStateText(stepState(3)) },
              { id: "4", label: copy.stepSign, state: stepState(4), stateLabel: stepStateText(stepState(4)) },
            ]}
          />

          {/* STEP 1: BUSINESS INFORMATION */}
          {currentWizardStep === 1 && (
            <div className="p-6 rounded-3xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-6">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {copy.step1Title}
                </h3>
                <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
                  {copy.step1Description}
                </p>
              </div>

              <form onSubmit={handleSaveLegalProfile} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {copy.legalName} *
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
                      {copy.tradeName}
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
                      {copy.country} *
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
                      {copy.province} *
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
                        ? `${copy.neq} *`
                        : copy.registration}
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
                      {copy.address} *
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
                      {copy.city} *
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
                      {copy.postalCode} *
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
                      {copy.phone} *
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
                      {copy.billingEmail} *
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
                    {copy.signatorySection}
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                        {copy.firstName} *
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
                        {copy.lastName} *
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
                        {copy.professionalEmail} *
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
                        {copy.jobTitle} *
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
                        {copy.legalCapacity} *
                      </label>
                      <select
                        value={legalProfile.authorized_representative_capacity || "Owner"}
                        onChange={(e) =>
                          setLegalProfile({ ...legalProfile, authorized_representative_capacity: e.target.value })
                        }
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/[0.1] bg-slate-50 dark:bg-white/[0.02] text-xs font-semibold text-slate-900 dark:text-white"
                      >
                        <option value="Owner">{copy.capacityOwner}</option>
                        <option value="President">{copy.capacityPresident}</option>
                        <option value="CEO">{copy.capacityCeo}</option>
                        <option value="Authorized Director">{copy.capacityDirector}</option>
                        <option value="Authorized Officer">{copy.capacityOfficer}</option>
                        <option value="Authorized Representative">{copy.capacityRepresentative}</option>
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
                      <span>{copy.authorityAttestation}</span>
                    </label>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={profileSaving}
                    className="px-6 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-xs shadow-md transition-all"
                  >
                    {profileSaving ? copy.saving : copy.saveProfile}
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
                    {copy.step2Title}
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">{copy.step2Description}</p>
                </div>
                <StatusBadge tone={commercialSchedule.is_blocked ? "warning" : "success"}>
                  {commercialSchedule.is_blocked ? copy.commercialBlocked : copy.commercialVerified}
                </StatusBadge>
              </div>

              {commercialSchedule.is_blocked && (
                <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-xs text-rose-950 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-50">
                  <p className="font-semibold">{copy.mismatchTitle}. {copy.mismatchSummary}</p>
                  {Array.isArray(commercialSchedule.mismatches) && commercialSchedule.mismatches.length > 0 && (
                    <ul className="mt-2 list-disc space-y-0.5 ps-5">
                      {commercialSchedule.mismatches.map((item: string, index: number) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-xl border border-slate-200/70 p-3 dark:border-white/10">
                  <span className="text-xs text-slate-600 dark:text-slate-300">{copy.planLabel}</span>
                  <div className="mt-0.5 text-base font-bold text-slate-900 dark:text-white">{commercialSchedule.plan_name}</div>
                  <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                    {money(commercialSchedule.monthly_price, commercialSchedule.currency || "CAD")} {copy.perMonth}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200/70 p-3 dark:border-white/10">
                  <span className="text-xs text-slate-600 dark:text-slate-300">{copy.moduleCap}</span>
                  <div className="mt-0.5 text-base font-bold text-slate-900 dark:text-white">
                    {commercialSchedule.selected_modules?.length || 0} / {commercialSchedule.max_selectable_modules || "—"}
                  </div>
                  <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                    {commercialSchedule.selected_modules?.join(", ") || copy.baseAccess}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200/70 p-3 dark:border-white/10">
                  <span className="text-xs text-slate-600 dark:text-slate-300">{copy.creditsLabel}</span>
                  <div className="mt-0.5 text-base font-bold text-slate-900 dark:text-white">
                    {typeof commercialSchedule.included_ai_credits === "number"
                      ? commercialSchedule.included_ai_credits.toLocaleString(locale)
                      : copy.unlimited}
                  </div>
                  <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">{copy.optionalTopups}</div>
                </div>
                <div className="rounded-xl border border-slate-200/70 p-3 dark:border-white/10">
                  <span className="text-xs text-slate-600 dark:text-slate-300">{copy.cycleLabel}</span>
                  <div className="mt-0.5 text-sm font-semibold text-slate-900 dark:text-white">{copy.freeCancellation}</div>
                </div>
              </div>

              <div className="space-y-1 rounded-xl bg-slate-50 p-3 text-xs text-slate-700 dark:bg-white/[0.03] dark:text-slate-200">
                <div><span className="font-semibold">{copy.taxLabel} : </span>{commercialSchedule.applicable_taxes}</div>
                <div><span className="font-semibold">{copy.renewalLabel} : </span>{commercialSchedule.renewal_terms}</div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <button type="button" onClick={() => setCurrentWizardStep(1)} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:text-slate-200">
                  {copy.editProfile}
                </button>
                <button
                  type="button"
                  disabled={commercialSchedule.is_blocked}
                  onClick={() => setCurrentWizardStep(3)}
                  className={`rounded-xl px-4 py-2 text-xs font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] ${
                    commercialSchedule.is_blocked ? "cursor-not-allowed bg-slate-400" : "bg-[#0076FF] hover:bg-[#158bff]"
                  }`}
                >
                  {copy.reviewAgreements}
                </button>
              </div>
            </div>
          )}

          {/* STEP 3 & 4: REVIEW & SIGN */}
          {(currentWizardStep === 3 || currentWizardStep === 4) && (
            <div className="p-6 rounded-3xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-6">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {currentWizardStep === 3 ? copy.step3Title : copy.step4Title}
                </h3>
                <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
                  {currentWizardStep === 3 ? copy.step3Description : copy.step4Description}
                </p>
              </div>
              <details className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-200">
                <summary className="cursor-pointer font-semibold">{copy.incorporationSummary}</summary>
                <p className="mt-2">{copy.incorporationBody}</p>
                <p className="mt-2">{copy.testDetailsBody}</p>
              </details>

              {/* Grid of Contracts to Review/Sign */}
              {contracts.length === 0 && (
                <p role="status" className="text-sm text-slate-600 dark:text-slate-300">{loading ? copy.refresh : copy.noContracts}</p>
              )}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))]">
                {contracts.map((item) => {
                  const optional = item.contract_type === "PRIVATE_LICENSE" && !licenseRequired;
                  const modified = formatWhen(item.updated_at);
                  const signedOn = formatWhen(item.signed_at);
                  return (
                    <AvenqoCard key={item.id} className="flex min-w-0 flex-col gap-3 p-4">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <StatusBadge>{typeText(item.contract_type)}</StatusBadge>
                        <span className="text-[10px] text-slate-500">{copy.versionLabel} {item.version}</span>
                        <StatusBadge tone={item.signature_mode === "SANDBOX_PILOT" ? "gold" : documentSigned(item) ? "success" : "warning"}>
                          {statusText(item)}
                        </StatusBadge>
                        {showTestMark(item) && <StatusBadge tone="gold">{copy.testIndicator}</StatusBadge>}
                        {optional && <StatusBadge tone="info">{copy.optionalSaas}</StatusBadge>}
                      </div>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-white">{item.title}</h4>
                      <p className="text-[11px] text-slate-600 dark:text-slate-300">{copy.versionLabel} {item.version}</p>
                      {underReview(item) ? (
                        <div className="space-y-1">
                          <p className="text-[11px] font-semibold text-amber-800 dark:text-amber-200">{copy.legalReviewBanner}</p>
                          <p className="text-[11px] text-amber-900/90 dark:text-amber-100/90">{copy.legalReviewExplain}</p>
                        </div>
                      ) : (
                        <p className="text-[11px] text-slate-600 dark:text-slate-300">{copy.approvalNotFinal}</p>
                      )}
                      {modified && <p className="text-[11px] text-slate-600 dark:text-slate-300">{copy.lastModified} : {modified}</p>}
                      {signedOn && <p className="text-[11px] text-slate-600 dark:text-slate-300">{copy.signedOn} : {signedOn}</p>}
                      {item.signature_mode === "SANDBOX_PILOT" && (
                        <p className="text-[11px] text-amber-800 dark:text-amber-200">{copy.statusPilot}</p>
                      )}
                      <div className="mt-auto flex flex-wrap gap-2 border-t border-slate-200/70 pt-3 dark:border-white/10">
                        <button type="button" onClick={() => void handleOpenReview(item, "read")} className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] dark:border-white/10 dark:text-slate-100 dark:hover:bg-white/5">
                          <Eye size={13} /> {copy.consult}
                        </button>
                        <button type="button" onClick={() => void handleDownload(item.contract_type)} className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-800 hover:bg-slate-50 dark:border-white/10 dark:text-slate-100">
                          <Download size={13} /> {copy.download}
                        </button>
                        {canSignDocument(item) && (
                          <button type="button" onClick={() => void handleOpenReview(item, "sign")} className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-[#0076FF] px-3 text-xs font-semibold text-white hover:bg-[#158bff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00D4FF]">
                            {copy.sign}
                          </button>
                        )}
                      </div>
                    </AvenqoCard>
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
          <div className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-white dark:border-white/[0.08] dark:bg-[#0B132B]">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-white/[0.03] text-slate-500 border-b border-slate-200/80 dark:border-white/[0.08]">
                <tr>
                  <th className="p-3 font-bold">{copy.archiveAgreement}</th>
                  <th className="p-3 font-bold">{copy.archiveStatus}</th>
                  <th className="p-3 font-bold">{copy.archiveSignatory}</th>
                  <th className="p-3 font-bold">{copy.archiveHash}</th>
                  <th className="p-3 font-bold">{copy.archiveDownload}</th>
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
                      <StatusBadge tone={c.signature_mode === "SANDBOX_PILOT" ? "gold" : documentSigned(c) ? "success" : "warning"}>
                        {statusText(c)}
                      </StatusBadge>
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-300">
                      {c.signatory_name || copy.signatoryPending}
                      {formatWhen(c.signed_at) && <div className="text-[10px] text-slate-500">{formatWhen(c.signed_at)}</div>}
                    </td>
                    <td className="p-3 font-mono text-[10px] text-slate-500">
                      {c.sha256_hash ? `${c.sha256_hash.slice(0, 16)}...` : "—"}
                    </td>
                    <td className="p-3">
                      <button type="button" onClick={() => void handleDownload(c.contract_type)} className="inline-flex items-center gap-1 font-bold text-[#0076FF] hover:underline">
                        <Download size={13} /> PDF
                      </button>
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
              <button type="button" onClick={() => { setSelectedContract(null); setPanelMode(null); setPdfBytes(null); }} aria-label={copy.close} className="rounded-lg p-1 text-slate-500 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF]">
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto bg-slate-200 p-5 text-sm leading-relaxed text-slate-800 dark:bg-slate-800 dark:text-slate-100">
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                {copy.versionLabel} {selectedContract.version}
                {" · "}
                {underReview(selectedContract) ? copy.legalReviewBanner : copy.approvalNotFinal}
              </p>
              {!locale.toLowerCase().startsWith((selectedContract.language || "fr").toLowerCase().slice(0, 2)) && (
                <p className="rounded-lg border border-[#C4A35A]/40 bg-[#C4A35A]/10 px-3 py-2 text-xs text-[#6E5210] dark:text-[#F3DE9A]">
                  {fillContractCopy(copy.governingNotice, { language: selectedContract.language || "fr" })}
                </p>
              )}
              {pdfBytes ? (
                <ContractPdfReader
                  data={pdfBytes}
                  labels={{ loading: copy.pdfLoading, failed: copy.pdfFailed, page: copy.pdfPage, of: copy.pdfOf, zoomIn: copy.zoomIn, zoomOut: copy.zoomOut }}
                />
              ) : (
                <p className="text-xs text-amber-800">{pdfError || copy.pdfFailed}</p>
              )}
            </div>

            {panelMode === "read" ? (
              <div className="flex justify-end border-t border-slate-200 bg-white p-5 dark:border-white/[0.08] dark:bg-[#0B132B]">
                <button type="button" onClick={() => void handleDownload(selectedContract.contract_type)} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-800">
                  <Download size={13} /> {copy.download}
                </button>
              </div>
            ) : (
            <div className="p-5 border-t border-slate-200 dark:border-white/[0.08] bg-white dark:bg-[#0B132B] space-y-4">
              <p className="text-xs leading-relaxed text-slate-700 dark:text-slate-200">{copy.codeWhy}</p>
              {/* Jeton / Défi de signature anti-rejeu */}
              {!challengeId ? (
                <div className="p-3.5 rounded-xl bg-blue-50 dark:bg-[#111D3D] border border-blue-200 dark:border-blue-900 flex items-center justify-between gap-3">
                  <div className="text-xs text-blue-900 dark:text-blue-200">
                    {copy.challengePrompt}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRequestChallenge()}
                    disabled={challengeLoading}
                    className="shrink-0 px-3 py-1.5 rounded-xl bg-[#0076FF] text-white text-xs font-bold"
                  >
                    {challengeLoading ? copy.generatingCode : copy.requestCode}
                  </button>
                </div>
              ) : (
                <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-300 text-xs text-emerald-900 dark:text-emerald-200 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>{challengeStatusMessage()}</div>
                    <span className="shrink-0 text-[10px] text-slate-500">{copy.challengeTtl}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRequestChallenge()}
                    disabled={challengeLoading}
                    className="px-3 py-1.5 rounded-xl border border-emerald-400/60 text-emerald-900 dark:text-emerald-100 text-xs font-semibold"
                  >
                    {challengeLoading ? copy.generatingCode : copy.resendCode}
                  </button>
                </div>
              )}

              <form onSubmit={handleSubmitSignature} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 dark:text-slate-300 mb-1">
                      {copy.signatoryTitle} *
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
                      {copy.verificationCode} *
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
                      {copy.authorityConsent}
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
                      {copy.termsConsent}
                    </span>
                  </label>
                </div>

                <div className="flex justify-between items-center pt-3 border-t border-slate-100 dark:border-white/[0.06]">
                  <button type="button" onClick={() => void handleDownload(selectedContract.contract_type)} className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800">
                    <Download size={13} /> {copy.download}
                  </button>
                  <button
                    type="submit"
                    disabled={signSubmitting || !declaredAuthority || !consentCheckbox || !challengeId || commercialBlocked}
                    className="px-6 py-2 rounded-xl bg-[#0076FF] hover:bg-blue-600 disabled:bg-slate-300 text-white font-bold text-xs shadow-md transition-all"
                  >
                    {signSubmitting ? copy.signing : copy.signAction}
                  </button>
                </div>
              </form>
            </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

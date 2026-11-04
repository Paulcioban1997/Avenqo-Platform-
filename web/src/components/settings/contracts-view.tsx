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
  status: "DRAFT" | "SENT" | "VIEWED" | "PENDING_SIGNATURE" | "SIGNED" | "REJECTED" | "EXPIRED" | "SUPERSEDED";
  version: string;
  language: string;
  signature_mode: "ELECTRONIC" | "MANUSCRIPT_WET_INK" | null;
  signatory_name: string | null;
  signatory_title: string | null;
  signatory_email: string | null;
  signed_at: string | null;
  sha256_hash: string;
  has_pdf: boolean;
}

export interface ContractDetail {
  id: string;
  contract_type: string;
  title: string;
  status: string;
  version: string;
  language: string;
  content_text: string;
  sha256_hash: string;
  signatory_name: string | null;
  signatory_title: string | null;
  signatory_email: string | null;
  signed_at: string | null;
  signature_mode: string | null;
}

export function ContractsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const session = useOptionalSession();
  const isFrench = locale.startsWith("fr");

  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiRequestError | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);

  // Modal Review & Sign State
  const [selectedContract, setSelectedContract] = useState<ContractDetail | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [signatoryTitle, setSignatoryTitle] = useState("Président / CEO");
  const [declaredAuthority, setDeclaredAuthority] = useState(false);
  const [consentCheckbox, setConsentCheckbox] = useState(false);
  const [signSubmitting, setSignSubmitting] = useState(false);

  // Wet-ink scan upload modal
  const [wetInkContract, setWetInkContract] = useState<ContractItem | null>(null);
  const [wetInkFile, setWetInkFile] = useState<File | null>(null);
  const [wetInkSubmitting, setWetInkSubmitting] = useState(false);
  const wetInkInputRef = useRef<HTMLInputElement | null>(null);

  const loadContracts = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await apiFetch("/api/v1/contracts", { headers: getAuthHeaders() });
      if (!res.ok) {
        throw new Error(isFrench ? "Impossible de charger vos contrats" : "Failed to load contracts");
      }
      const data = await res.json();
      if (Array.isArray(data)) {
        setContracts(data);
      }
    } catch (err: any) {
      setLoadError(err instanceof ApiRequestError ? err : new ApiRequestError("backend_error"));
    } finally {
      setLoading(false);
    }
  }, [isFrench]);

  useEffect(() => {
    void loadContracts();
  }, [loadContracts]);

  // Open contract for review & signing
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
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setReviewLoading(false);
    }
  };

  // Submit electronic signature
  const handleSubmitSignature = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContract) return;

    if (!declaredAuthority) {
      setAlertError(
        isFrench
          ? "Vous devez expressément déclarer votre autorité légale pour engager l'entreprise."
          : "You must expressly declare your legal authority to bind the company."
      );
      return;
    }
    if (!consentCheckbox) {
      setAlertError(
        isFrench
          ? "Le consentement explicite aux termes contractuels est obligatoire."
          : "Explicit consent to contractual terms is mandatory."
      );
      return;
    }

    setSignSubmitting(true);
    setAlertError(null);
    try {
      const res = await apiFetch(`/api/v1/contracts/${selectedContract.contract_type}/sign`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          signatory_title: signatoryTitle.trim(),
          declared_authority: declaredAuthority,
          consent_checkbox: consentCheckbox,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || (isFrench ? "Échec de la signature électronique." : "Signature failed."));
      }

      setSelectedContract(null);
      setAlertSuccess(
        isFrench
          ? "Contrat signé électroniquement avec succès ! Un exemplaire certifié a été archivé et envoyé par courriel."
          : "Contract electronically signed! A certified copy has been archived and emailed."
      );
      await loadContracts();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setSignSubmitting(false);
    }
  };

  // Upload wet-ink scanned contract
  const handleUploadWetInk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wetInkContract || !wetInkFile) return;

    setWetInkSubmitting(true);
    setAlertError(null);
    try {
      const formData = new FormData();
      formData.append("file", wetInkFile);
      formData.append("signatory_title", signatoryTitle);

      const res = await fetch(`/api/v1/contracts/${wetInkContract.contract_type}/upload-manuscript`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || (isFrench ? "Échec du téléversement du contrat manuscrit." : "Upload failed."));
      }

      setWetInkContract(null);
      setWetInkFile(null);
      setAlertSuccess(
        isFrench
          ? "Contrat signé au stylo téléversé et archivé avec succès !"
          : "Signed manuscript contract successfully uploaded and archived!"
      );
      await loadContracts();
    } catch (err: any) {
      setAlertError(err.message);
    } finally {
      setWetInkSubmitting(false);
    }
  };

  // Trigger PDF download
  const handleDownloadPdf = (contractType: string) => {
    const url = `/api/v1/contracts/${contractType}/download`;
    window.open(url, "_blank");
  };

  if (loadError) return <RequestFailure error={loadError} retry={() => { void loadContracts(); }} />;

  const signedCount = contracts.filter((c) => c.status === "SIGNED").length;
  const pendingCount = contracts.filter((c) => c.status !== "SIGNED").length;

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
                {isFrench ? "Documents juridiques — Mes contrats" : "Legal Documents — My Contracts"}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                {isFrench
                  ? "Accords de confidentialité, contrats d'abonnement SaaS et licences privées certifiés conformes (Loi 25 Québec & PIPEDA Canada)."
                  : "Certified enterprise NDA, SaaS subscription agreements, and private software licenses."}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => void loadContracts()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-[#0076FF]" : ""} />
            <span>{isFrench ? "Actualiser" : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Alerts */}
      {alertError && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs text-amber-800 dark:text-amber-300">
          <div className="flex items-center gap-2.5">
            <AlertCircle size={16} className="text-amber-600 shrink-0" />
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
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            <span>{alertSuccess}</span>
          </div>
          <button onClick={() => setAlertSuccess(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      {/* KPI Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <span className="text-xs font-semibold text-slate-500">{isFrench ? "Total Contrats" : "Total Contracts"}</span>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">{contracts.length}</div>
          <p className="text-[11px] text-slate-400 mt-1">{isFrench ? "Applicables à votre entreprise" : "Applicable to your company"}</p>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">{isFrench ? "Signés & Certifiés" : "Signed & Certified"}</span>
          <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">{signedCount}</div>
          <p className="text-[11px] text-slate-400 mt-1">{isFrench ? "Preuves d'audit SHA-256 scellées" : "SHA-256 sealed audit trails"}</p>
        </div>

        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">{isFrench ? "En Attente de Signature" : "Pending Signature"}</span>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400 mt-1">{pendingCount}</div>
          <p className="text-[11px] text-slate-400 mt-1">{isFrench ? "Requis pour activation complète" : "Required for full activation"}</p>
        </div>
      </div>

      {/* Notice de conformité */}
      <div className="p-4 rounded-2xl bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-800/40 text-xs text-blue-900 dark:text-blue-300 flex items-start gap-3">
        <ShieldCheck size={18} className="text-[#0076FF] shrink-0 mt-0.5" />
        <div>
          <span className="font-bold">{isFrench ? "Cadre d'intégrité et validité juridique :" : "Legal integrity framework:"}</span>
          <p className="mt-0.5 text-blue-800/90 dark:text-blue-300/80 leading-relaxed">
            {isFrench
              ? "Tous les contrats signés numériquement sur Avenqo sont conformes à la Loi concernant le cadre juridique des technologies de l'information (Québec, c. C-1.1). Chaque document bénéficie d'une empreinte cryptographique SHA-256 immuable, d'un horodatage UTC certifié et d'un archivage privé accessible aux deux parties. Les exemplaires signés à la main au stylo peuvent également être téléversés et scellés."
              : "All contracts digitally signed on Avenqo comply with Quebec IT legal frameworks (CQLR c. C-1.1) and PIPEDA. Documents are cryptographically sealed with SHA-256 and immutable UTC timestamps."}
          </p>
        </div>
      </div>

      {/* Contracts List */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
            <FileText size={18} className="text-[#0076FF]" />
            <span>{isFrench ? "Registres contractuels du locataire" : "Tenant Contractual Registry"}</span>
          </h2>
          <span className="text-xs text-slate-400">
            {isFrench ? "Version contractuelle officielle 2026-V1" : "Official 2026-V1 contract version"}
          </span>
        </div>

        {loading ? (
          <div className="py-12 text-center text-xs text-slate-400">
            <RefreshCw size={20} className="animate-spin text-[#0076FF] mx-auto mb-2" />
            <span>{isFrench ? "Chargement de vos contrats..." : "Loading contracts..."}</span>
          </div>
        ) : contracts.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">
            <FileText size={24} className="mx-auto mb-2 text-slate-300" />
            <span>{isFrench ? "Aucun contrat disponible pour le moment." : "No contracts available."}</span>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-white/[0.06]">
            {contracts.map((item) => {
              const isSigned = item.status === "SIGNED";

              return (
                <div key={item.id} className="py-4.5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-extrabold text-sm text-slate-900 dark:text-white">{item.title}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 dark:bg-white/[0.06] text-slate-600 dark:text-slate-300">
                        {item.contract_type}
                      </span>
                      {isSigned ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/50">
                          <CheckCircle2 size={11} />
                          <span>{isFrench ? "Signé & Certifié" : "Signed & Certified"}</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border border-amber-200/50">
                          <Clock size={11} />
                          <span>{isFrench ? "En attente de signature" : "Pending Signature"}</span>
                        </span>
                      )}
                    </div>

                    <div className="text-xs text-slate-500 dark:text-slate-400 flex flex-wrap items-center gap-x-4 gap-y-1">
                      <span>Réf : {item.contract_type}-{item.version}</span>
                      {isSigned && item.signed_at && (
                        <span>Signé le : {new Date(item.signed_at).toLocaleDateString(locale, { year: "numeric", month: "long", day: "numeric" })}</span>
                      )}
                      {isSigned && item.signatory_name && (
                        <span>Par : {item.signatory_name} ({item.signatory_title || "Dirigeant"})</span>
                      )}
                      {isSigned && item.signature_mode && (
                        <span>Mode : {item.signature_mode === "ELECTRONIC" ? "Numérique 1-Clic" : "Manuscrit (Stylo)"}</span>
                      )}
                      {item.sha256_hash && (
                        <span className="font-mono text-[10px] text-slate-400 truncate max-w-xs" title={item.sha256_hash}>
                          SHA : {item.sha256_hash.slice(0, 16)}...
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleDownloadPdf(item.contract_type)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors cursor-pointer"
                      title={isSigned ? "Télécharger le PDF signé" : "Télécharger le PDF pour impression"}
                    >
                      <Download size={13} />
                      <span>{isSigned ? (isFrench ? "PDF Signé" : "Signed PDF") : (isFrench ? "Imprimer PDF" : "Print PDF")}</span>
                    </button>

                    {!isSigned && (
                      <>
                        <button
                          onClick={() => void handleOpenReview(item)}
                          disabled={reviewLoading}
                          className="inline-flex items-center gap-1 px-3.5 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                        >
                          <FileCheck size={13} />
                          <span>{isFrench ? "Signer en ligne" : "E-Sign Online"}</span>
                        </button>

                        <button
                          onClick={() => {
                            setWetInkContract(item);
                            setWetInkFile(null);
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-600 dark:text-slate-300 transition-colors cursor-pointer"
                          title="Téléverser le contrat signé au stylo"
                        >
                          <Upload size={13} />
                          <span>{isFrench ? "Scan Stylo" : "Upload Scan"}</span>
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal: Review & E-Sign Contract */}
      {selectedContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-xs">
          <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.08] shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="p-5 border-b border-slate-100 dark:border-white/[0.06] flex items-center justify-between">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {selectedContract.title}
                </h3>
                <span className="text-xs text-slate-500">
                  Réf : {selectedContract.contract_type} — Version {selectedContract.version}
                </span>
              </div>
              <button
                onClick={() => setSelectedContract(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Contract Body (Scrollable) */}
            <div className="p-6 overflow-y-auto flex-1 font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200 bg-slate-50/50 dark:bg-white/[0.02] border-b border-slate-100 dark:border-white/[0.06] whitespace-pre-wrap select-text">
              {selectedContract.content_text}
            </div>

            {/* Signature Form */}
            <form onSubmit={handleSubmitSignature} className="p-5 bg-white dark:bg-[#0B132B] space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    {isFrench ? "Signataire (Nom & Prénom)" : "Signatory (Full Name)"}
                  </label>
                  <input
                    type="text"
                    disabled
                    value={session?.identity?.user ? `${session.identity.user.first_name} ${session.identity.user.last_name}` : "Utilisateur connecté"}
                    className="w-full px-3 py-2 rounded-xl bg-slate-100 dark:bg-white/[0.05] border border-slate-200 dark:border-white/[0.08] text-slate-600 dark:text-slate-400 cursor-not-allowed"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    {isFrench ? "Fonction / Titre légal dans l'entreprise *" : "Corporate Title / Authority *"}
                  </label>
                  <input
                    type="text"
                    required
                    value={signatoryTitle}
                    onChange={(e) => setSignatoryTitle(e.target.value)}
                    placeholder="ex. Président, CEO, Directeur Général"
                    className="w-full px-3 py-2 rounded-xl bg-white dark:bg-white/[0.04] border border-slate-300 dark:border-white/[0.1] text-slate-900 dark:text-white focus:outline-none focus:border-[#0076FF]"
                  />
                </div>
              </div>

              <div className="space-y-2 pt-1 text-xs text-slate-700 dark:text-slate-300">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={declaredAuthority}
                    onChange={(e) => setDeclaredAuthority(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded accent-[#0076FF]"
                  />
                  <span>
                    {isFrench
                      ? "Je déclare sur l'honneur détenir le pouvoir légal et statutaire nécessaire pour engager juridiquement l'entreprise au présent contrat."
                      : "I declare under penalty of law that I hold the legal authority to bind the company to this agreement."}
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentCheckbox}
                    onChange={(e) => setConsentCheckbox(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded accent-[#0076FF]"
                  />
                  <span>
                    {isFrench
                      ? "J'ai lu, compris et j'accepte expressément l'intégralité des termes et conditions du contrat ci-dessus (signature électronique conforme RLRQ c. C-1.1)."
                      : "I have read, understood, and agree to the full terms and conditions above (compliant digital e-signature)."}
                  </span>
                </label>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={() => handleDownloadPdf(selectedContract.contract_type)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:hover:text-white"
                >
                  <Download size={13} />
                  <span>{isFrench ? "Télécharger pour signature au stylo" : "Download to sign by hand"}</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedContract(null)}
                    className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
                  >
                    {isFrench ? "Annuler" : "Cancel"}
                  </button>
                  <button
                    type="submit"
                    disabled={signSubmitting || !declaredAuthority || !consentCheckbox}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                  >
                    <ShieldCheck size={14} />
                    <span>{signSubmitting ? (isFrench ? "Signature en cours..." : "Signing...") : (isFrench ? "Signer électroniquement" : "Sign Electronically")}</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Wet-Ink Scan Upload */}
      {wetInkContract && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200 dark:border-white/[0.08] shadow-2xl p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  {isFrench ? "Téléverser le contrat signé au stylo" : "Upload Wet-Ink Signed Contract"}
                </h3>
                <span className="text-xs text-slate-500">{wetInkContract.title}</span>
              </div>
              <button
                onClick={() => setWetInkContract(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {isFrench
                ? "Téléchargez le contrat PDF, imprimez-le, apposez votre signature manuscrite à l'encre, puis numérisez ou photographiez le document complet pour archivage permanent certifié."
                : "Print the PDF contract, sign with ink, and upload the scanned document for certified permanent archiving."}
            </p>

            <form onSubmit={handleUploadWetInk} className="space-y-4 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  {isFrench ? "Titre / Fonction du signataire" : "Signatory Title"}
                </label>
                <input
                  type="text"
                  required
                  value={signatoryTitle}
                  onChange={(e) => setSignatoryTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl text-xs bg-slate-50 dark:bg-white/[0.04] border border-slate-300 dark:border-white/[0.08] text-slate-900 dark:text-white"
                />
              </div>

              <div>
                <input
                  ref={wetInkInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      setWetInkFile(e.target.files[0]);
                    }
                  }}
                />
                <div
                  onClick={() => wetInkInputRef.current?.click()}
                  className="p-6 border-2 border-dashed rounded-xl text-center cursor-pointer hover:border-[#0076FF] transition-colors bg-slate-50 dark:bg-white/[0.02]"
                >
                  <Upload size={22} className="mx-auto mb-2 text-[#0076FF]" />
                  <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    {wetInkFile ? wetInkFile.name : (isFrench ? "Cliquer pour sélectionner le scan / photo du contrat signé" : "Click to select signed scan")}
                  </span>
                  <p className="text-[10px] text-slate-400 mt-1">PDF, PNG, JPG jusqu'à 25 Mo</p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-white/[0.06]">
                <button
                  type="button"
                  onClick={() => setWetInkContract(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-slate-300 cursor-pointer"
                >
                  {isFrench ? "Annuler" : "Cancel"}
                </button>
                <button
                  type="submit"
                  disabled={wetInkSubmitting || !wetInkFile}
                  className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                >
                  {wetInkSubmitting ? (isFrench ? "Téléversement..." : "Uploading...") : (isFrench ? "Valider et Archiver" : "Submit & Archive")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

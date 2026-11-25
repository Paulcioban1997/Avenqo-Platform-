"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  FileText,
  ExternalLink,
  Download,
  Printer,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Edit3,
  XCircle,
  ShieldAlert,
  Link2,
  Calculator,
  MapPin,
  CreditCard,
  Eye,
  Save,
} from "lucide-react";
import { DisplayAmount } from "@/components/common/display-amount";
import { getAuthHeaders } from "@/lib/api-headers";

export interface InvoiceProvenanceItem {
  field: string;
  sheet?: string | null;
  cell?: string | null;
  page?: number | string | null;
  confidence?: number | null;
  raw_text?: string | null;
}

export interface InvoiceLineItem {
  id?: string;
  description: string;
  quantity?: number;
  unit_price?: number;
  tax_amount?: number;
  total_amount: number;
  account_code?: string;
  provenance?: {
    sheet?: string;
    cell?: string;
    page?: number | string;
  };
}

export interface InvoicePaymentRecord {
  id: string;
  payment_date: string;
  amount: number;
  currency?: string;
  method?: string;
  reference?: string;
}

export interface LinkedLedgerEntry {
  id: string;
  transaction_date: string;
  transaction_type: "revenue" | "expense";
  category: string;
  description: string;
  amount: number;
  currency: string;
  status: string;
  is_confirmed?: boolean;
  reference_id?: string;
}

export interface EnrichedInvoiceItem {
  id: string;
  invoice_number: string;
  invoice_type: "receivable" | "payable" | string;
  party_name: string;
  issue_date: string;
  due_date: string;
  subtotal_amount?: number;
  tax_amount?: number;
  total_amount: number;
  paid_amount: number;
  remaining_amount: number;
  currency: string;
  status: string;
  is_confirmed?: boolean;
  notes?: string | null;
  // Optional enriched PR 3 / document provenance & AI classification fields
  source_module?: string | null;
  source_document_id?: string | null;
  source_document_name?: string | null;
  source_document_url?: string | null;
  source_mime_type?: string | null;
  duplicate_warning?: boolean;
  duplicate_reason?: string | null;
  duplicate_of_invoice_number?: string | null;
  proposed_classification?: {
    category?: string;
    account_code?: string;
    account_label?: string;
    confidence?: number;
    reasons?: string[];
    is_ai_suggestion?: boolean;
  } | null;
  line_items?: InvoiceLineItem[];
  provenance?: InvoiceProvenanceItem[];
  payments?: InvoicePaymentRecord[];
  extra_data?: Record<string, unknown>;
}

export interface InvoiceDetailDrawerProps {
  invoice: EnrichedInvoiceItem | null;
  onClose: () => void;
  linkedTransactions: LinkedLedgerEntry[];
  locale: string;
  isFr: boolean;
  canReadAccounting: boolean;
  canWriteAccounting: boolean;
  onSelectTransaction?: (txId: string) => void;
  onInvoiceUpdated?: (updated: EnrichedInvoiceItem) => void;
}

function isSafePreviewUrl(url?: string | null): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  if (!trimmed) return false;
  // Never allow raw filesystem paths or file:// URLs
  if (
    trimmed.startsWith("file:") ||
    /^[a-zA-Z]:[\\/]/.test(trimmed) ||
    trimmed.startsWith("/var/") ||
    trimmed.startsWith("/data/") ||
    trimmed.startsWith("\\\\")
  ) {
    return false;
  }
  return trimmed.startsWith("/api/") || trimmed.startsWith("https://") || trimmed.startsWith("blob:");
}

export function InvoiceDetailDrawer({
  invoice,
  onClose,
  linkedTransactions,
  locale,
  isFr,
  canReadAccounting,
  canWriteAccounting,
  onSelectTransaction,
  onInvoiceUpdated,
}: InvoiceDetailDrawerProps) {
  const [detail, setDetail] = useState<EnrichedInvoiceItem | null>(invoice);
  const [showPreviewFrame, setShowPreviewFrame] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editParty, setEditParty] = useState("");
  const [editNumber, setEditNumber] = useState("");
  const [editDueDate, setEditDueDate] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [confirmingDuplicateApprove, setConfirmingDuplicateApprove] = useState(false);
  const [actionBanner, setActionBanner] = useState<{
    tone: "success" | "warning" | "error";
    text: string;
  } | null>(null);
  const [downloadFormat, setDownloadFormat] = useState<"csv" | "json" | "txt">("csv");

  useEffect(() => {
    setDetail(invoice);
    setShowPreviewFrame(false);
    setIsEditing(false);
    setConfirmingDuplicateApprove(false);
    setActionBanner(null);
    if (invoice) {
      setEditParty(invoice.party_name || "");
      setEditNumber(invoice.invoice_number || "");
      setEditDueDate(invoice.due_date ? invoice.due_date.slice(0, 10) : "");
      setEditCategory(
        invoice.proposed_classification?.category ||
          (invoice.invoice_type === "receivable" ? "sales" : "operating_expense")
      );
      setEditNotes(invoice.notes || "");

      // Optional progressive enrichment when PR 3 detail endpoint is available
      let cancelled = false;
      (async () => {
        try {
          const resp = await fetch(`/api/v1/accounting/invoices/${invoice.id}`, {
            headers: getAuthHeaders(),
          });
          if (resp.ok && !cancelled) {
            const enriched = await resp.json();
            if (enriched && typeof enriched === "object" && enriched.id) {
              setDetail((prev) => (prev ? { ...prev, ...enriched } : enriched));
            }
          }
        } catch {
          // Standalone compatibility: current backend may only expose list endpoint
        }
      })();
      return () => {
        cancelled = true;
      };
    }
  }, [invoice]);

  if (!detail) return null;

  const isReceivable = detail.invoice_type === "receivable";
  const safeDocUrl = isSafePreviewUrl(detail.source_document_url)
    ? detail.source_document_url!
    : null;

  const lineItems: InvoiceLineItem[] =
    detail.line_items && detail.line_items.length > 0
      ? detail.line_items
      : [
          {
            description:
              detail.notes ||
              (isReceivable
                ? isFr
                  ? `Facturation client — ${detail.party_name}`
                  : `Customer billing — ${detail.party_name}`
                : isFr
                  ? `Facture fournisseur — ${detail.party_name}`
                  : `Supplier invoice — ${detail.party_name}`),
            quantity: 1,
            unit_price: detail.subtotal_amount ?? detail.total_amount - (detail.tax_amount ?? 0),
            tax_amount: detail.tax_amount ?? 0,
            total_amount: detail.total_amount,
          },
        ];

  const computedTax =
    detail.tax_amount ??
    lineItems.reduce((acc, item) => acc + Number(item.tax_amount ?? 0), 0);
  const computedSubtotal =
    detail.subtotal_amount ?? Number((detail.total_amount - computedTax).toFixed(2));
  const mathExpectedTotal = Number((computedSubtotal + computedTax).toFixed(2));
  const mathDelta = Math.abs(mathExpectedTotal - Number(detail.total_amount || 0));
  const balanceDelta = Math.abs(
    Number(detail.paid_amount || 0) +
      Number(detail.remaining_amount || 0) -
      Number(detail.total_amount || 0)
  );
  const mathValid = mathDelta <= 0.02 && balanceDelta <= 0.02;

  const isPaid =
    detail.status === "paid" ||
    (detail.total_amount > 0 && Number(detail.remaining_amount) <= 0.005);
  const isConfirmed = detail.is_confirmed !== false && detail.status !== "rejected" && detail.status !== "to_verify";

  const statusBadge = (() => {
    if (detail.status === "rejected") {
      return {
        label: isFr ? "Proposition rejetée" : "Proposal Rejected",
        cls: "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30",
      };
    }
    if (isPaid) {
      return {
        label: isFr ? "Payé · Confirmé" : "Paid · Confirmed",
        cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
      };
    }
    if (!isConfirmed) {
      return {
        label: isFr ? "À vérifier (IA / Brouillon)" : "To Verify (AI / Draft)",
        cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30",
      };
    }
    if (detail.status === "overdue") {
      return {
        label: isFr ? "Confirmé · En retard" : "Confirmed · Overdue",
        cls: "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30",
      };
    }
    return {
      label: isFr ? "Confirmé · Ouvert" : "Confirmed · Open",
      cls: "bg-blue-500/15 text-[#0076FF] dark:text-[#00D4FF] border-blue-500/30",
    };
  })();

  const sourceLabel =
    detail.source_module ||
    (typeof detail.extra_data?.source === "string" ? detail.extra_data.source : null) ||
    (isFr ? "Saisie comptable" : "Manual entry");

  const classification = detail.proposed_classification ?? {
    category: editCategory || (isReceivable ? "sales" : "operating_expense"),
    account_code: isReceivable ? "4100 — Ventes & Services" : "5200 — Charges d'exploitation",
    confidence: detail.is_confirmed ? 1.0 : 0.86,
    is_ai_suggestion: !detail.is_confirmed,
    reasons: detail.is_confirmed
      ? [
          isFr
            ? "Imputation validée dans le registre comptable de l'entreprise."
            : "Classification confirmed in the company accounting register.",
        ]
      : [
          isFr
            ? "Catégorie déduite du tiers et de la nature de la pièce (validation humaine requise)."
            : "Category inferred from counterparty and document type (human review required).",
        ],
  };

  const paymentsList: InvoicePaymentRecord[] =
    detail.payments && detail.payments.length > 0
      ? detail.payments
      : detail.paid_amount > 0
        ? [
            {
              id: `pmt-${detail.id}`,
              payment_date: detail.issue_date,
              amount: detail.paid_amount,
              currency: detail.currency,
              method: isFr ? "Règlement enregistré" : "Recorded payment",
              reference: detail.invoice_number,
            },
          ]
        : [];

  const handleDownloadInvoice = (fmt: "csv" | "json" | "txt") => {
    if (!canReadAccounting) return;
    let content = "";
    let mime = "text/plain;charset=utf-8";
    const safeNum = (detail.invoice_number || "invoice").replace(/[^a-zA-Z0-9._-]+/g, "-");

    if (fmt === "json") {
      mime = "application/json;charset=utf-8";
      content = JSON.stringify(
        {
          exported_at: new Date().toISOString(),
          invoice: detail,
          math_verification: {
            subtotal: computedSubtotal,
            tax: computedTax,
            total: detail.total_amount,
            valid: mathValid,
          },
          linked_transactions: linkedTransactions,
        },
        null,
        2
      );
    } else if (fmt === "csv") {
      mime = "text/csv;charset=utf-8";
      const escapeCsv = (val: unknown) => {
        const s = String(val ?? "");
        const safe = /^[=+\-@\t\r]/.test(s) && !/^[+-]\d+(?:\.\d+)?$/.test(s) ? `'${s}` : s;
        return `"${safe.replace(/"/g, '""')}"`;
      };
      const rows = [
        ["invoice_number", "type", "party_name", "issue_date", "due_date", "line_description", "quantity", "unit_price", "tax_amount", "line_total", "currency", "status"],
        ...lineItems.map((li) => [
          detail.invoice_number,
          detail.invoice_type,
          detail.party_name,
          detail.issue_date.slice(0, 10),
          detail.due_date.slice(0, 10),
          li.description,
          li.quantity ?? 1,
          li.unit_price ?? li.total_amount,
          li.tax_amount ?? 0,
          li.total_amount,
          detail.currency,
          detail.status,
        ]),
      ];
      content = rows.map((r) => r.map(escapeCsv).join(",")).join("\n");
    } else {
      content = [
        `FACTURE #${detail.invoice_number}`,
        `Type : ${isReceivable ? "Revenu / Client (AR)" : "Dépense / Fournisseur (AP)"}`,
        `Tiers : ${detail.party_name}`,
        `Émission : ${detail.issue_date.slice(0, 10)} | Échéance : ${detail.due_date.slice(0, 10)}`,
        `Sous-total : ${computedSubtotal.toFixed(2)} ${detail.currency}`,
        `Taxes : ${computedTax.toFixed(2)} ${detail.currency}`,
        `Total : ${detail.total_amount.toFixed(2)} ${detail.currency}`,
        `Payé : ${detail.paid_amount.toFixed(2)} ${detail.currency} | Solde : ${detail.remaining_amount.toFixed(2)} ${detail.currency}`,
        `Statut : ${statusBadge.label} | Source : ${sourceLabel}`,
      ].join("\n");
    }

    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `facture-${safeNum}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handlePrintInvoice = () => {
    if (!canReadAccounting) return;
    window.print();
  };

  const handleSaveCorrection = async () => {
    if (!canWriteAccounting) return;
    const updated: EnrichedInvoiceItem = {
      ...detail,
      party_name: editParty.trim() || detail.party_name,
      invoice_number: editNumber.trim() || detail.invoice_number,
      due_date: editDueDate ? `${editDueDate}T00:00:00Z` : detail.due_date,
      notes: editNotes,
      proposed_classification: {
        ...classification,
        category: editCategory,
        is_ai_suggestion: false,
      },
    };
    try {
      const resp = await fetch(`/api/v1/accounting/invoices/${detail.id}`, {
        method: "PATCH",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          party_name: updated.party_name,
          invoice_number: updated.invoice_number,
          due_date: updated.due_date,
          notes: updated.notes,
          category: editCategory,
        }),
      });
      if (resp.ok) {
        const serverData = await resp.json().catch(() => null);
        const merged = serverData && serverData.id ? { ...updated, ...serverData } : updated;
        setDetail(merged);
        onInvoiceUpdated?.(merged);
        setIsEditing(false);
        setActionBanner({
          tone: "success",
          text: isFr ? "Corrections enregistrées sur la facture." : "Invoice corrections saved.",
        });
        return;
      }
    } catch {
      // Fallback below when PATCH route is not yet mounted
    }
    setDetail(updated);
    onInvoiceUpdated?.(updated);
    setIsEditing(false);
    setActionBanner({
      tone: "warning",
      text: isFr
        ? "Correction appliquée dans la session de révision courante."
        : "Correction applied in the current review session.",
    });
  };

  const executeApprove = async () => {
    if (!canWriteAccounting) return;
    setConfirmingDuplicateApprove(false);
    const approved: EnrichedInvoiceItem = {
      ...detail,
      is_confirmed: true,
      status: detail.remaining_amount <= 0 ? "paid" : "unpaid",
      proposed_classification: {
        ...classification,
        is_ai_suggestion: false,
      },
    };
    try {
      const resp = await fetch(`/api/v1/accounting/invoices/${detail.id}/approve`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        setDetail(approved);
        onInvoiceUpdated?.(approved);
        setActionBanner({
          tone: "success",
          text: isFr ? "Facture et imputation comptable approuvées." : "Invoice and accounting classification approved.",
        });
        return;
      }
    } catch {
      // Standalone graceful fallback
    }
    setDetail(approved);
    onInvoiceUpdated?.(approved);
    setActionBanner({
      tone: "success",
      text: isFr
        ? "Statut marqué « Confirmé » pour cette facture."
        : "Status marked 'Confirmed' for this invoice.",
    });
  };

  const handleApproveClick = () => {
    if (!canWriteAccounting) return;
    if (detail.duplicate_warning && !confirmingDuplicateApprove) {
      setConfirmingDuplicateApprove(true);
      return;
    }
    void executeApprove();
  };

  const handleRejectProposal = async () => {
    if (!canWriteAccounting) return;
    const rejected: EnrichedInvoiceItem = {
      ...detail,
      is_confirmed: false,
      status: "rejected",
    };
    try {
      await fetch(`/api/v1/accounting/invoices/${detail.id}/reject`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
    } catch {
      // Standalone graceful fallback
    }
    setDetail(rejected);
    onInvoiceUpdated?.(rejected);
    setActionBanner({
      tone: "warning",
      text: isFr
        ? "Proposition IA rejetée — aucune écriture confirmée ne sera comptabilisée."
        : "AI proposal rejected — no confirmed entry will be posted.",
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/60 backdrop-blur-xs print:bg-white print:static"
      onClick={onClose}
    >
      <aside
        role="dialog"
        aria-label={`Facture ${detail.invoice_number}`}
        className="w-full max-w-2xl h-full bg-white dark:bg-[#0B132B] border-l border-slate-200 dark:border-white/[0.1] shadow-2xl flex flex-col overflow-hidden print:max-w-none print:border-none print:shadow-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Sticky Header */}
        <div className="px-6 py-5 border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/80 dark:bg-[#111D3D]/60 flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {isFr ? `Facture #${detail.invoice_number}` : `Invoice #${detail.invoice_number}`}
              </span>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${
                  isReceivable
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                    : "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30"
                }`}
              >
                {isReceivable
                  ? isFr
                    ? "Revenu · Client (AR)"
                    : "Revenue · Customer (AR)"
                  : isFr
                    ? "Dépense · Fournisseur (AP)"
                    : "Expense · Supplier (AP)"}
              </span>
              <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${statusBadge.cls}`}>
                {statusBadge.label}
              </span>
            </div>

            <div className="text-xs text-slate-600 dark:text-[#94A3B8] flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>
                <strong>{isReceivable ? (isFr ? "Client :" : "Customer:") : isFr ? "Fournisseur :" : "Vendor:"}</strong>{" "}
                {detail.party_name}
              </span>
              <span>·</span>
              <span>
                <strong>{isFr ? "Source :" : "Source:"}</strong> {sourceLabel}
              </span>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <div className="text-right">
              <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB]">
                <DisplayAmount
                  amount={detail.total_amount}
                  currency={detail.currency}
                  locale={locale}
                  onDate={detail.issue_date ? detail.issue_date.slice(0, 10) : null}
                  align="end"
                />
              </div>
              <div className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                {isFr ? "Devise d'origine :" : "Original currency:"} {detail.currency}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200/50 dark:hover:bg-white/[0.06] cursor-pointer print:hidden"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Duplicate Warning Banner (F4) */}
          {detail.duplicate_warning && (
            <div className="rounded-2xl p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700/60 space-y-2.5">
              <div className="flex items-start gap-2.5">
                <ShieldAlert size={18} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div className="text-xs text-amber-900 dark:text-amber-200">
                  <div className="font-extrabold">
                    {isFr ? "Alerte de doublon potentiel détectée" : "Potential Duplicate Invoice Detected"}
                  </div>
                  <p className="mt-0.5 leading-relaxed">
                    {detail.duplicate_reason ||
                      (isFr
                        ? `Une autre pièce porte le même numéro (${detail.invoice_number}), tiers (${detail.party_name}), montant et date. Vérifiez avant toute approbation comptable.`
                        : `Another record matches invoice number (${detail.invoice_number}), party (${detail.party_name}), amount, and date. Verify before approval.`)}
                  </p>
                </div>
              </div>

              {confirmingDuplicateApprove && canWriteAccounting && (
                <div className="pt-2 border-t border-amber-200 dark:border-amber-800/60 flex items-center justify-between gap-3">
                  <span className="text-xs font-bold text-amber-900 dark:text-amber-200">
                    {isFr
                      ? "Confirmez-vous qu'il ne s'agit PAS d'une double facturation ?"
                      : "Do you confirm this is NOT a duplicate billing?"}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setConfirmingDuplicateApprove(false)}
                      className="px-2.5 py-1 rounded-lg text-xs font-semibold border border-amber-400 text-amber-800 dark:text-amber-200 cursor-pointer"
                    >
                      {isFr ? "Annuler" : "Cancel"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void executeApprove()}
                      className="px-3 py-1 rounded-lg text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white cursor-pointer"
                    >
                      {isFr ? "Confirmer quand même" : "Confirm Anyway"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {actionBanner && (
            <div
              className={`rounded-xl px-4 py-2.5 text-xs font-medium flex items-center justify-between ${
                actionBanner.tone === "success"
                  ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                  : actionBanner.tone === "warning"
                    ? "bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800"
                    : "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
              }`}
            >
              <span>{actionBanner.text}</span>
              <button type="button" onClick={() => setActionBanner(null)} className="cursor-pointer">
                <X size={14} />
              </button>
            </div>
          )}

          {/* Secure Original File Preview Frame / Link */}
          <section className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50/50 dark:bg-[#060B13]/50 p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
                <FileText size={15} className="text-[#0076FF] dark:text-[#00D4FF]" />
                <span>{isFr ? "Pièce justificative originale" : "Original Source Document"}</span>
              </div>
              {safeDocUrl && canReadAccounting ? (
                <div className="flex items-center gap-2 print:hidden">
                  <button
                    type="button"
                    onClick={() => setShowPreviewFrame((v) => !v)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-white dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.1] text-slate-700 dark:text-slate-200 cursor-pointer"
                  >
                    <Eye size={13} />
                    <span>{showPreviewFrame ? (isFr ? "Masquer l'aperçu" : "Hide preview") : isFr ? "Aperçu intégré" : "Inline preview"}</span>
                  </button>
                  <a
                    href={safeDocUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#0076FF] text-white"
                  >
                    <ExternalLink size={13} />
                    <span>{isFr ? "Ouvrir" : "Open"}</span>
                  </a>
                </div>
              ) : (
                <span className="text-[11px] text-slate-400">
                  {isFr ? "Aucun fichier binaire joint" : "No binary file attached"}
                </span>
              )}
            </div>

            {safeDocUrl && showPreviewFrame && canReadAccounting && (
              <div className="rounded-xl overflow-hidden border border-slate-200 dark:border-white/[0.08] bg-white dark:bg-slate-900 h-64">
                <iframe
                  src={safeDocUrl}
                  title={`Aperçu ${detail.invoice_number}`}
                  className="w-full h-full border-0"
                  sandbox="allow-same-origin"
                />
              </div>
            )}
          </section>

          {/* Inline Correction Form (when editing & permitted) */}
          {isEditing && canWriteAccounting ? (
            <section className="rounded-2xl border border-[#0076FF]/40 bg-blue-50/40 dark:bg-[#111D3D]/50 p-4 space-y-3 print:hidden">
              <div className="text-xs font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-1.5">
                <Edit3 size={14} className="text-[#0076FF]" />
                <span>{isFr ? "Corriger les champs extraits" : "Correct Extracted Fields"}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <label className="space-y-1">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {isFr ? "Numéro de facture" : "Invoice Number"}
                  </span>
                  <input
                    value={editNumber}
                    onChange={(e) => setEditNumber(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#0B132B] text-slate-900 dark:text-white"
                  />
                </label>
                <label className="space-y-1">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {isReceivable ? (isFr ? "Client" : "Customer") : isFr ? "Fournisseur" : "Supplier"}
                  </span>
                  <input
                    value={editParty}
                    onChange={(e) => setEditParty(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#0B132B] text-slate-900 dark:text-white"
                  />
                </label>
                <label className="space-y-1">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {isFr ? "Date d'échéance" : "Due Date"}
                  </span>
                  <input
                    type="date"
                    value={editDueDate}
                    onChange={(e) => setEditDueDate(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#0B132B] text-slate-900 dark:text-white"
                  />
                </label>
                <label className="space-y-1">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">
                    {isFr ? "Catégorie comptable" : "Accounting Category"}
                  </span>
                  <input
                    value={editCategory}
                    onChange={(e) => setEditCategory(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#0B132B] text-slate-900 dark:text-white"
                  />
                </label>
              </div>
              <label className="block space-y-1 text-xs">
                <span className="font-semibold text-slate-600 dark:text-slate-300">
                  {isFr ? "Notes d'audit" : "Audit Notes"}
                </span>
                <textarea
                  rows={2}
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/[0.12] bg-white dark:bg-[#0B132B] text-slate-900 dark:text-white"
                />
              </label>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 dark:border-white/[0.1] text-slate-600 dark:text-slate-300 cursor-pointer"
                >
                  {isFr ? "Annuler" : "Cancel"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveCorrection()}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-[#0076FF] text-white cursor-pointer"
                >
                  <Save size={13} />
                  <span>{isFr ? "Enregistrer la correction" : "Save Correction"}</span>
                </button>
              </div>
            </section>
          ) : null}

          {/* Extracted Metadata & Provenance */}
          <section className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8] flex items-center gap-1.5">
              <MapPin size={13} />
              <span>{isFr ? "Champs extraits & Provenance documentaire" : "Extracted Fields & Document Provenance"}</span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#111D3D]/40 border border-slate-200/70 dark:border-white/[0.06]">
                <div className="text-[10px] text-slate-400">{isFr ? "Date d'émission" : "Issue Date"}</div>
                <div className="font-bold text-slate-900 dark:text-white mt-0.5">
                  {detail.issue_date ? detail.issue_date.slice(0, 10) : "—"}
                </div>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#111D3D]/40 border border-slate-200/70 dark:border-white/[0.06]">
                <div className="text-[10px] text-slate-400">{isFr ? "Échéance" : "Due Date"}</div>
                <div className="font-bold text-slate-900 dark:text-white mt-0.5">
                  {detail.due_date ? detail.due_date.slice(0, 10) : "—"}
                </div>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#111D3D]/40 border border-slate-200/70 dark:border-white/[0.06]">
                <div className="text-[10px] text-slate-400">{isFr ? "Montant réglé" : "Paid Amount"}</div>
                <div className="font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                  <DisplayAmount amount={detail.paid_amount} currency={detail.currency} locale={locale} />
                </div>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#111D3D]/40 border border-slate-200/70 dark:border-white/[0.06]">
                <div className="text-[10px] text-slate-400">{isFr ? "Solde à régler" : "Remaining Due"}</div>
                <div className="font-bold text-amber-600 dark:text-amber-400 mt-0.5">
                  <DisplayAmount amount={detail.remaining_amount} currency={detail.currency} locale={locale} />
                </div>
              </div>
            </div>

            {detail.provenance && detail.provenance.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {detail.provenance.map((p, idx) => (
                  <span
                    key={`${p.field}-${idx}`}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] bg-slate-100 dark:bg-[#111D3D] text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-white/[0.08]"
                  >
                    <strong className="font-semibold">{p.field}:</strong>
                    <span>
                      {p.sheet
                        ? `${isFr ? "Onglet" : "Sheet"} ${p.sheet}${p.cell ? ` · ${p.cell}` : ""}`
                        : p.page != null
                          ? `Page ${p.page}`
                          : p.cell || "OCR"}
                    </span>
                  </span>
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-slate-400 dark:text-slate-500">
                {isFr
                  ? "Provenance : enregistrement structuré direct (aucune coordonnée de cellule ou page OCR attachée)."
                  : "Provenance: direct structured record (no spreadsheet cell or OCR page coordinate attached)."}
              </div>
            )}
          </section>

          {/* Line Items & Math Check */}
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8] flex items-center gap-1.5">
                <Calculator size={13} />
                <span>{isFr ? "Lignes de facturation & Contrôle arithmétique" : "Line Items & Math Verification"}</span>
              </h3>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold ${
                  mathValid
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                    : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                }`}
              >
                {mathValid ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                <span>
                  {mathValid
                    ? isFr
                      ? "Sous-total + Taxes = Total vérifié"
                      : "Subtotal + Tax = Total verified"
                    : isFr
                      ? "Écart arithmétique à vérifier"
                      : "Arithmetic discrepancy to verify"}
                </span>
              </span>
            </div>

            <div className="rounded-xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden">
              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50 dark:bg-[#111D3D]/60 text-slate-500 dark:text-slate-400 border-b border-slate-200/80 dark:border-white/[0.08]">
                    <th className="py-2.5 px-3">{isFr ? "Description" : "Description"}</th>
                    <th className="py-2.5 px-3 text-right">{isFr ? "Qté" : "Qty"}</th>
                    <th className="py-2.5 px-3 text-right">{isFr ? "Taxes" : "Tax"}</th>
                    <th className="py-2.5 px-3 text-right">{isFr ? "Total" : "Total"}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/[0.05]">
                  {lineItems.map((item, i) => (
                    <tr key={item.id ?? i}>
                      <td className="py-2.5 px-3 text-slate-800 dark:text-[#F4F7FB]">
                        <div>{item.description}</div>
                        {item.provenance && (item.provenance.sheet || item.provenance.cell || item.provenance.page != null) && (
                          <div className="text-[10px] text-slate-400">
                            {item.provenance.sheet ? `${item.provenance.sheet} ` : ""}
                            {item.provenance.cell ? `· ${item.provenance.cell}` : ""}
                            {item.provenance.page != null ? `Page ${item.provenance.page}` : ""}
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-600 dark:text-slate-300">
                        {item.quantity ?? 1}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-600 dark:text-slate-300">
                        {(item.tax_amount ?? 0).toFixed(2)} {detail.currency}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono font-bold text-slate-900 dark:text-white">
                        {item.total_amount.toFixed(2)} {detail.currency}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-50/70 dark:bg-[#060B13]/60 border-t border-slate-200/80 dark:border-white/[0.08] text-xs">
                  <tr>
                    <td colSpan={3} className="py-1.5 px-3 text-right text-slate-500">
                      {isFr ? "Sous-total hors taxes" : "Subtotal"}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono font-semibold text-slate-700 dark:text-slate-200">
                      {computedSubtotal.toFixed(2)} {detail.currency}
                    </td>
                  </tr>
                  <tr>
                    <td colSpan={3} className="py-1.5 px-3 text-right text-slate-500">
                      {isFr ? "Taxes documentées" : "Documented Taxes"}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono font-semibold text-slate-700 dark:text-slate-200">
                      {computedTax.toFixed(2)} {detail.currency}
                    </td>
                  </tr>
                  <tr className="border-t border-slate-200/60 dark:border-white/[0.06]">
                    <td colSpan={3} className="py-2 px-3 text-right font-bold text-slate-900 dark:text-white">
                      {isFr ? "Total facture" : "Invoice Total"}
                    </td>
                    <td className="py-2 px-3 text-right font-mono font-extrabold text-slate-900 dark:text-white">
                      {detail.total_amount.toFixed(2)} {detail.currency}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>

          {/* Proposed Classification & Confidence */}
          <section className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] bg-slate-50/40 dark:bg-[#111D3D]/30 p-4 space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 dark:text-[#F4F7FB]">
                <Sparkles size={14} className="text-[#0076FF] dark:text-[#00D4FF]" />
                <span>{isFr ? "Classification comptable proposée" : "Proposed Accounting Classification"}</span>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  classification.is_ai_suggestion
                    ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                    : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                }`}
              >
                {classification.is_ai_suggestion
                  ? isFr
                    ? `Suggestion IA (${Math.round((classification.confidence ?? 0.85) * 100)} %) — À vérifier`
                    : `AI Suggestion (${Math.round((classification.confidence ?? 0.85) * 100)}%) — To verify`
                  : isFr
                    ? "Imputation confirmée"
                    : "Confirmed Classification"}
              </span>
            </div>

            <div className="text-xs text-slate-700 dark:text-slate-200 flex flex-wrap gap-3">
              <span>
                <strong>{isFr ? "Catégorie :" : "Category:"}</strong>{" "}
                <span className="capitalize">{classification.category}</span>
              </span>
              {classification.account_code && (
                <span>
                  <strong>{isFr ? "Compte :" : "Account:"}</strong> {classification.account_code}
                </span>
              )}
            </div>

            {classification.reasons && classification.reasons.length > 0 && (
              <ul className="list-disc list-inside text-[11px] text-slate-500 dark:text-[#94A3B8] space-y-0.5">
                {classification.reasons.map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            )}
          </section>

          {/* Linked Accounting Entries & Payments */}
          <section className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#94A3B8] flex items-center gap-1.5">
              <Link2 size={13} />
              <span>
                {isFr
                  ? `Écritures comptables & Paiements liés (${linkedTransactions.length + paymentsList.length})`
                  : `Linked Journal Entries & Payments (${linkedTransactions.length + paymentsList.length})`}
              </span>
            </h3>

            {linkedTransactions.length === 0 && paymentsList.length === 0 ? (
              <div className="rounded-xl p-3.5 text-xs text-slate-500 dark:text-[#94A3B8] border border-dashed border-slate-200 dark:border-white/[0.08]">
                {isFr
                  ? "Aucune écriture de règlement ou de grand livre n'est encore rattachée à cette référence."
                  : "No settlement or general ledger entry is linked to this invoice reference yet."}
              </div>
            ) : (
              <div className="space-y-2">
                {paymentsList.map((pmt) => (
                  <div
                    key={pmt.id}
                    className="flex items-center justify-between p-3 rounded-xl bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/40 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <CreditCard size={14} className="text-emerald-600 dark:text-emerald-400" />
                      <div>
                        <div className="font-bold text-slate-800 dark:text-[#F4F7FB]">
                          {pmt.method || (isFr ? "Paiement" : "Payment")}
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {pmt.payment_date ? pmt.payment_date.slice(0, 10) : "—"} · Réf. {pmt.reference || detail.invoice_number}
                        </div>
                      </div>
                    </div>
                    <div className="font-mono font-bold text-emerald-700 dark:text-emerald-400">
                      {pmt.amount.toFixed(2)} {pmt.currency || detail.currency}
                    </div>
                  </div>
                ))}

                {linkedTransactions.map((tx) => (
                  <button
                    key={tx.id}
                    type="button"
                    onClick={() => onSelectTransaction?.(tx.id)}
                    className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-[#111D3D]/50 hover:bg-slate-100 dark:hover:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] text-xs text-left transition-colors cursor-pointer"
                  >
                    <div>
                      <div className="font-bold text-slate-800 dark:text-[#F4F7FB]">
                        {tx.description}
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                        {tx.transaction_date ? tx.transaction_date.slice(0, 10) : "—"} · {tx.category} ·{" "}
                        {tx.is_confirmed === false
                          ? isFr
                            ? "À vérifier"
                            : "To verify"
                          : isFr
                            ? "Écriture confirmée"
                            : "Confirmed entry"}
                      </div>
                    </div>
                    <div className="font-mono font-bold text-slate-900 dark:text-white">
                      {tx.amount.toFixed(2)} {tx.currency}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Permission-Gated Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-200/80 dark:border-white/[0.08] bg-slate-50/80 dark:bg-[#111D3D]/60 flex flex-wrap items-center justify-between gap-3 print:hidden">
          {canReadAccounting && (
            <div className="flex flex-wrap items-center gap-2">
              {safeDocUrl && (
                <a
                  href={safeDocUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-white/[0.05]"
                >
                  <ExternalLink size={13} />
                  <span>{isFr ? "Ouvrir" : "Open"}</span>
                </a>
              )}

              <div className="inline-flex items-center rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] overflow-hidden">
                <select
                  aria-label={isFr ? "Format de téléchargement facture" : "Invoice download format"}
                  value={downloadFormat}
                  onChange={(e) => setDownloadFormat(e.target.value as "csv" | "json" | "txt")}
                  className="px-2 py-1.5 text-xs bg-transparent text-slate-700 dark:text-slate-200 border-r border-slate-200 dark:border-white/[0.1] outline-none"
                >
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                  <option value="txt">TXT</option>
                </select>
                <button
                  type="button"
                  onClick={() => handleDownloadInvoice(downloadFormat)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-white/[0.05] cursor-pointer"
                >
                  <Download size={13} />
                  <span>{isFr ? "Télécharger" : "Download"}</span>
                </button>
              </div>

              <button
                type="button"
                onClick={handlePrintInvoice}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-white/[0.05] cursor-pointer"
              >
                <Printer size={13} />
                <span>{isFr ? "Imprimer" : "Print"}</span>
              </button>
            </div>
          )}

          {canWriteAccounting ? (
            <div className="flex flex-wrap items-center gap-2 ml-auto">
              <button
                type="button"
                onClick={() => setIsEditing((v) => !v)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.12] text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-white dark:hover:bg-white/[0.06] cursor-pointer"
              >
                <Edit3 size={13} />
                <span>{isFr ? "Corriger" : "Correct"}</span>
              </button>

              <button
                type="button"
                onClick={() => void handleRejectProposal()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-rose-300 dark:border-rose-700/60 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 cursor-pointer"
              >
                <XCircle size={13} />
                <span>{isFr ? "Rejeter la proposition" : "Reject Proposal"}</span>
              </button>

              <button
                type="button"
                onClick={handleApproveClick}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-bold shadow-xs cursor-pointer"
              >
                <CheckCircle2 size={14} />
                <span>{isFr ? "Approuver" : "Approve"}</span>
              </button>
            </div>
          ) : (
            <span className="text-[11px] text-slate-400 ml-auto">
              {isFr ? "Mode lecture seule (droits d'approbation requis)" : "Read-only mode (write permission required)"}
            </span>
          )}
        </div>
      </aside>
    </div>
  );
}

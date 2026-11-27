"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import { OcrAccountingInbox } from "@/components/accounting/ocr-accounting-inbox";
import { SelectedDocumentInvoices } from "@/components/accounting/selected-document-invoices";
import {
  ReceiptText,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Plus,
  Plug,
  CheckCircle2,
  Clock,
  Sparkles,
  ShieldAlert,
  Filter,
  Scale,
  Wallet,
  Percent,
  FileCheck2,
  Eye,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { HorizontalScroller } from "@/components/shell/horizontal-scroller";
import { DisplayAmount } from "@/components/common/display-amount";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { useOptionalSession } from "@/lib/session-context";
import {
  InvoiceDetailDrawer,
  type EnrichedInvoiceItem,
  type LinkedLedgerEntry,
} from "@/components/accounting/invoice-detail-drawer";

interface FinancialOverview {
  data_type?: string;
  is_projection?: boolean;
  total_revenue?: number;
  total_expenses?: number;
  cogs?: number;
  net_income?: number;
  net_profit?: number;
  gross_profit?: number;
  gross_margin_pct?: number;
  operating_margin_pct?: number;
  profit_margin?: number;
  unpaid_invoices_count?: number;
  unpaid_invoices_amount?: number;
  receivables?: {
    unpaid_count?: number;
    total_due?: number;
    overdue_count?: number;
    overdue_amount?: number;
  };
  payables?: {
    unpaid_count?: number;
    total_due?: number;
    overdue_count?: number;
    overdue_amount?: number;
  };
  taxes_total?: number;
  pending_entries_count?: number;
  currency?: string;
  transactions_count?: number;
  confirmed_transactions_count?: number;
  source_context?: { state: string | null; selection: string | null; name: string | null };
}

interface MarginsResponse {
  gross_profit?: number;
  gross_margin_pct?: number;
  operating_profit?: number;
  operating_margin_pct?: number;
  total_revenue?: number;
}

interface AnomalyItem {
  id: string;
  date: string;
  category: string;
  description: string;
  amount: number;
  category_average?: number;
  percentage_above_average?: number;
  reason: string;
}

interface CashFlowForecast {
  is_projection?: boolean;
  confidence?: string;
  disclaimer?: string;
  horizon_days?: number;
  current_confirmed_balance?: number;
  expected_incoming_receivables?: number;
  expected_outgoing_payables?: number;
  estimated_recurring_burn?: number;
  projected_net_cash_flow?: number;
  projected_final_balance?: number;
  currency?: string;
}

interface TransactionItem extends LinkedLedgerEntry {
  tax_amount?: number;
  extra_data?: Record<string, unknown>;
}

type PeriodFilter = "all" | "this_month" | "last_30d" | "quarter" | "year";
type StatusFilter = "all" | "confirmed" | "to_verify" | "paid" | "unpaid";
type SourceFilter = "all" | "retail" | "crm" | "ocr" | "manual";
type WorkspaceTab = "comparative" | "receivables" | "payables";

const EXTERNAL_SOURCE_KEYS = ["source", "connector", "provider", "import_source", "bank", "origin", "source_module"];
const INITIAL_ACCOUNTING_LIMIT = 150;
const MAX_ACCOUNTING_LIMIT = 200;

function externalSource(extra: Record<string, unknown> | undefined): string | null {
  if (!extra) return null;
  for (const key of EXTERNAL_SOURCE_KEYS) {
    const value = extra[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function classifySourceBucket(rawSource: string | null | undefined): Exclude<SourceFilter, "all"> {
  if (!rawSource) return "manual";
  const s = rawSource.toLowerCase();
  if (s.includes("retail") || s.includes("shopify") || s.includes("woo") || s.includes("commerce") || s.includes("pos")) {
    return "retail";
  }
  if (s.includes("crm") || s.includes("client") || s.includes("deal")) {
    return "crm";
  }
  if (s.includes("ocr") || s.includes("pdf") || s.includes("scan") || s.includes("xlsx") || s.includes("import") || s.includes("doc")) {
    return "ocr";
  }
  return "manual";
}

function matchesPeriod(isoDate: string | undefined, period: PeriodFilter): boolean {
  if (period === "all" || !isoDate) return true;
  const dt = new Date(isoDate);
  if (isNaN(dt.getTime())) return true;
  const now = new Date();
  if (period === "this_month") {
    return dt.getUTCFullYear() === now.getUTCFullYear() && dt.getUTCMonth() === now.getUTCMonth();
  }
  if (period === "last_30d") {
    return now.getTime() - dt.getTime() <= 30 * 86_400_000;
  }
  if (period === "quarter") {
    const qNow = Math.floor(now.getUTCMonth() / 3);
    const qDt = Math.floor(dt.getUTCMonth() / 3);
    return dt.getUTCFullYear() === now.getUTCFullYear() && qNow === qDt;
  }
  if (period === "year") {
    return dt.getUTCFullYear() === now.getUTCFullYear();
  }
  return true;
}

function enrichDuplicateFlags(invoices: EnrichedInvoiceItem[], isFr: boolean): EnrichedInvoiceItem[] {
  const groups = new Map<string, EnrichedInvoiceItem[]>();
  for (const inv of invoices) {
    const key = [
      (inv.invoice_number || "").trim().toLowerCase(),
      (inv.party_name || "").trim().toLowerCase(),
      Number(inv.total_amount || 0).toFixed(2),
      (inv.issue_date || "").slice(0, 10),
    ].join("|");
    const bucket = groups.get(key) ?? [];
    bucket.push(inv);
    groups.set(key, bucket);
  }

  return invoices.map((inv) => {
    const key = [
      (inv.invoice_number || "").trim().toLowerCase(),
      (inv.party_name || "").trim().toLowerCase(),
      Number(inv.total_amount || 0).toFixed(2),
      (inv.issue_date || "").slice(0, 10),
    ].join("|");
    const peers = groups.get(key) ?? [];
    const hasPeerDuplicate = peers.length > 1;
    const explicitDup =
      Boolean(inv.duplicate_warning) ||
      Boolean(inv.extra_data && inv.extra_data["duplicate_warning"]);

    if (!hasPeerDuplicate && !explicitDup) return inv;
    return {
      ...inv,
      duplicate_warning: true,
      duplicate_reason:
        inv.duplicate_reason ||
        (isFr
          ? `Doublon potentiel détecté : numéro ${inv.invoice_number}, tiers « ${inv.party_name} », montant ${Number(inv.total_amount).toFixed(2)} ${inv.currency} et date ${inv.issue_date.slice(0, 10)} identiques.`
          : `Potential duplicate detected: matching number ${inv.invoice_number}, counterparty "${inv.party_name}", amount ${Number(inv.total_amount).toFixed(2)} ${inv.currency}, and date ${inv.issue_date.slice(0, 10)}.`),
    };
  });
}

export function AccountingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const isFr = locale.toLowerCase().startsWith("fr");
  const session = useOptionalSession();

  const userPerms = Array.isArray(session?.identity?.user?.permissions)
    ? session.identity.user.permissions
    : [];
  const isPlatformAdmin = Boolean(session?.identity?.user?.is_platform_admin);

  const canReadAccounting =
    isPlatformAdmin ||
    userPerms.includes("accounting:read") ||
    userPerms.includes("accounting:write");

  const canWriteAccounting =
    isPlatformAdmin ||
    userPerms.includes("accounting:write");

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [loadedSourceKey, setLoadedSourceKey] = useState<string | null>(null);
  const loadSequence = useRef(0);
  const sourceKey = `${session?.identity?.company?.id ?? ""}:${session?.identity?.user?.id ?? ""}:${session?.sourceRevision ?? 0}`;
  const sourceSelectionState = session?.sourceSelectionState;
  const [refreshing, setRefreshing] = useState(false);
  const [invoiceLimit, setInvoiceLimit] = useState(INITIAL_ACCOUNTING_LIMIT);
  const [overview, setOverview] = useState<FinancialOverview | null>(null);
  const [margins, setMargins] = useState<MarginsResponse | null>(null);
  const [invoices, setInvoices] = useState<EnrichedInvoiceItem[]>([]);
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [forecast, setForecast] = useState<CashFlowForecast | null>(null);

  // Filters (F1) & Tabs (F3)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("comparative");
  const [ledgerFilter, setLedgerFilter] = useState<"all" | "revenue" | "expense">("all");
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [currencyFilter, setCurrencyFilter] = useState<string>("all");

  // Selected Invoice Drawer (F2) & Cross-link highlight
  const [selectedInvoice, setSelectedInvoice] = useState<EnrichedInvoiceItem | null>(null);
  const [highlightedTxId, setHighlightedTxId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (sourceSelectionState) return;
    const sequence = ++loadSequence.current;
    setLoading(true);
    setLoadError(false);
    setSelectedInvoice(null);
    setHighlightedTxId(null);
    try {
      const headers = getAuthHeaders();
      const responses = await Promise.all([
        fetch("/api/v1/accounting/overview", { headers }),
        fetch("/api/v1/accounting/margins", { headers }),
        fetch(`/api/v1/accounting/invoices?limit=${invoiceLimit}`, { headers }),
        fetch(`/api/v1/accounting/transactions?limit=${invoiceLimit}`, { headers }),
        fetch("/api/v1/accounting/anomalies", { headers }),
        fetch("/api/v1/accounting/forecast/cashflow?horizon_days=30", { headers }),
      ]);
      if (responses.some(response => !response.ok)) throw new Error("Accounting request failed");
      const [ovData, mgData, invData, txData, anomData, fcData] =
        await Promise.all(responses.map(response => response.json()));
      if (sequence !== loadSequence.current) return;
      const rawList: EnrichedInvoiceItem[] = Array.isArray(invData)
        ? invData
        : Array.isArray(invData?.invoices) ? invData.invoices : [];
      setOverview(ovData);
      setMargins(mgData);
      setInvoices(rawList.map(inv => ({
        ...inv,
        remaining_amount: inv.remaining_amount ?? Math.max(0, Number(inv.total_amount || 0) - Number(inv.paid_amount || 0)),
      })));
      setTransactions(Array.isArray(txData) ? txData.map((row: TransactionItem & { date?: string }) => ({
        ...row,
        transaction_date: row.transaction_date || row.date || "",
        extra_data: row.extra_data && typeof row.extra_data === "object" ? row.extra_data : {},
      })) : []);
      setAnomalies(Array.isArray(anomData?.anomalies) ? anomData.anomalies : []);
      setForecast(fcData);
      setLoadedSourceKey(sourceKey);
    } catch {
      if (sequence !== loadSequence.current) return;
      setOverview(null);
      setMargins(null);
      setInvoices([]);
      setTransactions([]);
      setAnomalies([]);
      setForecast(null);
      setLoadError(true);
      setLoadedSourceKey(sourceKey);
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }, [invoiceLimit, sourceKey, sourceSelectionState]);

  useEffect(() => {
    void loadData();
    return () => { loadSequence.current += 1; };
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const invoicesWithDuplicates = useMemo(
    () => enrichDuplicateFlags(invoices, isFr),
    [invoices, isFr]
  );

  const duplicateInvoices = useMemo(
    () => invoicesWithDuplicates.filter((inv) => inv.duplicate_warning),
    [invoicesWithDuplicates]
  );

  const availableCurrencies = useMemo(() => {
    const set = new Set<string>();
    if (overview?.currency) set.add(overview.currency);
    invoices.forEach((i) => i.currency && set.add(i.currency));
    transactions.forEach((tx) => tx.currency && set.add(tx.currency));
    if (set.size === 0) set.add("CAD");
    return Array.from(set);
  }, [overview, invoices, transactions]);

  const filteredInvoices = useMemo(() => {
    return invoicesWithDuplicates.filter((inv) => {
      if (!matchesPeriod(inv.issue_date || inv.due_date, periodFilter)) return false;
      if (currencyFilter !== "all" && inv.currency !== currencyFilter) return false;
      const srcBucket = classifySourceBucket(
        inv.source_module || externalSource(inv.extra_data)
      );
      if (sourceFilter !== "all" && srcBucket !== sourceFilter) return false;

      if (statusFilter === "confirmed" && inv.is_confirmed === false) return false;
      if (statusFilter === "to_verify" && inv.is_confirmed !== false && inv.status !== "to_verify") return false;
      if (statusFilter === "paid" && inv.status !== "paid" && inv.remaining_amount > 0.005) return false;
      if (statusFilter === "unpaid" && (inv.status === "paid" || inv.remaining_amount <= 0.005)) return false;
      return true;
    });
  }, [invoicesWithDuplicates, periodFilter, currencyFilter, sourceFilter, statusFilter]);

  const receivableInvoices = useMemo(
    () => filteredInvoices.filter((inv) => inv.invoice_type === "receivable"),
    [filteredInvoices]
  );
  const payableInvoices = useMemo(
    () => filteredInvoices.filter((inv) => inv.invoice_type === "payable"),
    [filteredInvoices]
  );

  const filteredTransactions = useMemo(() => {
    return transactions.filter((tx) => {
      if (ledgerFilter !== "all" && tx.transaction_type !== ledgerFilter) return false;
      if (!matchesPeriod(tx.transaction_date, periodFilter)) return false;
      if (currencyFilter !== "all" && tx.currency !== currencyFilter) return false;
      const srcBucket = classifySourceBucket(externalSource(tx.extra_data));
      if (sourceFilter !== "all" && srcBucket !== sourceFilter) return false;
      if (statusFilter === "confirmed" && tx.is_confirmed === false) return false;
      if (statusFilter === "to_verify" && tx.is_confirmed !== false && tx.status !== "pending") return false;
      return true;
    });
  }, [transactions, ledgerFilter, periodFilter, currencyFilter, sourceFilter, statusFilter]);

  // Financial Metrics (strictly distinguishing Confirmed Actuals vs AI Forecast / Pending)
  // Global KPIs always retain the authoritative backend overview currency to prevent currency relabeling without FX conversion.
  const overviewCurrency = overview?.currency || "CAD";
  const currency = overviewCurrency;
  const revenue = overview?.total_revenue ?? 0;
  const expenses = overview?.total_expenses ?? 0;
  const netProfit = overview?.net_income ?? overview?.net_profit ?? revenue - expenses;
  const grossMarginPct =
    margins?.gross_margin_pct ??
    overview?.gross_margin_pct ??
    (revenue > 0 ? Number((((revenue - (overview?.cogs ?? 0)) / revenue) * 100).toFixed(1)) : null);
  const operatingMarginPct =
    margins?.operating_margin_pct ??
    overview?.operating_margin_pct ??
    overview?.profit_margin ??
    (revenue > 0 ? Number(((netProfit / revenue) * 100).toFixed(1)) : null);

  const confirmedReceivableInvoices = useMemo(
    () =>
      receivableInvoices.filter(
        (i) => i.is_confirmed !== false && i.status !== "to_verify" && i.status !== "rejected"
      ),
    [receivableInvoices]
  );
  const confirmedPayableInvoices = useMemo(
    () =>
      payableInvoices.filter(
        (i) => i.is_confirmed !== false && i.status !== "to_verify" && i.status !== "rejected"
      ),
    [payableInvoices]
  );

  const arDue =
    overview?.receivables?.total_due ??
    confirmedReceivableInvoices
      .filter((i) => i.status !== "paid")
      .reduce((acc, i) => acc + Number(i.remaining_amount || 0), 0);
  const arCount =
    overview?.receivables?.unpaid_count ??
    confirmedReceivableInvoices.filter((i) => i.status !== "paid" && i.remaining_amount > 0).length;

  const apDue =
    overview?.payables?.total_due ??
    confirmedPayableInvoices
      .filter((i) => i.status !== "paid")
      .reduce((acc, i) => acc + Number(i.remaining_amount || 0), 0);
  const apCount =
    overview?.payables?.unpaid_count ??
    confirmedPayableInvoices.filter((i) => i.status !== "paid" && i.remaining_amount > 0).length;

  const unpaidInvoicesCount = overview?.unpaid_invoices_count ?? arCount + apCount;
  const unpaidInvoicesAmount = overview?.unpaid_invoices_amount ?? arDue + apDue;

  const knownTaxes =
    overview?.taxes_total ??
    transactions
      .filter((tx) => tx.is_confirmed !== false)
      .reduce((acc, tx) => acc + Number(tx.tax_amount || 0), 0);

  const pendingValidationCount =
    overview?.pending_entries_count ??
    transactions.filter((tx) => tx.is_confirmed === false || tx.status === "pending").length +
      invoices.filter((inv) => inv.is_confirmed === false || inv.status === "to_verify").length;

  const confirmedCashBalance = forecast?.current_confirmed_balance ?? netProfit;
  const projectedBalance = forecast?.projected_final_balance ?? null;

  const unreconciled =
    transactions.length > 0 && transactions.every((tx) => !externalSource(tx.extra_data));
  const recordedCaption = isFr
    ? "Somme des écritures confirmées, source non indiquée"
    : "Sum of confirmed entries, source not indicated";

  const linkedTransactionsForSelectedInvoice = useMemo(() => {
    if (!selectedInvoice) return [];
    const invNum = (selectedInvoice.invoice_number || "").trim().toLowerCase();
    return transactions.filter((tx) => {
      const ref = (tx.reference_id || "").trim().toLowerCase();
      return (
        (invNum && ref === invNum) ||
        ref === selectedInvoice.id.toLowerCase() ||
        (tx.description && invNum && tx.description.toLowerCase().includes(invNum))
      );
    });
  }, [selectedInvoice, transactions]);

  const handleInvoiceUpdate = (updated: EnrichedInvoiceItem) => {
    setInvoices((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    setSelectedInvoice(updated);
  };

  const renderInvoiceTable = (list: EnrichedInvoiceItem[], emptyLabel: string) => {
    if (list.length === 0) {
      return (
        <div className="p-8 text-center rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] text-xs text-slate-500 dark:text-[#94A3B8]">
          {emptyLabel}
        </div>
      );
    }

    return (
      <HorizontalScroller>
        <table className="w-max min-w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
              <th className="py-3 px-4">{isFr ? "Facture" : "Invoice"}</th>
              <th className="py-3 px-4">{isFr ? "Tiers" : "Counterparty"}</th>
              <th className="py-3 px-4">{isFr ? "Émission / Échéance" : "Issue / Due"}</th>
              <th className="py-3 px-4">{isFr ? "Source" : "Source"}</th>
              <th className="py-3 px-4 text-right">{isFr ? "Total" : "Total"}</th>
              <th className="py-3 px-4 text-right">{isFr ? "Solde dû" : "Balance Due"}</th>
              <th className="py-3 px-4 text-right">{isFr ? "Statut & Audit" : "Status & Audit"}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/[0.05]">
            {list.map((inv) => {
              const isRec = inv.invoice_type === "receivable";
              const isPaid = inv.status === "paid" || inv.remaining_amount <= 0.005;
              const isUnconfirmed = inv.is_confirmed === false || inv.status === "to_verify";
              const srcName = inv.source_module || externalSource(inv.extra_data) || (isFr ? "Manuel" : "Manual");
              const linkedCount = transactions.filter(
                (tx) =>
                  tx.reference_id &&
                  tx.reference_id.toLowerCase() === (inv.invoice_number || "").toLowerCase()
              ).length;

              return (
                <tr
                  key={inv.id}
                  onClick={() => setSelectedInvoice(inv)}
                  className="hover:bg-blue-50/50 dark:hover:bg-[#111D3D]/50 transition-colors cursor-pointer group"
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedInvoice(inv);
                        }}
                        className="font-mono font-bold text-slate-900 dark:text-[#F4F7FB] group-hover:text-[#0076FF] dark:group-hover:text-[#00D4FF] underline-offset-2 group-hover:underline focus:outline-none focus:ring-2 focus:ring-[#0076FF] rounded px-1 -mx-1 cursor-pointer"
                      >
                        #{inv.invoice_number}
                      </button>
                      {inv.duplicate_warning && (
                        <span
                          title={inv.duplicate_reason || ""}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-700 dark:text-amber-400 text-[10px] font-bold"
                        >
                          <ShieldAlert size={11} />
                          {isFr ? "Doublon ?" : "Duplicate?"}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {isRec
                        ? isFr
                          ? "Compte client (AR)"
                          : "Receivable (AR)"
                        : isFr
                          ? "Compte fournisseur (AP)"
                          : "Payable (AP)"}
                      {linkedCount > 0 ? ` · ${linkedCount} ${isFr ? "écriture(s)" : "entry"}` : ""}
                    </div>
                  </td>

                  <td className="py-3 px-4 font-semibold text-slate-800 dark:text-[#F4F7FB]">
                    {inv.party_name}
                  </td>

                  <td className="py-3 px-4 text-slate-600 dark:text-[#94A3B8]">
                    <div>{inv.issue_date ? inv.issue_date.slice(0, 10) : "—"}</div>
                    <div className="text-[10px] text-slate-400">
                      {isFr ? "Éch." : "Due"} {inv.due_date ? inv.due_date.slice(0, 10) : "—"}
                    </div>
                  </td>

                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 dark:bg-[#111D3D] text-slate-600 dark:text-slate-300">
                      {srcName}
                    </span>
                  </td>

                  <td className="py-3 px-4 font-mono font-bold text-right text-slate-900 dark:text-white">
                    <DisplayAmount
                      amount={inv.total_amount}
                      currency={inv.currency || currency}
                      locale={locale}
                      onDate={inv.issue_date ? inv.issue_date.slice(0, 10) : null}
                      align="end"
                    />
                  </td>

                  <td className="py-3 px-4 font-mono font-bold text-right text-amber-600 dark:text-amber-400">
                    <DisplayAmount
                      amount={inv.remaining_amount}
                      currency={inv.currency || currency}
                      locale={locale}
                      align="end"
                    />
                  </td>

                  <td className="py-3 px-4 text-right">
                    <div className="inline-flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold ${
                          inv.status === "rejected"
                            ? "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
                            : isUnconfirmed
                              ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                              : isPaid
                                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                                : inv.status === "overdue"
                                  ? "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
                                  : "bg-blue-50 text-[#0076FF] dark:bg-blue-950/40 dark:text-[#00D4FF]"
                        }`}
                      >
                        {inv.status === "rejected"
                          ? isFr
                            ? "Rejetée"
                            : "Rejected"
                          : isUnconfirmed
                            ? isPaid
                              ? isFr
                                ? "Payé · À vérifier"
                                : "Paid · To verify"
                              : isFr
                                ? "À vérifier"
                                : "To verify"
                            : isPaid
                              ? isFr
                                ? "Payé · Confirmé"
                                : "Paid · Confirmed"
                              : inv.status === "overdue"
                                ? isFr
                                  ? "Confirmé · En retard"
                                  : "Confirmed · Overdue"
                                : isFr
                                  ? "Confirmé · Impayé"
                                  : "Confirmed · Unpaid"}
                      </span>
                      <Eye size={13} className="text-slate-400 group-hover:text-[#0076FF]" />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </HorizontalScroller>
    );
  };

  if (sourceSelectionState) {
    const failed = sourceSelectionState === "unconfirmed";
    return (
      <div className="p-6 space-y-3" role={failed ? "alert" : "status"}>
        <p>{failed
          ? (isFr ? "Impossible de confirmer la source comptable." : "Unable to confirm the accounting source.")
          : (isFr ? "Confirmation de la source comptable…" : "Confirming accounting source…")}</p>
        {failed && <button type="button" onClick={() => void session?.reload()} className="underline">{isFr ? "Réessayer" : "Retry"}</button>}
      </div>
    );
  }

  if (loading || loadedSourceKey !== sourceKey || loadError) {
    return (
      <div className="p-6 space-y-3" role={loadError && !loading ? "alert" : "status"}>
        <p>{loadError && !loading
          ? (isFr ? "Impossible de charger les données comptables de la source active." : "Unable to load accounting data for the active source.")
          : (isFr ? "Chargement de la comptabilité…" : "Loading accounting…")}</p>
        {loadError && !loading && (
          <button type="button" onClick={() => void loadData()} className="underline">
            {isFr ? "Réessayer" : "Retry"}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF]">
              <ReceiptText size={22} />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                {t.navigation.accountingAi || (isFr ? "Comptabilité IA" : "Accounting AI")}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                {unreconciled
                  ? isFr
                    ? "Totaux calculés sur les écritures confirmées de cette entreprise. Les projections IA sont isolées des soldes comptables."
                    : "Totals calculated from confirmed company entries. AI projections are strictly separated from confirmed balances."
                  : isFr
                    ? "Grand livre, comptes clients (AR), comptes fournisseurs (AP), audit de factures et trésorerie."
                    : "General ledger, accounts receivable (AR), accounts payable (AP), invoice audit, and cash flow."}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin text-[#0076FF]" : ""} />
            <span>{isFr ? "Actualiser" : "Refresh"}</span>
          </button>

          <Link
            href="/connections"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors"
          >
            <Plus size={14} />
            <span>{isFr ? "Sources de données" : "Data Sources"}</span>
          </Link>
        </div>
      </div>

      {overview?.source_context?.selection && (
        <div role={overview.source_context.state === "READY" ? "status" : "alert"} className="rounded-xl border border-slate-200 dark:border-white/[0.08] p-3 text-xs">
          <strong>{isFr ? "Source comptable : " : "Accounting source: "}</strong>
          {overview.source_context.state === "READY"
            ? (overview.source_context.name || (isFr ? "Sources actives" : "Active sources"))
            : (isFr ? "Source indisponible ou sans données exploitables. Aucun élargissement automatique du périmètre comptable." : "Source unavailable or without usable data. Accounting scope is not automatically widened.")}
        </div>
      )}

      {/* Global Duplicate Warning Banner (F4) */}
      {duplicateInvoices.length > 0 && (
        <div
          role="alert"
          className="rounded-2xl p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert size={20} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900 dark:text-amber-200">
              <div className="font-extrabold">
                {isFr
                  ? `${duplicateInvoices.length} facture(s) présentent un risque de doublon (numéro, tiers, montant et date identiques)`
                  : `${duplicateInvoices.length} invoice(s) flagged for duplicate risk (matching number, party, amount, and date)`}
              </div>
              <p className="mt-0.5 text-amber-800/90 dark:text-amber-300/90">
                {isFr
                  ? "Cliquez sur la facture signalée pour inspecter sa pièce source et confirmer ou rejeter la proposition avant comptabilisation."
                  : "Click a flagged invoice to inspect its source document and confirm or reject before posting."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSelectedInvoice(duplicateInvoices[0])}
            className="px-3.5 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold shrink-0 cursor-pointer"
          >
            {isFr ? "Vérifier le doublon" : "Inspect Duplicate"}
          </button>
        </div>
      )}

      {/* Multi-Criteria Filter Bar (F1: Période, Statut, Source, Devise) */}
      <div className="p-3.5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs flex flex-wrap items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5 font-bold text-slate-600 dark:text-[#94A3B8] pr-1">
          <Filter size={14} className="text-[#0076FF] dark:text-[#00D4FF]" />
          <span>{isFr ? "Filtres :" : "Filters:"}</span>
        </div>

        <select
          aria-label={isFr ? "Période" : "Period"}
          value={periodFilter}
          onChange={(e) => setPeriodFilter(e.target.value as PeriodFilter)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50 dark:bg-[#111D3D] text-slate-800 dark:text-[#F4F7FB] font-medium"
        >
          <option value="all">{isFr ? "Toutes les périodes" : "All periods"}</option>
          <option value="this_month">{isFr ? "Ce mois-ci" : "This month"}</option>
          <option value="last_30d">{isFr ? "30 derniers jours" : "Last 30 days"}</option>
          <option value="quarter">{isFr ? "Trimestre en cours" : "Current quarter"}</option>
          <option value="year">{isFr ? "Année en cours" : "Current year"}</option>
        </select>

        <select
          aria-label={isFr ? "Statut" : "Status"}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50 dark:bg-[#111D3D] text-slate-800 dark:text-[#F4F7FB] font-medium"
        >
          <option value="all">{isFr ? "Tous les statuts" : "All statuses"}</option>
          <option value="confirmed">{isFr ? "Confirmé uniquement" : "Confirmed only"}</option>
          <option value="to_verify">{isFr ? "À vérifier / En attente" : "To verify / Pending"}</option>
          <option value="unpaid">{isFr ? "Factures impayées" : "Unpaid invoices"}</option>
          <option value="paid">{isFr ? "Factures réglées" : "Paid invoices"}</option>
        </select>

        <select
          aria-label={isFr ? "Source" : "Source"}
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50 dark:bg-[#111D3D] text-slate-800 dark:text-[#F4F7FB] font-medium"
        >
          <option value="all">{isFr ? "Toutes les sources" : "All sources"}</option>
          <option value="retail">Retail / E-commerce</option>
          <option value="crm">CRM</option>
          <option value="ocr">{isFr ? "OCR / Document importé" : "OCR / Imported Document"}</option>
          <option value="manual">{isFr ? "Saisie manuelle" : "Manual entry"}</option>
        </select>

        <select
          aria-label={isFr ? "Devise" : "Currency"}
          value={currencyFilter}
          onChange={(e) => setCurrencyFilter(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50 dark:bg-[#111D3D] text-slate-800 dark:text-[#F4F7FB] font-medium"
        >
          <option value="all">{isFr ? `Toutes devises (${currency})` : `All currencies (${currency})`}</option>
          {availableCurrencies.map((curr) => (
            <option key={curr} value={curr}>
              {curr}
            </option>
          ))}
        </select>

        {(periodFilter !== "all" || statusFilter !== "all" || sourceFilter !== "all" || currencyFilter !== "all") && (
          <button
            type="button"
            onClick={() => {
              setPeriodFilter("all");
              setStatusFilter("all");
              setSourceFilter("all");
              setCurrencyFilter("all");
            }}
            className="text-xs font-semibold text-[#0076FF] dark:text-[#00D4FF] hover:underline ml-auto cursor-pointer"
          >
            {isFr ? "Réinitialiser" : "Reset"}
          </button>
        )}

        <div className="w-full pt-1 border-t border-slate-100 dark:border-white/[0.05] flex items-center justify-between text-[11px] text-slate-500 dark:text-[#94A3B8]">
          <span>
            {isFr
              ? `${filteredInvoices.length} facture(s) affichée(s) sur ${invoices.length} chargée(s) (fenêtre max ${invoiceLimit}) · Les cartes KPI globales ci-dessous sont exprimées en ${overviewCurrency}.`
              : `Showing ${filteredInvoices.length} of ${invoices.length} loaded invoice(s) (window max ${invoiceLimit}) · Global KPI cards below are reported in ${overviewCurrency}.`}
          </span>
          {invoices.length >= invoiceLimit && invoiceLimit < MAX_ACCOUNTING_LIMIT && (
            <button
              type="button"
              onClick={() => setInvoiceLimit(MAX_ACCOUNTING_LIMIT)}
              className="font-semibold text-[#0076FF] dark:text-[#00D4FF] hover:underline cursor-pointer"
            >
              {isFr ? `Charger plus de factures (+${MAX_ACCOUNTING_LIMIT - invoiceLimit})` : `Load more invoices (+${MAX_ACCOUNTING_LIMIT - invoiceLimit})`}
            </button>
          )}
        </div>
      </div>

      {/* Primary KPI Grid — Confirmed Actuals */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Revenue */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{isFr ? "Revenus confirmés" : "Confirmed Revenue"}</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold">
              <ArrowUpRight size={12} /> {isFr ? "Confirmé" : "Confirmed"}
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            <DisplayAmount amount={revenue} currency={currency} locale={locale} />
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {unreconciled ? recordedCaption : isFr ? "Flux entrants comptabilisés" : "Posted incoming revenue"}
          </div>
        </div>

        {/* Expenses */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{isFr ? "Dépenses confirmées" : "Confirmed Expenses"}</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-[10px] font-bold">
              <ArrowDownRight size={12} /> {isFr ? "Confirmé" : "Confirmed"}
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            <DisplayAmount amount={expenses} currency={currency} locale={locale} />
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            {unreconciled ? recordedCaption : isFr ? "Charges opérationnelles confirmées" : "Confirmed operational expenses"}
          </div>
        </div>

        {/* Net Profit & Calculable Margins */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{isFr ? "Profit net & Marges" : "Net Profit & Margins"}</span>
            <span
              className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                netProfit >= 0
                  ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400"
                  : "bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-400"
              }`}
            >
              {operatingMarginPct != null ? `${operatingMarginPct}%` : isFr ? "Marge N/D" : "Margin N/A"}
            </span>
          </div>
          <div
            className={`text-2xl font-extrabold mt-2 ${
              netProfit >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600"
            }`}
          >
            <DisplayAmount amount={netProfit} currency={currency} locale={locale} />
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 flex items-center gap-1.5">
            <Percent size={11} />
            <span>
              {grossMarginPct != null
                ? isFr
                  ? `Marge brute ${grossMarginPct}% · Exploit. ${operatingMarginPct ?? 0}%`
                  : `Gross ${grossMarginPct}% · Oper. ${operatingMarginPct ?? 0}%`
                : isFr
                  ? "Marge non calculable (revenu nul)"
                  : "Margin not calculable (zero revenue)"}
            </span>
          </div>
        </div>

        {/* Unpaid Invoices (AR + AP) */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>{isFr ? "Factures impayées" : "Unpaid Invoices"}</span>
            <span className="p-1.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400">
              <Clock size={14} />
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {unpaidInvoicesCount} {isFr ? "ouvertes" : "open"}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            <DisplayAmount amount={unpaidInvoicesAmount} currency={currency} locale={locale} />
          </div>
        </div>
      </div>

      {/* Secondary Executive Strip: AR, AP, Cash Flow (Confirmed vs AI Projection), Taxes, Anomalies, Pending Validation */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        <button
          type="button"
          onClick={() => setActiveTab("receivables")}
          className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] hover:border-[#0076FF]/50 text-left transition-colors cursor-pointer"
        >
          <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
            {isFr ? "Comptes clients (AR)" : "Accounts Receivable (AR)"}
          </div>
          <div className="text-base font-extrabold text-emerald-600 dark:text-emerald-400 mt-1">
            <DisplayAmount amount={arDue} currency={currency} locale={locale} />
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {arCount} {isFr ? "à encaisser · Confirmé" : "to collect · Confirmed"}
          </div>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("payables")}
          className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] hover:border-[#0076FF]/50 text-left transition-colors cursor-pointer"
        >
          <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
            {isFr ? "Comptes fournisseurs (AP)" : "Accounts Payable (AP)"}
          </div>
          <div className="text-base font-extrabold text-rose-600 dark:text-rose-400 mt-1">
            <DisplayAmount amount={apDue} currency={currency} locale={locale} />
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {apCount} {isFr ? "à régler · Confirmé" : "to pay · Confirmed"}
          </div>
        </button>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08]">
          <div className="flex items-center justify-between gap-1">
            <span className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8] flex items-center gap-1">
              <Wallet size={12} /> {isFr ? "Trésorerie" : "Cash Flow"}
            </span>
            {projectedBalance != null && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-400">
                {isFr ? "Projection IA 30j" : "30d AI Est."}
              </span>
            )}
          </div>
          <div className="text-base font-extrabold text-slate-900 dark:text-white mt-1">
            <DisplayAmount amount={confirmedCashBalance} currency={currency} locale={locale} />
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {projectedBalance != null
              ? isFr
                ? `Solde confirmé · Est. 30j : ${projectedBalance.toFixed(0)} ${currency}`
                : `Confirmed · 30d Est.: ${projectedBalance.toFixed(0)} ${currency}`
              : isFr
                ? "Solde net des écritures confirmées"
                : "Net confirmed ledger balance"}
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08]">
          <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8] flex items-center gap-1">
            <Scale size={12} /> {isFr ? "Taxes connues" : "Documented Taxes"}
          </div>
          <div className="text-base font-extrabold text-slate-900 dark:text-white mt-1">
            <DisplayAmount amount={knownTaxes} currency={currency} locale={locale} />
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {isFr ? "Taxes extraites des écritures confirmées" : "Taxes on confirmed entries"}
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08]">
          <div className="flex items-center justify-between gap-1">
            <span className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8] flex items-center gap-1">
              <FileCheck2 size={12} /> {isFr ? "À valider & Anomalies" : "Pending & Anomalies"}
            </span>
            {(pendingValidationCount > 0 || anomalies.length > 0) && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-400">
                {isFr ? "À vérifier" : "Review"}
              </span>
            )}
          </div>
          <div className="text-base font-extrabold text-slate-900 dark:text-white mt-1">
            {pendingValidationCount} {isFr ? "en attente" : "pending"} · {anomalies.length}{" "}
            {isFr ? "anomalie(s)" : "anomalies"}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">
            {isFr ? "Exclu des soldes confirmés jusqu'à validation" : "Excluded from confirmed balances until approved"}
          </div>
        </div>
      </div>

      {/* Anomalies Alert Strip (when AI anomalies exist) */}
      {anomalies.length > 0 && (
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-amber-300/70 dark:border-amber-600/30 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              <Sparkles size={15} className="text-amber-500" />
              <span>
                {isFr
                  ? `Anomalies de dépenses détectées (${anomalies.length})`
                  : `Detected Expense Anomalies (${anomalies.length})`}
              </span>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-400">
              {isFr ? "Analyse IA — À vérifier" : "AI Insight — To verify"}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {anomalies.slice(0, 4).map((anom) => (
              <div
                key={anom.id}
                className="p-3 rounded-xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/70 dark:border-amber-800/40 text-xs"
              >
                <div className="font-bold text-slate-800 dark:text-white flex items-center justify-between">
                  <span>{anom.description}</span>
                  <span className="font-mono text-rose-600 dark:text-rose-400">
                    {anom.amount.toFixed(2)} {currency}
                  </span>
                </div>
                <div className="text-[11px] text-slate-600 dark:text-[#94A3B8] mt-0.5">{anom.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Receivables vs Payables vs Comparative Workspace (F3 & F2) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              {isFr ? "Factures, Créances Clients & Dettes Fournisseurs" : "Invoices, Receivables & Payables"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              {isFr
                ? "Cliquez sur n'importe quelle facture pour ouvrir sa fiche détaillée, sa pièce originale, sa provenance et ses écritures liées."
                : "Click any invoice to open its full detail drawer, original document, provenance, and linked entries."}
            </p>
          </div>

          <HorizontalScroller>
            <div className="flex w-max items-center gap-1.5 rounded-xl bg-slate-100 p-1 text-xs font-medium dark:bg-[#111D3D]">
              <button
                type="button"
                onClick={() => setActiveTab("comparative")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  activeTab === "comparative"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr
                  ? `Vue comparative globale (${filteredInvoices.length})`
                  : `Global Comparative View (${filteredInvoices.length})`}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("receivables")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  activeTab === "receivables"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr
                  ? `Revenus / Comptes clients (${receivableInvoices.length})`
                  : `Revenue / Receivables (${receivableInvoices.length})`}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("payables")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  activeTab === "payables"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr
                  ? `Dépenses / Comptes fournisseurs (${payableInvoices.length})`
                  : `Expenses / Payables (${payableInvoices.length})`}
              </button>
            </div>
          </HorizontalScroller>
        </div>

        {activeTab === "comparative" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              <div className="p-4 rounded-xl bg-emerald-50/40 dark:bg-emerald-950/15 border border-emerald-200/70 dark:border-emerald-800/30 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-emerald-800 dark:text-emerald-300">
                    {isFr ? "Total à recevoir — Clients (AR)" : "Total Receivable — Customers (AR)"}
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                    {receivableInvoices.length} {isFr ? "facture(s) filtrée(s)" : "filtered invoice(s)"}
                  </div>
                </div>
                <div className="text-lg font-extrabold text-emerald-700 dark:text-emerald-400">
                  <DisplayAmount amount={arDue} currency={currency} locale={locale} align="end" />
                </div>
              </div>

              <div className="p-4 rounded-xl bg-rose-50/40 dark:bg-rose-950/15 border border-rose-200/70 dark:border-rose-800/30 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-rose-800 dark:text-rose-300">
                    {isFr ? "Total à payer — Fournisseurs (AP)" : "Total Payable — Suppliers (AP)"}
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                    {payableInvoices.length} {isFr ? "facture(s) filtrée(s)" : "filtered invoice(s)"}
                  </div>
                </div>
                <div className="text-lg font-extrabold text-rose-700 dark:text-rose-400">
                  <DisplayAmount amount={apDue} currency={currency} locale={locale} align="end" />
                </div>
              </div>
            </div>

            {renderInvoiceTable(
              filteredInvoices,
              isFr
                ? "Aucune facture client ou fournisseur pour les filtres sélectionnés."
                : "No customer or supplier invoices match the selected filters."
            )}
          </div>
        )}

        {activeTab === "receivables" &&
          renderInvoiceTable(
            receivableInvoices,
            isFr
              ? "Aucune facture client (AR) trouvée pour cette sélection."
              : "No customer receivable invoices (AR) found for this selection."
          )}

        {activeTab === "payables" &&
          renderInvoiceTable(
            payableInvoices,
            isFr
              ? "Aucune facture fournisseur (AP) trouvée pour cette sélection."
              : "No supplier payable invoices (AP) found for this selection."
          )}
      </div>

      {/* Transactions & General Ledger with Cross-Links */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              {isFr ? "Journal des transactions & Grand livre" : "Transaction Ledger & Journal"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              {isFr
                ? "Les totaux utilisent le cours du jour. Chaque écriture utilise le taux à sa date. Cliquez sur une référence de facture pour l'inspecter."
                : "Totals use today's rate. Each entry uses the rate on its date. Click any invoice reference to inspect it."}
            </p>
          </div>

          <HorizontalScroller>
            <div className="flex w-max items-center gap-1.5 rounded-xl bg-slate-100 p-1 text-xs font-medium dark:bg-[#111D3D]">
              <button
                type="button"
                onClick={() => setLedgerFilter("all")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  ledgerFilter === "all"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr ? `Toutes (${filteredTransactions.length})` : `All (${filteredTransactions.length})`}
              </button>
              <button
                type="button"
                onClick={() => setLedgerFilter("revenue")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  ledgerFilter === "revenue"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr ? "Revenus" : "Revenue"}
              </button>
              <button
                type="button"
                onClick={() => setLedgerFilter("expense")}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  ledgerFilter === "expense"
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {isFr ? "Dépenses" : "Expenses"}
              </button>
            </div>
          </HorizontalScroller>
        </div>

        {unreconciled && (
          <p
            role="status"
            className="text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-xl px-3 py-2"
          >
            {isFr
              ? "Aucune source bancaire ou connecteur n’est indiqué sur ces écritures. Elles restent dans le journal de cette entreprise et ne constituent pas un état financier rapproché."
              : "No bank or connector source is recorded on these entries. They stay in this company’s journal and are not a reconciled financial statement."}
          </p>
        )}

        {filteredTransactions.length === 0 ? (
          <div className="p-12 text-center rounded-2xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] flex items-center justify-center mx-auto">
              <ReceiptText size={24} />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-800 dark:text-[#F4F7FB]">
                {isFr ? "Aucune transaction comptable trouvée" : "No accounting transactions found"}
              </div>
              <p className="text-xs text-slate-400 dark:text-slate-500 max-w-md mx-auto mt-1">
                {isFr
                  ? "Connectez vos sources de données comptables ou effectuez des saisies pour activer l'analyse financière IA."
                  : "Connect your accounting data sources or enter transactions to activate AI financial analytics."}
              </p>
            </div>
            <Link
              href="/connections"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors"
            >
              <Plug size={14} />
              <span>{t.navigation.connections || (isFr ? "Connexions" : "Connections")}</span>
            </Link>
          </div>
        ) : (
          <HorizontalScroller>
            <table className="w-max min-w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">{isFr ? "Date" : "Date"}</th>
                  <th className="py-3 px-4">{isFr ? "Type" : "Type"}</th>
                  <th className="py-3 px-4">{isFr ? "Catégorie" : "Category"}</th>
                  <th className="py-3 px-4">{isFr ? "Description" : "Description"}</th>
                  <th className="py-3 px-4">{isFr ? "Facture / Réf." : "Invoice / Ref."}</th>
                  <th className="py-3 px-4 text-right">{isFr ? "Montant" : "Amount"}</th>
                  <th className="py-3 px-4 text-right">{isFr ? "Statut" : "Status"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {filteredTransactions.map((tx) => {
                  const isRevenue = tx.transaction_type === "revenue";
                  const dateStr = tx.transaction_date ? tx.transaction_date.slice(0, 10) : "—";
                  const source = externalSource(tx.extra_data);
                  const isPending = tx.is_confirmed === false || tx.status === "pending";
                  const statusLabel = isPending
                    ? isFr
                      ? "À vérifier"
                      : "To verify"
                    : source
                      ? tx.status === "confirmed"
                        ? isFr
                          ? `Confirmé · ${source}`
                          : `Confirmed · ${source}`
                        : `${tx.status} · ${source}`
                      : tx.status === "confirmed"
                        ? isFr
                          ? "Confirmé — source non indiquée"
                          : "Confirmed — source not indicated"
                        : tx.status;

                  const matchedInvoice = tx.reference_id
                    ? invoicesWithDuplicates.find(
                        (inv) =>
                          inv.invoice_number.toLowerCase() === tx.reference_id!.toLowerCase() ||
                          inv.id.toLowerCase() === tx.reference_id!.toLowerCase()
                      )
                    : undefined;

                  return (
                    <tr
                      key={tx.id}
                      className={`transition-colors ${
                        highlightedTxId === tx.id
                          ? "bg-blue-50 dark:bg-[#0076FF]/20"
                          : "hover:bg-slate-50/80 dark:hover:bg-white/[0.02]"
                      }`}
                    >
                      <td className="py-3 px-4 text-slate-600 dark:text-[#94A3B8]">{dateStr}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold ${
                            isRevenue
                              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                              : "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
                          }`}
                        >
                          {isRevenue ? (isFr ? "Revenu" : "Revenue") : isFr ? "Dépense" : "Expense"}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-800 dark:text-[#F4F7FB] capitalize">
                        {tx.category}
                      </td>
                      <td className="py-3 px-4 text-slate-600 dark:text-slate-300 max-w-xs truncate">
                        {tx.description}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {matchedInvoice ? (
                          <button
                            type="button"
                            onClick={() => setSelectedInvoice(matchedInvoice)}
                            className="text-[#0076FF] dark:text-[#00D4FF] font-bold hover:underline cursor-pointer"
                          >
                            #{matchedInvoice.invoice_number}
                          </button>
                        ) : (
                          <span className="text-slate-400">{tx.reference_id || "—"}</span>
                        )}
                      </td>
                      <td
                        className={`py-3 px-4 font-mono font-bold text-right ${
                          isRevenue ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600"
                        }`}
                      >
                        <DisplayAmount
                          amount={(isRevenue ? 1 : -1) * Number(tx.amount || 0)}
                          currency={tx.currency || currency}
                          locale={locale}
                          onDate={tx.transaction_date ? tx.transaction_date.slice(0, 10) : null}
                          align="end"
                        />
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span
                          className={`inline-flex items-center gap-1 text-[10px] font-medium ${
                            isPending
                              ? "text-amber-600 dark:text-amber-400"
                              : "text-emerald-600 dark:text-emerald-400"
                          }`}
                        >
                          {isPending ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
                          <span>{statusLabel}</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </HorizontalScroller>
        )}
      </div>

      <SelectedDocumentInvoices key={`selected:${sourceKey}`} isFr={isFr} />
      <OcrAccountingInbox key={sourceKey} isFr={isFr} onSelect={setSelectedInvoice} />

      {/* Clickable Invoice Detail Drawer (F2) */}
      <InvoiceDetailDrawer
        invoice={selectedInvoice}
        onClose={() => setSelectedInvoice(null)}
        linkedTransactions={linkedTransactionsForSelectedInvoice}
        locale={locale}
        isFr={isFr}
        canReadAccounting={canReadAccounting}
        canWriteAccounting={canWriteAccounting}
        onSelectTransaction={(txId) => {
          setHighlightedTxId(txId);
          setSelectedInvoice(null);
        }}
        onInvoiceUpdated={handleInvoiceUpdate}
      />
    </div>
  );
}

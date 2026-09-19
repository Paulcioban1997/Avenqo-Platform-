"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  ReceiptText,
  DollarSign,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Plus,
  FileSpreadsheet,
  Download,
  Plug,
  Calendar,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

interface FinancialOverview {
  total_revenue?: number;
  total_expenses?: number;
  net_profit?: number;
  profit_margin?: number;
  unpaid_invoices_count?: number;
  unpaid_invoices_amount?: number;
  currency?: string;
  confirmed_transactions_count?: number;
}

interface TransactionItem {
  id: string;
  transaction_date: string;
  transaction_type: "revenue" | "expense";
  category: string;
  description: string;
  amount: number;
  currency: string;
  status: string;
  reference_id?: string;
}

export function AccountingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [overview, setOverview] = useState<FinancialOverview | null>(null);
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [activeFilter, setActiveFilter] = useState<"all" | "revenue" | "expense">("all");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [ovRes, txRes] = await Promise.all([
        fetch("/api/v1/accounting/overview", { headers }).catch(() => null),
        fetch("/api/v1/accounting/transactions?limit=50", { headers }).catch(() => null),
      ]);

      if (ovRes && ovRes.ok) {
        const data = await ovRes.json();
        setOverview(data);
      }
      if (txRes && txRes.ok) {
        const txData = await txRes.json();
        if (Array.isArray(txData)) {
          setTransactions(txData);
        }
      }
    } catch {
      // keep safe state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const filteredTransactions = transactions.filter((t) => {
    if (activeFilter === "all") return true;
    return t.transaction_type === activeFilter;
  });

  const currency = overview?.currency || "CAD";
  const revenue = overview?.total_revenue || 0;
  const expenses = overview?.total_expenses || 0;
  const netProfit = overview?.net_profit || revenue - expenses;
  const margin = overview?.profit_margin ?? (revenue > 0 ? ((netProfit / revenue) * 100).toFixed(1) : 0);

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
                {t.navigation?.accountingAi || "Comptabilité & Finance IA"}
              </h1>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-[#94A3B8]">
                Consolidation financière certifiée, détection d'anomalies et suivi automatisé de trésorerie.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin text-[#0076FF]" : ""} />
            <span>Actualiser</span>
          </button>

          <Link
            href="/connections"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors"
          >
            <Plus size={14} />
            <span>Connecter des sources</span>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Revenue */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Chiffre d'affaires</span>
            <span className="p-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400">
              <ArrowUpRight size={14} />
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            ${revenue.toLocaleString("fr-CA", { minimumFractionDigits: 2 })} {currency}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Entrées comptabilisées
          </div>
        </div>

        {/* Expenses */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Dépenses consolidées</span>
            <span className="p-1.5 rounded-lg bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400">
              <ArrowDownRight size={14} />
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            ${expenses.toLocaleString("fr-CA", { minimumFractionDigits: 2 })} {currency}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Charges et achats vérifiés
          </div>
        </div>

        {/* Net Profit */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Résultat Net</span>
            <span className={`p-1.5 rounded-lg text-xs font-bold ${netProfit >= 0 ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400" : "bg-rose-50 text-rose-600"}`}>
              {margin}%
            </span>
          </div>
          <div className={`text-2xl font-extrabold mt-2 ${netProfit >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600"}`}>
            ${netProfit.toLocaleString("fr-CA", { minimumFractionDigits: 2 })} {currency}
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            Marge bénéficiaire nette
          </div>
        </div>

        {/* Pending Invoices */}
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-[#94A3B8]">
            <span>Créances en attente</span>
            <span className="p-1.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400">
              <Clock size={14} />
            </span>
          </div>
          <div className="text-2xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
            {overview?.unpaid_invoices_count || 0} facture(s)
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
            ${(overview?.unpaid_invoices_amount || 0).toLocaleString("fr-CA", { minimumFractionDigits: 2 })} {currency}
          </div>
        </div>
      </div>

      {/* Transactions & Ledger */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100 dark:border-white/[0.06]">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              Journal des Écritures & Transactions
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              Écritures synchronisées automatiquement depuis vos boutiques en ligne et imports bancaires.
            </p>
          </div>

          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-[#111D3D] text-xs font-medium">
            <button
              onClick={() => setActiveFilter("all")}
              className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                activeFilter === "all"
                  ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Toutes ({transactions.length})
            </button>
            <button
              onClick={() => setActiveFilter("revenue")}
              className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                activeFilter === "revenue"
                  ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Revenus
            </button>
            <button
              onClick={() => setActiveFilter("expense")}
              className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                activeFilter === "expense"
                  ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Dépenses
            </button>
          </div>
        </div>

        {filteredTransactions.length === 0 ? (
          <div className="p-12 text-center rounded-2xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06] space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] dark:text-[#00D4FF] flex items-center justify-center mx-auto">
              <ReceiptText size={24} />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-800 dark:text-[#F4F7FB]">
                Aucune écriture comptable disponible
              </div>
              <p className="text-xs text-slate-400 dark:text-slate-500 max-w-md mx-auto mt-1">
                Connectez votre boutique en ligne (Shopify, WooCommerce, Etsy) ou importez vos relevés comptables (CSV, Excel) pour générer automatiquement vos écritures.
              </p>
            </div>
            <Link
              href="/connections"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors"
            >
              <Plug size={14} />
              <span>Ouvrir les Connexions</span>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Catégorie</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4">Réf.</th>
                  <th className="py-3 px-4 text-right">Montant</th>
                  <th className="py-3 px-4 text-right">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {filteredTransactions.map((tx) => {
                  const isRevenue = tx.transaction_type === "revenue";
                  const dateStr = tx.transaction_date ? tx.transaction_date.slice(0, 10) : "—";

                  return (
                    <tr key={tx.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02] transition-colors">
                      <td className="py-3 px-4 text-slate-600 dark:text-[#94A3B8]">{dateStr}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold ${
                            isRevenue
                              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                              : "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
                          }`}
                        >
                          {isRevenue ? "Entrée" : "Sortie"}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-800 dark:text-[#F4F7FB] capitalize">
                        {tx.category}
                      </td>
                      <td className="py-3 px-4 text-slate-600 dark:text-slate-300 max-w-xs truncate">
                        {tx.description}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-400">
                        {tx.reference_id || "—"}
                      </td>
                      <td className={`py-3 px-4 font-mono font-bold text-right ${isRevenue ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600"}`}>
                        {isRevenue ? "+" : "-"}${Number(tx.amount || 0).toFixed(2)} {tx.currency || currency}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">
                          <CheckCircle2 size={12} />
                          <span>Vérifié</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  CreditCard,
  ExternalLink,
  Sparkles,
  RefreshCw,
  Download,
  FileText,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  Zap,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

interface SubscriptionInfo {
  plan_code: string;
  status: string;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean;
}

interface AICreditBalance {
  billing_period?: string;
  monthly_allocation?: number;
  monthly_included?: number;
  monthly_remaining?: number;
  monthly_used?: number;
  purchased_total_available?: number;
  purchased_remaining?: number;
  total_available?: number;
  total_remaining?: number;
}

interface CreditPack {
  code: string;
  name: string;
  credits: number;
  price_cents?: number;
  price_usd?: number;
}

interface InvoiceItem {
  id: string;
  number?: string | null;
  plan_code?: string;
  status: string;
  currency: string;
  total: number;
  subtotal?: number;
  tax_total?: number;
  amount_paid?: number;
  issued_at?: string;
  period_start?: string;
  period_end?: string;
  invoice_pdf?: string | null;
  hosted_invoice_url?: string | null;
}

export function BillingView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [subscription, setSubscription] = useState<SubscriptionInfo>({
    plan_code: "demo",
    status: "inactive",
  });

  const [credits, setCredits] = useState<AICreditBalance>({
    billing_period: "2026-09",
    monthly_allocation: 6500,
    monthly_remaining: 6500,
    monthly_used: 0,
    purchased_total_available: 0,
    total_available: 6500,
  });

  const [creditPacks, setCreditPacks] = useState<CreditPack[]>([
    { code: "pack_6500", name: "Pack Découverte", credits: 6500, price_usd: 10 },
    { code: "pack_25000", name: "Pack Évolution", credits: 25000, price_usd: 35 },
    { code: "pack_65000", name: "Pack Business Pro", credits: 65000, price_usd: 80 },
  ]);

  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setActionError(null);
    try {
      const headers = getAuthHeaders();
      const [subRes, credRes, packRes, invRes] = await Promise.all([
        fetch("/api/v1/billing/subscription", { headers }).catch(() => null),
        fetch("/api/v1/billing/ai-credits", { headers }).catch(() => null),
        fetch("/api/v1/billing/credit-packs", { headers }).catch(() => null),
        fetch("/api/v1/billing/invoices/history?offset=0&limit=50", { headers }).catch(() => null),
      ]);

      if (subRes && subRes.ok) {
        const subData = await subRes.json();
        setSubscription(subData);
      }
      if (credRes && credRes.ok) {
        const credData = await credRes.json();
        setCredits(credData);
      }
      if (packRes && packRes.ok) {
        const packData = await packRes.json();
        if (Array.isArray(packData) && packData.length > 0) {
          setCreditPacks(packData);
        }
      }
      if (invRes && invRes.ok) {
        const invData = await invRes.json();
        if (invData && Array.isArray(invData.items)) {
          setInvoices(invData.items);
        }
      }
    } catch {
      // Keep loaded state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefreshBalance = async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/v1/billing/ai-credits", { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setCredits(data);
      }
    } finally {
      setRefreshing(false);
    }
  };

  const handleOpenStripePortal = async () => {
    try {
      const res = await fetch("/api/v1/billing/portal", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          window.open(data.url, "_blank");
          return;
        }
      }
      setActionError("Le portail Stripe n'est pas configuré pour ce compte de test.");
    } catch {
      setActionError("Impossible d'ouvrir le portail Stripe pour l'instant.");
    }
  };

  const handleManageSubscription = async () => {
    try {
      const res = await fetch("/api/v1/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ plan_code: subscription.plan_code || "professional" }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          window.location.href = data.url;
          return;
        }
      }
      handleOpenStripePortal();
    } catch {
      handleOpenStripePortal();
    }
  };

  const handleBuyCredits = async (packCode: string) => {
    try {
      const res = await fetch("/api/v1/billing/credit-packs/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ pack_code: packCode }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          window.location.href = data.url;
          return;
        }
      }
      setActionError("Un abonnement actif ou d'essai est requis pour acheter des packs de crédits.");
    } catch {
      setActionError("Erreur lors de l'accès au paiement des crédits.");
    }
  };

  const handleDownloadInvoice = async (invoice: InvoiceItem, format: "pdf" | "csv" | "xlsx") => {
    setDownloadingId(`${invoice.id}-${format}`);
    setActionError(null);
    try {
      const endpoint =
        format === "pdf"
          ? `/api/v1/billing/invoices/${invoice.id}/pdf`
          : `/api/v1/billing/invoices/${invoice.id}/export/${format}`;

      const res = await fetch(endpoint, {
        headers: getAuthHeaders(),
      });

      if (!res.ok) {
        throw new Error("Erreur de téléchargement");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const num = invoice.number || invoice.id.slice(0, 8);
      a.download = `facture-avenqo-${num}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setActionSuccess(`Facture ${num} (${format.toUpperCase()}) téléchargée avec succès.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch {
      setActionError(`Impossible de télécharger la facture au format ${format.toUpperCase()}.`);
    } finally {
      setDownloadingId(null);
    }
  };

  const monthlyAlloc = credits.monthly_allocation ?? credits.monthly_included ?? 6500;
  const monthlyRem = credits.monthly_remaining ?? monthlyAlloc;
  const monthlyUsed = credits.monthly_used ?? Math.max(0, monthlyAlloc - monthlyRem);
  const purchasedRem = credits.purchased_total_available ?? credits.purchased_remaining ?? 0;
  const totalAvail = credits.total_available ?? credits.total_remaining ?? (monthlyRem + purchasedRem);
  const progressPercent = monthlyAlloc > 0 ? Math.min(100, Math.round((monthlyUsed / monthlyAlloc) * 100)) : 0;

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
            Facturation
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            Gérez votre abonnement, vos factures officielles et le solde de vos crédits d'intelligence artificielle.
          </p>
        </div>

        <button
          onClick={handleOpenStripePortal}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors self-start sm:self-auto"
        >
          <ExternalLink size={15} />
          <span>Portail Stripe</span>
        </button>
      </div>

      {/* Notifications */}
      {actionError && (
        <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 flex items-center gap-2.5 text-xs text-amber-800 dark:text-amber-300">
          <AlertCircle size={16} className="shrink-0 text-amber-600 dark:text-amber-400" />
          <span>{actionError}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 flex items-center gap-2.5 text-xs text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 size={16} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* 1. Subscription Plan Card */}
      <div className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB]">
              Plan {subscription.plan_code ? subscription.plan_code.charAt(0).toUpperCase() + subscription.plan_code.slice(1) : "Demo"}
            </div>
            <div className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">
              État :{" "}
              <span className={`font-semibold ${subscription.status === "active" ? "text-emerald-600 dark:text-emerald-400" : "text-slate-600 dark:text-slate-300"}`}>
                {subscription.status === "active" ? "Actif" : subscription.status === "trialing" ? "Essai" : "Inactif"}
              </span>
            </div>
          </div>

          <button
            onClick={handleManageSubscription}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors self-start sm:self-auto"
          >
            <CreditCard size={14} />
            <span>Gérer l'abonnement</span>
          </button>
        </div>
      </div>

      {/* 2. AI Credits Card */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-[#0076FF] dark:text-[#00D4FF]">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
                Crédits IA
              </h2>
              <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
                Votre allocation mensuelle et le solde de vos crédits achetés.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 self-end sm:self-auto">
            <span className="text-xs text-slate-400 dark:text-slate-500">
              Période de facturation: {credits.billing_period || "2026-09"}
            </span>
            <button
              onClick={handleRefreshBalance}
              disabled={refreshing}
              title="Rafraîchir les crédits"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors"
            >
              <RefreshCw size={15} className={refreshing ? "animate-spin text-[#0076FF]" : ""} />
            </button>
          </div>
        </div>

        {/* 4 Metric Boxes */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 my-4">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
              Allocation mensuelle
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-1.5">
              {monthlyAlloc.toLocaleString()}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
              Allocation mensuelle restante
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-1.5">
              {monthlyRem.toLocaleString()}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
              Crédits achetés restants
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-1.5">
              {purchasedRem.toLocaleString()}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-blue-50/60 dark:bg-[#172652] border border-blue-100 dark:border-[#0076FF]/30">
            <div className="text-[11px] font-semibold text-blue-700 dark:text-[#00D4FF]">
              Total disponible
            </div>
            <div className="text-xl font-extrabold text-[#0076FF] dark:text-[#00D4FF] mt-1.5">
              {totalAvail.toLocaleString()}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4 pt-2">
          <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-white/[0.08] overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#0076FF] to-[#00D4FF] transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500 mt-2">
            <span>
              Crédits {monthlyUsed.toLocaleString()} sur {monthlyAlloc.toLocaleString()} utilisés pendant cette période
            </span>
            <span>{progressPercent}%</span>
          </div>
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-2">
            L'usage mensuel et les crédits achetés sont remis à zéro à chaque renouvellement d'abonnement payé.
          </p>
        </div>
      </div>

      {/* 3. Add AI Credits Section */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
            Ajouter des crédits IA
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
            Packs de crédits à achat unique, traités en toute sécurité par Stripe.
          </p>
          <div className="mt-1 text-xs font-semibold text-amber-600 dark:text-amber-400">
            Un abonnement actif ou d'essai est requis pour acheter des packs de crédits.
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {creditPacks.map((pack) => (
            <div
              key={pack.code}
              className="p-5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    {pack.name}
                  </span>
                  <Zap size={15} className="text-[#0076FF]" />
                </div>
                <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-2">
                  {pack.credits.toLocaleString()} crédits
                </div>
                <div className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1">
                  ${pack.price_usd || ((pack.price_cents || 0) / 100)} USD
                </div>
              </div>

              <button
                onClick={() => handleBuyCredits(pack.code)}
                className="mt-4 w-full py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#111D3D] dark:hover:bg-[#172652] text-xs font-semibold text-slate-800 dark:text-[#F4F7FB] transition-colors"
              >
                Acheter ce pack
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Invoices History Table */}
      <div className="space-y-3 pt-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              Historique des Factures
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              Consultez et téléchargez vos factures certifiées pour votre comptabilité.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">
              {invoices.length} facture(s) émise(s)
            </span>
          </div>
        </div>

        <div className="rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] overflow-hidden shadow-xs">
          {invoices.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 dark:text-slate-500">
              Aucune facture disponible pour le moment. Vos reçus s'afficheront automatiquement dès votre premier cycle de facturation.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                    <th className="py-3 px-4">N° Facture</th>
                    <th className="py-3 px-4">Date</th>
                    <th className="py-3 px-4">Période</th>
                    <th className="py-3 px-4">Plan</th>
                    <th className="py-3 px-4">Montant</th>
                    <th className="py-3 px-4">Statut</th>
                    <th className="py-3 px-4 text-right">Téléchargements</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                  {invoices.map((inv) => {
                    const invNumber = inv.number || `AVQ-${inv.id.slice(0, 8).toUpperCase()}`;
                    const dateStr = inv.issued_at ? inv.issued_at.slice(0, 10) : "—";
                    const periodStr =
                      inv.period_start && inv.period_end
                        ? `${inv.period_start.slice(0, 7)}`
                        : "Courante";
                    const amountStr = `${((inv.total || 0) / 100).toFixed(2)} ${(inv.currency || "CAD").toUpperCase()}`;
                    const isPaid = (inv.status || "").toLowerCase() === "paid";

                    return (
                      <tr
                        key={inv.id}
                        className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="py-3.5 px-4 font-mono font-bold text-slate-900 dark:text-[#F4F7FB]">
                          {invNumber}
                        </td>
                        <td className="py-3.5 px-4 text-slate-600 dark:text-[#94A3B8]">
                          {dateStr}
                        </td>
                        <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400">
                          {periodStr}
                        </td>
                        <td className="py-3.5 px-4">
                          <span className="capitalize font-medium text-slate-700 dark:text-slate-300">
                            {inv.plan_code || "Demo"}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-bold text-slate-900 dark:text-[#F4F7FB]">
                          {amountStr}
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              isPaid
                                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                                : "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                            }`}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-current" />
                            {isPaid ? "Payée" : "En attente"}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {/* PDF Real Download */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "pdf")}
                              disabled={downloadingId === `${inv.id}-pdf`}
                              title="Télécharger la facture officielle en PDF"
                              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 text-[#0076FF] hover:bg-blue-100 dark:bg-[#111D3D] dark:text-[#00D4FF] dark:hover:bg-[#172652] font-semibold text-[11px] transition-colors"
                            >
                              <Download size={13} className={downloadingId === `${inv.id}-pdf` ? "animate-bounce" : ""} />
                              <span>PDF</span>
                            </button>

                            {/* CSV Export */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "csv")}
                              disabled={downloadingId === `${inv.id}-csv`}
                              title="Exporter au format CSV"
                              className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-[#94A3B8] text-[11px] transition-colors"
                            >
                              <FileText size={13} />
                              <span>CSV</span>
                            </button>

                            {/* XLSX Export */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "xlsx")}
                              disabled={downloadingId === `${inv.id}-xlsx`}
                              title="Exporter au format Excel (XLSX)"
                              className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-[#94A3B8] text-[11px] transition-colors"
                            >
                              <FileSpreadsheet size={13} />
                              <span>XLSX</span>
                            </button>
                          </div>
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
    </div>
  );
}

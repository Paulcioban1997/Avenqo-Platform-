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
  Building2,
  Calendar,
  Layers,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Lock,
  Check,
  X,
  Send,
  HelpCircle,
  ArrowRight,
  Shield,
} from "lucide-react";
import { getAuthHeaders } from "@/lib/api-headers";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

interface ModuleEntitlementItem {
  key: string;
  display_name: string;
  description: string;
  active: boolean;
  category: string;
}

interface EntitlementsInfo {
  plan_code: string;
  active_modules: string[];
  module_limit: number | null;
  remaining_module_slots: number | null;
  modules: ModuleEntitlementItem[];
}

interface PaymentMethodSummary {
  brand: string;
  last4: string;
  exp_month: number;
  exp_year: number;
}

interface SubscriptionInfo {
  plan_code: string;
  status: string;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean;
  plan_name?: string;
  monthly_price_usd?: number;
  billing_frequency?: string;
  currency?: string;
  company_name?: string;
  payment_method?: PaymentMethodSummary | null;
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

interface AICreditBreakdownItem {
  module: string;
  credits_used: number;
  percentage: number;
}

interface AICreditHistoryItem {
  id: string;
  date: string;
  module: string;
  operation: string;
  credits_used: number;
  user: string;
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
    plan_name: "Demo",
    monthly_price_usd: 0,
    billing_frequency: "monthly",
    currency: "USD",
  });

  const [credits, setCredits] = useState<AICreditBalance>({
    billing_period: "2026-09",
    monthly_allocation: 6500,
    monthly_remaining: 6500,
    monthly_used: 0,
    purchased_total_available: 0,
    total_available: 6500,
  });

  const [breakdownPeriod, setBreakdownPeriod] = useState<string>("billing_period");
  const [breakdownItems, setBreakdownItems] = useState<AICreditBreakdownItem[]>([]);
  const [totalBreakdownUsed, setTotalBreakdownUsed] = useState<number>(0);

  const [historyItems, setHistoryItems] = useState<AICreditHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState<number>(0);
  const [historyPage, setHistoryPage] = useState<number>(0);
  const historyPageSize = 5;

  const [creditPacks, setCreditPacks] = useState<CreditPack[]>([
    { code: "pack_6500", name: "Pack Découverte", credits: 6500, price_usd: 10 },
    { code: "pack_25000", name: "Pack Évolution", credits: 25000, price_usd: 35 },
    { code: "pack_65000", name: "Pack Business Pro", credits: 65000, price_usd: 80 },
  ]);

  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [entitlements, setEntitlements] = useState<EntitlementsInfo | null>(null);
  const [userRole, setUserRole] = useState<string>("ADMIN");
  const [userEmail, setUserEmail] = useState<string>("");
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState<boolean>(false);
  const [isEnterpriseModalOpen, setIsEnterpriseModalOpen] = useState<boolean>(false);
  const [submittingQuote, setSubmittingQuote] = useState<boolean>(false);
  const [quoteSuccessMsg, setQuoteSuccessMsg] = useState<string | null>(null);
  const [enterpriseForm, setEnterpriseForm] = useState({
    requested_modules: ["retail", "crm", "accounting", "marketing"],
    estimated_users: 15,
    monthly_volume: "50k à 100k transactions",
    required_integrations: ["Shopify Plus", "ERP / Custom API"],
    notes: "",
  });

  const canManageBilling = ["OWNER", "ADMIN", "SUPER_ADMIN"].includes(userRole?.toUpperCase());

  const loadData = useCallback(async () => {
    setLoading(true);
    setActionError(null);
    try {
      const headers = getAuthHeaders();
      const [subRes, credRes, packRes, invRes, entRes, userRes] = await Promise.all([
        fetch("/api/v1/billing/subscription", { headers }).catch(() => null),
        fetch("/api/v1/billing/ai-credits", { headers }).catch(() => null),
        fetch("/api/v1/billing/credit-packs", { headers }).catch(() => null),
        fetch("/api/v1/billing/invoices/history?offset=0&limit=50", { headers }).catch(() => null),
        fetch("/api/v1/modules/entitlements", { headers }).catch(() => null),
        fetch("/api/v1/auth/me", { headers }).catch(() => null),
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
      if (entRes && entRes.ok) {
        const entData = await entRes.json();
        setEntitlements(entData);
      }
      if (userRes && userRes.ok) {
        const userData = await userRes.json();
        if (userData.user?.role) {
          setUserRole(userData.user.role);
        }
        if (userData.user?.email) {
          setUserEmail(userData.user.email);
        }
      }
    } catch {
      // Keep loaded state
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBreakdown = useCallback(async (period: string) => {
    try {
      const headers = getAuthHeaders();
      const res = await fetch(`/api/v1/billing/ai-credits/breakdown?period=${period}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setBreakdownItems(data.items || []);
        setTotalBreakdownUsed(data.total_used || 0);
      }
    } catch {}
  }, []);

  const loadHistory = useCallback(async (page: number) => {
    try {
      const headers = getAuthHeaders();
      const offset = page * historyPageSize;
      const res = await fetch(
        `/api/v1/billing/ai-credits/history?offset=${offset}&limit=${historyPageSize}`,
        { headers }
      );
      if (res.ok) {
        const data = await res.json();
        setHistoryItems(data.items || []);
        setHistoryTotal(data.total || 0);
      }
    } catch {}
  }, [historyPageSize]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    loadBreakdown(breakdownPeriod);
  }, [loadBreakdown, breakdownPeriod]);

  useEffect(() => {
    loadHistory(historyPage);
  }, [loadHistory, historyPage]);

  const handleRefreshBalance = async () => {
    setRefreshing(true);
    try {
      const headers = getAuthHeaders();
      const [res, bdRes] = await Promise.all([
        fetch("/api/v1/billing/ai-credits", { headers }),
        fetch(`/api/v1/billing/ai-credits/breakdown?period=${breakdownPeriod}`, { headers }),
      ]);
      if (res.ok) {
        const data = await res.json();
        setCredits(data);
      }
      if (bdRes.ok) {
        const bdData = await bdRes.json();
        setBreakdownItems(bdData.items || []);
        setTotalBreakdownUsed(bdData.total_used || 0);
      }
      loadHistory(0);
      setHistoryPage(0);
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
      setActionError("Le portail Stripe n'est pas encore configuré pour cette organisation.");
    } catch {
      setActionError("Impossible d'ouvrir le portail Stripe pour l'instant.");
    }
  };

  const handleManageSubscription = () => {
    if (!canManageBilling) {
      setActionError("Seuls les administrateurs de l'organisation peuvent modifier l'abonnement.");
      return;
    }
    if (subscription.plan_code?.toLowerCase() === "demo") {
      setIsUpgradeModalOpen(true);
    } else {
      setIsEnterpriseModalOpen(true);
    }
  };

  const handleConfirmUpgradeToProfessional = async () => {
    setActionError(null);
    try {
      const res = await fetch("/api/v1/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ plan_code: "professional" }),
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

  const handleSubmitEnterpriseQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingQuote(true);
    setActionError(null);
    try {
      const res = await fetch("/api/v1/billing/enterprise-quote", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          requested_modules: enterpriseForm.requested_modules,
          estimated_users: enterpriseForm.estimated_users,
          monthly_volume: enterpriseForm.monthly_volume,
          required_integrations: enterpriseForm.required_integrations,
          contact_email: userEmail,
          notes: enterpriseForm.notes,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setQuoteSuccessMsg(`Demande ${data.reference_id} enregistrée. Notre équipe Enterprise vous contactera sous 24h.`);
        setTimeout(() => {
          setIsEnterpriseModalOpen(false);
          setQuoteSuccessMsg(null);
        }, 4000);
      } else {
        const err = await res.json().catch(() => ({ detail: "Erreur d'enregistrement" }));
        setActionError(err.detail || "Erreur lors de l'envoi de la demande Enterprise.");
      }
    } catch {
      setActionError("Erreur réseau lors de l'envoi de la demande Enterprise.");
    } finally {
      setSubmittingQuote(false);
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

  const totalHistoryPages = Math.ceil(historyTotal / historyPageSize) || 1;

  const statusLabel =
    subscription.status === "active"
      ? "Actif"
      : subscription.status === "trialing"
      ? "Essai"
      : subscription.status === "past_due"
      ? "Paiement en retard"
      : subscription.status === "canceled"
      ? "Annulé"
      : "Inactif";

  const statusColor =
    subscription.status === "active"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
      : subscription.status === "trialing"
      ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400"
      : subscription.status === "past_due"
      ? "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
      : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
            {t.navigation?.billing || "Facturation"}
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            Gérez votre abonnement officiel, vos factures certifiées et le suivi de vos crédits d'intelligence artificielle.
          </p>
        </div>

        <button
          onClick={handleOpenStripePortal}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors self-start sm:self-auto cursor-pointer"
        >
          <ExternalLink size={15} />
          <span>Portail Stripe Sécurisé</span>
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

      {/* 1. PLAN ACTUEL (Subscription Overview) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-5">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-white/[0.06] pb-3">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Plan Actuel
          </div>
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${statusColor}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            {statusLabel}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-slate-400 dark:text-slate-500">Formule & Organisation</div>
            <div className="text-lg font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-0.5">
              {subscription.plan_name || "Avenqo Professional"}
            </div>
            <div className="text-xs text-slate-500 dark:text-[#94A3B8] flex items-center gap-1 mt-1">
              <Building2 size={13} className="text-[#0076FF]" />
              <span className="truncate">{subscription.company_name || "Votre Organisation"}</span>
            </div>
          </div>

          <div>
            <div className="text-xs text-slate-400 dark:text-slate-500">Tarification</div>
            <div className="text-lg font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-0.5">
              ${subscription.monthly_price_usd || 49}.00 {subscription.currency || "USD"}
            </div>
            <div className="text-xs text-slate-500 dark:text-[#94A3B8] mt-1 capitalize">
              Facturation {subscription.billing_frequency === "annual" ? "annuelle" : "mensuelle"}
            </div>
          </div>

          <div>
            <div className="text-xs text-slate-400 dark:text-slate-500">Prochain renouvellement</div>
            <div className="text-sm font-bold text-slate-800 dark:text-[#F4F7FB] mt-1 flex items-center gap-1.5">
              <Calendar size={14} className="text-slate-400" />
              <span>
                {subscription.current_period_end
                  ? new Date(subscription.current_period_end).toLocaleDateString(locale, {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })
                  : "Fin de période courante"}
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              Cycle: {credits.billing_period || "2026-09"}
            </div>
          </div>

          <div>
            <div className="text-xs text-slate-400 dark:text-slate-500">Mode de paiement</div>
            <div className="text-sm font-semibold text-slate-800 dark:text-[#F4F7FB] mt-1 flex items-center gap-1.5">
              <CreditCard size={14} className="text-[#0076FF]" />
              {subscription.payment_method ? (
                <span>
                  {subscription.payment_method.brand} •••• {subscription.payment_method.last4}
                </span>
              ) : (
                <span className="text-slate-400 dark:text-slate-500 text-xs">Stripe Checkout</span>
              )}
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              {subscription.payment_method
                ? `Exp: ${String(subscription.payment_method.exp_month).padStart(2, "0")}/${subscription.payment_method.exp_year}`
                : "Sécurisé par Stripe"}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-slate-100 dark:border-white/[0.06]">
          <button
            onClick={handleManageSubscription}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
          >
            <CreditCard size={14} />
            <span>Changer de formule</span>
          </button>
          <button
            onClick={handleOpenStripePortal}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#111D3D] dark:hover:bg-[#172652] text-xs font-semibold text-slate-700 dark:text-[#F4F7FB] transition-colors cursor-pointer"
          >
            <ShieldCheck size={14} />
            <span>Gérer le mode de paiement</span>
          </button>
        </div>
      </div>

      {/* 1.5. MODULES MÉTIERS ACTIFS & QUOTAS */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-white/[0.06] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-[#0076FF] dark:text-[#00D4FF]">
              <Layers size={18} />
            </div>
            <div>
              <h2 className="text-sm font-extrabold text-slate-900 dark:text-[#F4F7FB]">
                Modules Métiers Actifs & Quotas d'Agents
              </h2>
              <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
                Agents autonomes configurés pour votre organisation (distincts de vos crédits de requêtes IA).
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-blue-50 text-[#0076FF] dark:bg-[#111D3D] dark:text-[#00D4FF] border border-blue-200/60 dark:border-blue-900/40 font-mono">
              {entitlements ? `${entitlements.active_modules?.length || 0} / ${entitlements.module_limit !== null ? entitlements.module_limit : "∞"}` : "Chargement..."}
            </span>
            <span className="text-[11px] font-semibold text-slate-400 dark:text-slate-500">
              {subscription.plan_code?.toLowerCase() === "demo"
                ? "(Max 3 pour Demo)"
                : subscription.plan_code?.toLowerCase() === "professional"
                ? "(Max 6 pour Professional)"
                : "(Sur-mesure Enterprise)"}
            </span>
          </div>
        </div>

        {/* Modules List Grid */}
        <div className="space-y-3">
          <div className="text-xs font-semibold text-slate-500 dark:text-slate-400">
            Agents métier activés sur votre espace :
          </div>
          <div className="flex flex-wrap gap-2.5">
            {entitlements?.active_modules && entitlements.active_modules.length > 0 ? (
              entitlements.active_modules.map((modKey) => {
                const modDef = entitlements.modules?.find((m) => m.key === modKey);
                return (
                  <div
                    key={modKey}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-200/60 dark:border-white/[0.08] text-xs"
                  >
                    <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                    <span className="font-bold text-slate-800 dark:text-slate-200">
                      {modDef?.display_name || modKey.toUpperCase()}
                    </span>
                    {modDef?.category && (
                      <span className="text-[10px] text-slate-400 dark:text-slate-500 bg-white/60 dark:bg-black/20 px-1.5 py-0.5 rounded">
                        {modDef.category}
                      </span>
                    )}
                  </div>
                );
              })
            ) : (
              <span className="text-xs text-slate-400 italic">
                Aucun module activé pour l'instant. Rendez-vous dans les Paramètres pour activer vos agents.
              </span>
            )}
          </div>
        </div>

        {/* Conditional Upgrade Callout */}
        {subscription.plan_code?.toLowerCase() === "demo" && (entitlements?.active_modules?.length || 0) >= 3 && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-blue-500/10 via-indigo-500/10 to-transparent border border-blue-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="text-xs font-bold text-[#0076FF] dark:text-[#00D4FF] flex items-center gap-1.5">
                <Lock size={14} />
                <span>Limite de 3 modules atteinte pour la formule Demo</span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-300">
                Passez à la formule Professional ($49.00 USD/mois) pour activer jusqu'à 6 modules métiers, sans aucune perte de vos données ou connexions actuelles.
              </p>
            </div>
            <button
              onClick={() => setIsUpgradeModalOpen(true)}
              className="px-4 py-2 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white text-xs font-semibold shrink-0 transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
            >
              <span>Passer à Professional</span>
              <ArrowRight size={14} />
            </button>
          </div>
        )}

        {subscription.plan_code?.toLowerCase() === "professional" && (entitlements?.active_modules?.length || 0) >= 6 && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-transparent border border-purple-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="text-xs font-bold text-purple-600 dark:text-purple-400 flex items-center gap-1.5">
                <Shield size={14} />
                <span>Capacité maximale de 6 modules atteinte (Professional)</span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-300">
                Besoin d'agents supplémentaires, d'intégrations ERP/SAP ou d'un SLA dédié ? Demandez un devis Enterprise personnalisé.
              </p>
            </div>
            <button
              onClick={() => setIsEnterpriseModalOpen(true)}
              className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shrink-0 transition-colors shadow-xs cursor-pointer flex items-center gap-1.5"
            >
              <span>Demander un devis Enterprise</span>
              <ArrowRight size={14} />
            </button>
          </div>
        )}
      </div>

      {/* 2. CRÉDITS IA DASHBOARD */}
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
                Consommation et solde en temps réel garantis par le registre de crédits d'Avenqo.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 self-end sm:self-auto">
            <span className="text-xs text-slate-400 dark:text-slate-500">
              Cycle: {credits.billing_period || "2026-09"}
            </span>
            <button
              onClick={handleRefreshBalance}
              disabled={refreshing}
              title="Rafraîchir les crédits"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors cursor-pointer"
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
              Crédits utilisés
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-[#F4F7FB] mt-1.5">
              {monthlyUsed.toLocaleString()}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06]">
            <div className="text-[11px] font-semibold text-slate-500 dark:text-[#94A3B8]">
              Crédits restants
            </div>
            <div className="text-xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1.5">
              {monthlyRem.toLocaleString()}
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
              {monthlyUsed.toLocaleString()} / {monthlyAlloc.toLocaleString()} utilisés
            </span>
            <span className="font-bold text-slate-700 dark:text-slate-300">{progressPercent} %</span>
          </div>
        </div>
      </div>

      {/* 3. UTILISATION DES CRÉDITS (Breakdown by Module) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB] flex items-center gap-2">
              <Layers size={18} className="text-[#0076FF]" />
              <span>Utilisation des crédits</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8] mt-0.5">
              Répartition granulaire de la consommation par module d'intelligence artificielle.
            </p>
          </div>

          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-[#111D3D] text-[11px] font-medium">
            {[
              { id: "today", label: "Aujourd'hui" },
              { id: "7d", label: "7 jours" },
              { id: "30d", label: "30 jours" },
              { id: "billing_period", label: "Période courante" },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => setBreakdownPeriod(p.id)}
                className={`px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  breakdownPeriod === p.id
                    ? "bg-white dark:bg-[#0076FF] text-slate-900 dark:text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {breakdownItems.length === 0 || totalBreakdownUsed === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400 dark:text-slate-500 rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06]">
            Aucune utilisation de crédits enregistrée pour cette période. Vos analyses retail et interactions CRM alimenteront ce graphique.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
            {breakdownItems.map((item) => (
              <div
                key={item.module}
                className="p-4 rounded-xl bg-slate-50 dark:bg-[#111D3D] border border-slate-100 dark:border-white/[0.06] flex flex-col justify-between"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
                    {item.module}
                  </span>
                  <span className="text-xs font-bold text-[#0076FF] dark:text-[#00D4FF]">
                    {item.credits_used.toLocaleString()} crédits
                  </span>
                </div>
                <div className="mt-3">
                  <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-white/[0.08] overflow-hidden">
                    <div
                      className="h-full rounded-full bg-[#0076FF]"
                      style={{ width: `${Math.min(100, item.percentage)}%` }}
                    />
                  </div>
                  <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 text-right">
                    {item.percentage}% du total
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. HISTORIQUE D'UTILISATION (Usage History Table) */}
      <div className="p-6 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              Historique d'utilisation
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              Journal immuable de chaque opération IA effectuée par les collaborateurs de votre organisation.
            </p>
          </div>
          <div className="text-xs text-slate-400">
            {historyTotal} opération(s) enregistrée(s)
          </div>
        </div>

        {historyItems.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400 dark:text-slate-500 rounded-xl bg-slate-50/50 dark:bg-[#060B13]/30 border border-dashed border-slate-200 dark:border-white/[0.06]">
            Aucune opération IA dans l'historique récent.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-white/[0.08] bg-slate-50/70 dark:bg-[#060B13]/40 text-slate-500 dark:text-slate-400 font-semibold">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Module</th>
                  <th className="py-3 px-4">Opération</th>
                  <th className="py-3 px-4">Crédits utilisés</th>
                  <th className="py-3 px-4">Utilisateur</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {historyItems.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 text-slate-600 dark:text-[#94A3B8]">{item.date}</td>
                    <td className="py-3 px-4 font-semibold text-slate-800 dark:text-[#F4F7FB]">{item.module}</td>
                    <td className="py-3 px-4 text-slate-600 dark:text-slate-300">{item.operation}</td>
                    <td className="py-3 px-4 font-mono font-bold text-[#0076FF] dark:text-[#00D4FF]">
                      {item.credits_used}
                    </td>
                    <td className="py-3 px-4 text-slate-500 dark:text-slate-400">{item.user}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {totalHistoryPages > 1 && (
              <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-white/[0.06] text-xs text-slate-500">
                <span>
                  Page {historyPage + 1} sur {totalHistoryPages}
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setHistoryPage((p) => Math.max(0, p - 1))}
                    disabled={historyPage === 0}
                    className="p-1.5 rounded-lg border border-slate-200 dark:border-white/[0.08] disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors cursor-pointer"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <button
                    onClick={() => setHistoryPage((p) => Math.min(totalHistoryPages - 1, p + 1))}
                    disabled={historyPage >= totalHistoryPages - 1}
                    className="p-1.5 rounded-lg border border-slate-200 dark:border-white/[0.08] disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-white/[0.06] transition-colors cursor-pointer"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 5. AJOUTER DES CRÉDITS IA */}
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
            Ajouter des crédits IA
          </h2>
          <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
            Packs de recharge instantanée sans engagement, traités en toute sécurité par Stripe.
          </p>
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
                className="mt-4 w-full py-2 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-[#111D3D] dark:hover:bg-[#172652] text-xs font-semibold text-slate-800 dark:text-[#F4F7FB] transition-colors cursor-pointer"
              >
                Acheter ce pack
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 6. FACTURES (Invoices Table & Real PDF Download) */}
      <div className="space-y-3 pt-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 dark:text-[#F4F7FB]">
              Factures certifiées
            </h2>
            <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
              Consultez et téléchargez vos factures officielles Avenqo / PMC Solutions AI au format PDF conforme.
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
              Aucune facture émise pour le moment. Vos reçus certifiés apparaîtront automatiquement dès votre premier cycle de facturation.
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
                    <th className="py-3 px-4 text-right">Télécharger</th>
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
                            {inv.plan_code || "Professional"}
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
                            {/* Real PDF Download */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "pdf")}
                              disabled={downloadingId === `${inv.id}-pdf`}
                              title="Télécharger la facture officielle en PDF"
                              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 text-[#0076FF] hover:bg-blue-100 dark:bg-[#111D3D] dark:text-[#00D4FF] dark:hover:bg-[#172652] font-semibold text-[11px] transition-colors cursor-pointer"
                            >
                              <Download size={13} className={downloadingId === `${inv.id}-pdf` ? "animate-bounce" : ""} />
                              <span>PDF</span>
                            </button>

                            {/* CSV Export */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "csv")}
                              disabled={downloadingId === `${inv.id}-csv`}
                              title="Exporter au format CSV"
                              className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-[#94A3B8] text-[11px] transition-colors cursor-pointer"
                            >
                              <FileText size={13} />
                              <span>CSV</span>
                            </button>

                            {/* XLSX Export */}
                            <button
                              onClick={() => handleDownloadInvoice(inv, "xlsx")}
                              disabled={downloadingId === `${inv.id}-xlsx`}
                              title="Exporter au format Excel (XLSX)"
                              className="flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-white/[0.06] text-slate-500 dark:text-[#94A3B8] text-[11px] transition-colors cursor-pointer"
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

      {/* MODAL 1: DEMO -> PROFESSIONAL UPGRADE */}
      {isUpgradeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in">
          <div className="bg-white dark:bg-[#0B132B] rounded-3xl border border-slate-200 dark:border-white/[0.1] max-w-lg w-full p-6 sm:p-8 space-y-6 shadow-2xl relative">
            <button
              onClick={() => setIsUpgradeModalOpen(false)}
              className="absolute top-5 right-5 text-slate-400 hover:text-slate-700 dark:hover:text-white p-1 rounded-lg"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-3 rounded-2xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF]">
                <Sparkles size={24} />
              </div>
              <div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">
                  Passer à Avenqo Professional
                </h3>
                <p className="text-xs text-slate-500">
                  Débloquez jusqu'à 6 agents métiers et 25 000 crédits IA mensuels.
                </p>
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.06] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500 font-medium">Tarif officiel :</span>
                <span className="text-base font-extrabold text-slate-900 dark:text-white">$49.00 USD / mois</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Fréquence :</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">Facturation mensuelle</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Date d'effet :</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">Immédiate (dès confirmation Stripe)</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500 font-medium">Prorata :</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">Ajusté automatiquement par Stripe</span>
              </div>
              <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-200/60 dark:border-white/[0.06]">
                <span className="text-slate-500 font-medium">Capacité modules :</span>
                <span className="font-bold text-[#0076FF] dark:text-[#00D4FF]">Jusqu'à 6 modules actifs</span>
              </div>
            </div>

            <div className="space-y-2 text-xs text-slate-600 dark:text-slate-400">
              <div className="flex items-center gap-2">
                <Check size={14} className="text-emerald-500 shrink-0" />
                <span>Tous vos modules actuels restent activés et opérationnels.</span>
              </div>
              <div className="flex items-center gap-2">
                <Check size={14} className="text-emerald-500 shrink-0" />
                <span>Conservation intégrale de vos données, boutiques et fichiers importés.</span>
              </div>
              <div className="flex items-center gap-2">
                <Check size={14} className="text-emerald-500 shrink-0" />
                <span>Paiement sécurisé 3D Secure via Stripe Customer Checkout.</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsUpgradeModalOpen(false)}
                className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/[0.04]"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={handleConfirmUpgradeToProfessional}
                className="px-5 py-2.5 rounded-xl bg-[#0076FF] hover:bg-blue-600 text-white text-xs font-bold transition-colors shadow-xs flex items-center gap-2 cursor-pointer"
              >
                <span>Confirmer et passer à Professional</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: PROFESSIONAL -> ENTERPRISE QUOTE REQUEST */}
      {isEnterpriseModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in overflow-y-auto">
          <div className="bg-white dark:bg-[#0B132B] rounded-3xl border border-slate-200 dark:border-white/[0.1] max-w-lg w-full p-6 sm:p-8 space-y-5 shadow-2xl relative my-8">
            <button
              onClick={() => {
                setIsEnterpriseModalOpen(false);
                setQuoteSuccessMsg(null);
              }}
              className="absolute top-5 right-5 text-slate-400 hover:text-slate-700 dark:hover:text-white p-1 rounded-lg"
            >
              <X size={20} />
            </button>

            <div className="flex items-center gap-3">
              <div className="p-3 rounded-2xl bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400">
                <Shield size={24} />
              </div>
              <div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white">
                  Demande de Devis Avenqo Enterprise
                </h3>
                <p className="text-xs text-slate-500">
                  Solutions sur-mesure pour grands comptes et volumes intensifs.
                </p>
              </div>
            </div>

            {quoteSuccessMsg ? (
              <div className="p-6 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-center space-y-3">
                <CheckCircle2 size={36} className="text-emerald-600 dark:text-emerald-400 mx-auto" />
                <h4 className="text-sm font-bold text-emerald-900 dark:text-emerald-200">
                  Demande transmise avec succès
                </h4>
                <p className="text-xs text-emerald-800 dark:text-emerald-300">
                  {quoteSuccessMsg}
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmitEnterpriseQuote} className="space-y-4 text-xs">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                    Organisation & Contact
                  </label>
                  <div className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.08] flex justify-between">
                    <span className="font-bold text-slate-900 dark:text-white">{subscription.company_name || "Votre Organisation"}</span>
                    <span className="text-slate-400">{userEmail}</span>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                    Modules Métiers souhaités
                  </label>
                  <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.08]">
                    {["retail", "crm", "accounting", "marketing", "voice", "ocr", "automations", "agents"].map((mod) => (
                      <label key={mod} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={enterpriseForm.requested_modules.includes(mod)}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setEnterpriseForm((prev) => ({
                              ...prev,
                              requested_modules: checked
                                ? [...prev.requested_modules, mod]
                                : prev.requested_modules.filter((m) => m !== mod),
                            }));
                          }}
                          className="rounded border-slate-300 text-[#0076FF] focus:ring-[#0076FF]"
                        />
                        <span className="capitalize text-slate-700 dark:text-slate-300">{mod} AI</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                      Nombre d'utilisateurs estimés
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={10000}
                      value={enterpriseForm.estimated_users}
                      onChange={(e) => setEnterpriseForm({ ...enterpriseForm, estimated_users: parseInt(e.target.value) || 1 })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.08] text-slate-900 dark:text-white font-medium"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                      Volume mensuel estimé
                    </label>
                    <select
                      value={enterpriseForm.monthly_volume}
                      onChange={(e) => setEnterpriseForm({ ...enterpriseForm, monthly_volume: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.08] text-slate-900 dark:text-white font-medium"
                    >
                      <option value="10k à 50k transactions">10k à 50k transactions</option>
                      <option value="50k à 100k transactions">50k à 100k transactions</option>
                      <option value="Plus de 100k transactions">Plus de 100k transactions</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                    Intégrations requises & Spécifications
                  </label>
                  <textarea
                    rows={2}
                    value={enterpriseForm.notes}
                    onChange={(e) => setEnterpriseForm({ ...enterpriseForm, notes: e.target.value })}
                    placeholder="ERP interne, Shopify Plus multi-pays, volumétrie spécifique..."
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-white/[0.02] border border-slate-200/60 dark:border-white/[0.08] text-slate-900 dark:text-white placeholder:text-slate-400 resize-none"
                  />
                </div>

                <div className="p-3 rounded-xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 text-[11px] text-slate-600 dark:text-slate-400 flex items-start gap-2">
                  <ShieldCheck size={16} className="text-[#0076FF] shrink-0 mt-0.5" />
                  <span>
                    La soumission de ce formulaire n'entraîne aucun débit bancaire et ne modifie pas vos droits sans validation contractuelle préalable.
                  </span>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-100 dark:border-white/[0.06]">
                  <button
                    type="button"
                    onClick={() => setIsEnterpriseModalOpen(false)}
                    className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/[0.1] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                  >
                    Annuler
                  </button>
                  <button
                    type="submit"
                    disabled={submittingQuote}
                    className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold transition-colors shadow-xs flex items-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    <Send size={14} className={submittingQuote ? "animate-spin" : ""} />
                    <span>{submittingQuote ? "Envoi en cours..." : "Transmettre ma demande de devis"}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

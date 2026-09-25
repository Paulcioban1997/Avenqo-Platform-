"use client";

import React, { useState, useEffect } from "react";
import {
  DollarSign,
  ShoppingCart,
  Users,
  TrendingUp,
  Percent,
  Sparkles,
  Calendar,
  ChevronDown,
  RefreshCw,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  MapPin,
  PieChart as PieIcon,
  HelpCircle,
} from "lucide-react";
import { MetricCard, AvenqoCard, StatusBadge } from "@/components/ui/avenqo-card";
import { KPISkeleton, ChartSkeleton, AIInsightSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/status-states";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getAuthHeaders } from "@/lib/api-headers";

export interface DashboardViewProps {
  tenantName?: string;
  userName?: string;
}

interface DashboardKPI {
  key: string;
  value: number | null;
  previous_value?: number | null;
  change_percent?: number | null;
  currency?: string | null;
  available: boolean;
}

interface DashboardPriority {
  id: string;
  title: string;
  explanation: string;
  suggested_action: string;
  severity: string;
  source_capability: string;
}

interface DashboardTrendPoint {
  period: string;
  revenue: number;
  orders: number;
}

export function DashboardView({
  tenantName = "",
  userName = "",
}: DashboardViewProps) {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);

  const [dateRange, setDateRange] = useState<"all" | "7d" | "30d" | "quarter">("30d");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kpis, setKpis] = useState<Record<string, DashboardKPI>>({});
  const [priorities, setPriorities] = useState<DashboardPriority[]>([]);
  const [trendPoints, setTrendPoints] = useState<DashboardTrendPoint[]>([]);
  const [currency, setCurrency] = useState("CAD");
  const [hoveredTrendIdx, setHoveredTrendIdx] = useState<number | null>(null);
  const [userFirstName, setUserFirstName] = useState<string>(userName);
  const [currentTenant, setCurrentTenant] = useState<string>(tenantName);

  // Dynamic greeting based on current local hour
  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return t.dashboard.greetingMorning;
    if (hour < 18) return t.dashboard.greetingAfternoon;
    return t.dashboard.greetingEvening;
  })();

  const fetchDashboardData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const headers = getAuthHeaders();
      const periodKey = {
        all: "all",
        "7d": "last_7_days",
        "30d": "last_30_days",
        quarter: "current_quarter",
      }[dateRange];
      const [res, meRes, salesRes] = await Promise.all([
        fetch(`/api/v1/dashboard?period=${periodKey}`, { headers }),
        fetch("/api/v1/auth/me", { headers }),
        fetch(`/api/v1/sales/summary?period=${periodKey}`, { headers }).catch(() => null),
      ]);

      if (meRes.ok) {
        const meData = await meRes.json();
        if (meData.user?.first_name) {
          setUserFirstName(meData.user.first_name);
        }
        if (meData.company?.name) {
          setCurrentTenant(meData.company.name);
        }
      }

      if (res.ok) {
        const data = await res.json();
        setCurrency(data.company?.currency || "CAD");
        if (Array.isArray(data.kpis)) {
          const mapped: Record<string, DashboardKPI> = {};
          data.kpis.forEach((k: DashboardKPI) => {
            mapped[k.key] = k;
          });
          setKpis(mapped);
        }
        if (Array.isArray(data.priorities)) {
          setPriorities(data.priorities);
        }
        if (salesRes?.ok) {
          const salesData = await salesRes.json();
          const points = salesData.trend?.points;
          setTrendPoints(Array.isArray(points) ? points : []);
        } else {
          setTrendPoints([]);
        }
      } else {
        // Empty state when unauthenticated or tenant has no calculated records
        setKpis({});
        setPriorities([]);
        setTrendPoints([]);
      }
    } catch {
      // Network or gateway unreached: keep empty state with zero fake data
      setKpis({});
      setPriorities([]);
      setTrendPoints([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [dateRange]);

  // Unified chart timeline points derived strictly from actual data availability
  const hasData = Object.keys(kpis).length > 0 && Object.values(kpis).some((k) => k.available);
  const periodLabel = {
    all: t.dashboard.dateRangeAll,
    "7d": t.dashboard.dateRange7d,
    "30d": t.dashboard.dateRange30d,
    quarter: t.dashboard.dateRangeQuarter,
  }[dateRange];

  // Format currency helper
  const formatMoney = (val: number | null | undefined) => {
    if (val === null || val === undefined) return "—";
    return new Intl.NumberFormat(locale === "fr" ? "fr-CA" : "en-CA", {
      style: "currency",
      currency: currency || "CAD",
      maximumFractionDigits: 0,
    }).format(val);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-in fade-in duration-200">
      {/* Dynamic Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
              {greeting}{userFirstName ? `, ${userFirstName}` : ""}
            </h1>
            {currentTenant && (
              <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 dark:bg-[#0076FF]/15 dark:text-[#00D4FF] border border-blue-200 dark:border-[#0076FF]/30">
                {currentTenant}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            {t.dashboard.trendSubtitle}
          </p>
        </div>

        {/* Date Range Picker Controls */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-xl p-1 bg-slate-100 dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] text-xs">
            <button
              onClick={() => setDateRange("all")}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
                dateRange === "all"
                  ? "bg-white dark:bg-[#172652] text-slate-900 dark:text-[#F4F7FB] shadow-2xs"
                  : "text-slate-600 dark:text-[#94A3B8] hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              {t.dashboard.dateRangeAll}
            </button>
            <button
              onClick={() => setDateRange("7d")}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
                dateRange === "7d"
                  ? "bg-white dark:bg-[#172652] text-slate-900 dark:text-[#F4F7FB] shadow-2xs"
                  : "text-slate-600 dark:text-[#94A3B8] hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              {t.dashboard.dateRange7d}
            </button>
            <button
              onClick={() => setDateRange("30d")}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
                dateRange === "30d"
                  ? "bg-white dark:bg-[#172652] text-slate-900 dark:text-[#F4F7FB] shadow-2xs"
                  : "text-slate-600 dark:text-[#94A3B8] hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              {t.dashboard.dateRange30d}
            </button>
            <button
              onClick={() => setDateRange("quarter")}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-colors ${
                dateRange === "quarter"
                  ? "bg-white dark:bg-[#172652] text-slate-900 dark:text-[#F4F7FB] shadow-2xs"
                  : "text-slate-600 dark:text-[#94A3B8] hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              {t.dashboard.dateRangeQuarter}
            </button>
          </div>

          <button
            onClick={fetchDashboardData}
            aria-label="Actualiser les métriques"
            className="p-2 rounded-xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] hover:bg-slate-50 dark:hover:bg-[#172652] text-slate-600 dark:text-[#94A3B8] transition-colors"
            title="Actualiser"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* KPI Grid (5 Metrics) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {isLoading ? (
          <>
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
          </>
        ) : (
          <>
            {/* Chiffre d'affaires / Revenue */}
            <MetricCard
              title={t.dashboard.revenue}
              value={kpis.revenue?.available ? formatMoney(kpis.revenue.value) : "—"}
              delta={kpis.revenue?.change_percent ?? null}
              period={periodLabel}
              icon={<DollarSign className="w-4 h-4" />}
              badge="Live"
            />

            {/* Commandes / Orders */}
            <MetricCard
              title={t.dashboard.orders}
              value={kpis.orders?.available ? (kpis.orders.value ?? 0).toLocaleString() : "—"}
              delta={kpis.orders?.change_percent ?? null}
              period={periodLabel}
              icon={<ShoppingCart className="w-4 h-4" />}
            />

            {/* Clients / Customers */}
            <MetricCard
              title={t.dashboard.customers}
              value={kpis.customers?.available ? (kpis.customers.value ?? 0).toLocaleString() : "—"}
              delta={kpis.customers?.change_percent ?? null}
              period={periodLabel}
              icon={<Users className="w-4 h-4" />}
            />

            {/* Panier moyen / AOV */}
            <MetricCard
              title={t.dashboard.aov}
              value={kpis.aov?.available ? formatMoney(kpis.aov.value) : "—"}
              delta={kpis.aov?.change_percent ?? null}
              period={periodLabel}
              icon={<TrendingUp className="w-4 h-4" />}
            />

            {/* Taux de conversion */}
            <MetricCard
              title={t.dashboard.conversionRate}
              value={kpis.conversion_rate?.available ? `${(kpis.conversion_rate.value ?? 0).toFixed(1)}%` : "—"}
              delta={kpis.conversion_rate?.change_percent ?? null}
              period={periodLabel}
              icon={<Percent className="w-4 h-4" />}
            />
          </>
        )}
      </div>

      {/* Main Charts & Avenqo AI Insight Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Combined Trend Chart */}
        <div className="lg:col-span-2 space-y-6">
          <AvenqoCard variant="default" className="p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-4 border-b border-slate-100 dark:border-white/[0.06]">
              <div>
                <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
                  {t.dashboard.trendTitle}
                </h2>
                <p className="text-xs text-slate-500 dark:text-[#94A3B8]">
                  {t.dashboard.trendSubtitle}
                </p>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5 font-medium text-slate-600 dark:text-[#94A3B8]">
                  <span className="w-3 h-1 rounded-full bg-[#0076FF]" />
                  <span>{t.dashboard.revenue}</span>
                </div>
                <div className="flex items-center gap-1.5 font-medium text-slate-600 dark:text-[#94A3B8]">
                  <span className="w-3 h-1 rounded-full bg-[#00D4FF]" />
                  <span>{t.dashboard.orders}</span>
                </div>
              </div>
            </div>

            {/* Interactive SVG Chart or Empty State */}
            {isLoading ? (
              <ChartSkeleton height={240} />
            ) : hasData && trendPoints.length > 0 ? (
              <div className="relative pt-4">
                <div className="h-60 w-full flex items-end justify-between gap-3 pt-4">
                  {trendPoints.map((point, idx) => {
                    const maxRevenue = Math.max(...trendPoints.map((item) => item.revenue), 1);
                    const maxOrders = Math.max(...trendPoints.map((item) => item.orders), 1);
                    const revenueHeight = (point.revenue / maxRevenue) * 100;
                    const ordersHeight = (point.orders / maxOrders) * 100;
                    return (
                    <div
                      key={point.period}
                      onMouseEnter={() => setHoveredTrendIdx(idx)}
                      onMouseLeave={() => setHoveredTrendIdx(null)}
                      className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer"
                    >
                      {hoveredTrendIdx === idx && (
                        <div className="absolute top-0 px-2.5 py-1 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-[10px] font-bold shadow-md animate-in fade-in">
                          {point.period}: {formatMoney(point.revenue)} / {point.orders.toLocaleString()} {t.dashboard.orders.toLowerCase()}
                        </div>
                      )}
                      <div className="w-full max-w-[28px] flex items-end gap-1 h-full justify-center">
                        <div
                          className="w-1/2 rounded-t-md bg-[#0076FF] group-hover:bg-[#158bff] transition-all duration-300"
                          style={{ height: `${revenueHeight}%` }}
                        />
                        <div
                          className="w-1/2 rounded-t-md bg-[#00D4FF] group-hover:bg-cyan-300 transition-all duration-300"
                          style={{ height: `${ordersHeight}%` }}
                        />
                      </div>
                      <span className="mt-2 text-[11px] font-medium text-slate-400 group-hover:text-slate-700 dark:group-hover:text-white">
                        {point.period}
                      </span>
                    </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <EmptyState
                title="Aucune transaction à afficher"
                description="Synchronisez un connecteur e-commerce (WooCommerce, Shopify) pour tracer la courbe consolidée de vos ventes réelles."
                actionLabel="Gérer les intégrations"
                onAction={() => (window.location.href = "/integrations")}
                className="py-10"
              />
            )}
          </AvenqoCard>

          {/* Regional Sales & Category Breakdown */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* Donut Category Split */}
            <AvenqoCard variant="default" className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <PieIcon className="w-4 h-4 text-[#0076FF]" />
                  <h3 className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {t.dashboard.categorySplitTitle}
                  </h3>
                </div>
              </div>

              <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                Données de catégories indisponibles
              </div>
            </AvenqoCard>

            {/* Regional Distribution */}
            <AvenqoCard variant="default" className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-[#00D4FF]" />
                  <h3 className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {t.dashboard.regionalSalesTitle}
                  </h3>
                </div>
              </div>

              <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                Données géographiques indisponibles
              </div>
            </AvenqoCard>
          </div>
        </div>

        {/* Right Col: Cartouche "Avenqo AI Insight" */}
        <div className="space-y-6">
          <AvenqoCard
            variant="highlighted"
            className="p-6 relative overflow-hidden flex flex-col justify-between min-h-[380px]"
          >
            <div>
              {/* Header */}
              <div className="flex items-center justify-between pb-3 border-b border-blue-100 dark:border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-[#0076FF] to-[#00D4FF] text-white flex items-center justify-center shadow-xs">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB]">
                      {t.dashboard.aiInsightTitle}
                    </h3>
                    <span className="text-[10px] text-[#0076FF] dark:text-[#00D4FF] font-semibold">
                      Moteur Prédictif Multi-Agents
                    </span>
                  </div>
                </div>
                <StatusBadge status={priorities.length > 0 ? "active" : "pending"} size="sm" />
              </div>

              {/* Body */}
              {isLoading ? (
                <div className="py-6">
                  <AIInsightSkeleton />
                </div>
              ) : priorities.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {priorities.map((p) => (
                    <div
                      key={p.id}
                      className="p-3.5 rounded-xl bg-white/80 dark:bg-[#111D3D]/80 border border-slate-200/80 dark:border-white/[0.08] shadow-2xs space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB]">
                          {p.title}
                        </span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 dark:bg-[#0076FF]/20 dark:text-[#00D4FF]">
                          {p.severity}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-[#94A3B8] leading-relaxed">
                        {p.explanation}
                      </p>
                      {p.suggested_action && (
                        <div className="pt-2 border-t border-slate-100 dark:border-white/[0.06] text-[11px] font-semibold text-[#0076FF] dark:text-[#00D4FF] flex items-center gap-1">
                          <ArrowRight className="w-3 h-3" />
                          <span>{p.suggested_action}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                /* Strict Zero-Mock Rule: Display "Données insuffisantes pour analyse" */
                <div className="my-8 p-4 rounded-xl border border-dashed border-slate-200 dark:border-white/[0.08] text-center space-y-2 bg-slate-50/50 dark:bg-white/[0.02]">
                  <AlertCircle className="w-8 h-8 text-slate-400 mx-auto" />
                  <div className="text-xs font-bold text-slate-800 dark:text-[#F4F7FB]">
                    {t.dashboard.aiInsightInsufficient}
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                    {t.dashboard.aiInsightEmpty}
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="mt-4 pt-3 border-t border-blue-100 dark:border-white/[0.06] flex items-center justify-between text-xs text-slate-500 dark:text-[#94A3B8]">
              <div className="flex items-center gap-1.5 text-[11px]">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span>Raisonnement certifié</span>
              </div>
              <span className="text-[11px] font-semibold text-slate-600 dark:text-[#F4F7FB]">
                {periodLabel}
              </span>
            </div>
          </AvenqoCard>
        </div>
      </div>
    </div>
  );
}

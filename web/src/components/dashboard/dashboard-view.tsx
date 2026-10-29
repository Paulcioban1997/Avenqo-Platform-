"use client";

import React, { useState, useEffect, useRef } from "react";
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
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useSession } from "@/lib/session-context";
import { RequestFailure } from "@/components/ui/request-failure";
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
  type?: string;
  title: string;
  explanation: string;
  suggested_action: string;
  severity: string;
  source_capability: string;
  evidence?: { product_name?: string; change_percent?: number };
}

interface DashboardTrendPoint {
  period: string;
  revenue: number;
  orders: number;
}

interface DashboardSplitItem {
  label: string;
  revenue: number;
  orders: number;
  share: number;
}

interface DashboardSplit {
  available: boolean;
  reason?: string | null;
  items: DashboardSplitItem[];
}

interface DashboardConversion {
  available: boolean;
  reason?: string | null;
  value: number | null;
}

export function DashboardView({
  tenantName = "",
  userName = "",
}: DashboardViewProps) {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const application = getApplicationCatalog(locale);
  const company = application.company;
  const phase4d = application.phase4d;
  const dashboardHome = application.dashboardHome;
  const [greeting, setGreeting] = useState(t.dashboard.greetingMorning);

  const [dateRange, setDateRange] = useState<"all" | "7d" | "30d" | "quarter">("30d");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [kpis, setKpis] = useState<Record<string, DashboardKPI>>({});
  const [priorities, setPriorities] = useState<DashboardPriority[]>([]);
  const [trendPoints, setTrendPoints] = useState<DashboardTrendPoint[]>([]);
  const [categorySplit, setCategorySplit] = useState<DashboardSplit>({ available: false, items: [] });
  const [regionalSplit, setRegionalSplit] = useState<DashboardSplit>({ available: false, items: [] });
  const [conversion, setConversion] = useState<DashboardConversion>({ available: false, value: null });
  const [currency, setCurrency] = useState("CAD");
  const [hoveredTrendIdx, setHoveredTrendIdx] = useState<number | null>(null);
  const [calendarReconnectNeeded, setCalendarReconnectNeeded] = useState(false);
  const session = useSession();
  const loadRevision = useRef(0);
  const userFirstName = session.identity?.user.first_name ?? userName;
  const currentTenant = session.identity?.company.name ?? tenantName;

  useEffect(() => {
    const hour = new Date().getHours();
    setGreeting(
      hour < 12
        ? t.dashboard.greetingMorning
        : hour < 18
          ? t.dashboard.greetingAfternoon
          : t.dashboard.greetingEvening,
    );
  }, [t.dashboard.greetingAfternoon, t.dashboard.greetingEvening, t.dashboard.greetingMorning]);

  const fetchDashboardData = async () => {
    const revision = ++loadRevision.current;
    setIsLoading(true);
    setError(null);
    setKpis({});
    setPriorities([]);
    setTrendPoints([]);
    setCategorySplit({ available: false, items: [] });
    setRegionalSplit({ available: false, items: [] });
    setConversion({ available: false, value: null });
    try {
      const headers = getAuthHeaders();
      void apiFetch("/api/v1/crm/calendar/connection", { headers })
        .then(async (cRes) => {
          if (!cRes.ok) return;
          const cData = await cRes.json();
          const isStaleToken = Boolean(
            cData.requires_reconnect ||
            (!cData.connected && cData.provider === "google") ||
            cData.sync_status === "error" ||
            cData.sync_status === "revoked" ||
            (cData.last_synced_at && (Date.now() - new Date(cData.last_synced_at).getTime()) >= 6 * 86400000)
          );
          setCalendarReconnectNeeded(isStaleToken);
        })
        .catch(() => {});

      const periodKey = {
        all: "all",
        "7d": "last_7_days",
        "30d": "last_30_days",
        quarter: "current_quarter",
      }[dateRange];
      const res = await apiFetch(`/api/v1/dashboard?period=${periodKey}`, { headers });

      if (res.ok) {
        const data = await res.json();
        if (revision !== loadRevision.current) return;
        setCurrency(data.company?.currency || "CAD");
        if (Array.isArray(data.kpis)) {
          const mapped: Record<string, DashboardKPI> = {};
          data.kpis.forEach((k: DashboardKPI) => {
            mapped[k.key === "average_order_value" ? "aov" : k.key] = k;
          });
          setKpis(mapped);
        }
        if (Array.isArray(data.priorities)) {
          setPriorities(data.priorities);
        }
        const points = data.trend?.points;
        setTrendPoints(Array.isArray(points) ? points : []);
        setCategorySplit(data.category_split && Array.isArray(data.category_split.items)
          ? data.category_split
          : { available: false, items: [] });
        setRegionalSplit(data.regional_split && Array.isArray(data.regional_split.items)
          ? data.regional_split
          : { available: false, items: [] });
        setConversion(data.conversion && typeof data.conversion === "object"
          ? data.conversion
          : { available: false, value: null });
      }
    } catch (error) {
      if (revision === loadRevision.current) setError(error instanceof ApiRequestError ? error : new ApiRequestError("backend_error"));
    } finally {
      if (revision === loadRevision.current) setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    return () => { loadRevision.current++; };
  }, [dateRange, session.sourceRevision, session.identity?.company.id]);

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
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
  };

  if (error) return <RequestFailure error={error} retry={() => { void fetchDashboardData(); }} />;

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
            aria-label={company.employeesRefreshTooltip}
            className="p-2 rounded-xl bg-white dark:bg-[#111D3D] border border-slate-200/80 dark:border-white/[0.08] hover:bg-slate-50 dark:hover:bg-[#172652] text-slate-600 dark:text-[#94A3B8] transition-colors"
            title={company.employeesRefreshTooltip}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {calendarReconnectNeeded && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-in fade-in shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-sm font-bold text-amber-950 dark:text-amber-200">
                {locale.startsWith("fr")
                  ? "Reconnectez Google Calendar pour reprendre les réservations"
                  : "Reconnect Google Calendar to resume appointment booking"}
              </p>
              <p className="text-xs text-amber-800/90 dark:text-amber-300/80">
                {locale.startsWith("fr")
                  ? "Le jeton Google Calendar a expiré. Les disponibilités externes ne peuvent pas être vérifiées, suspendant la prise de rendez-vous."
                  : "Google Calendar token expired. External availability cannot be confirmed, pausing bookings."}
              </p>
            </div>
          </div>
          <a
            href="/crm?tab=connections"
            className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold transition shrink-0 flex items-center gap-1.5 shadow-sm"
          >
            <span>{locale.startsWith("fr") ? "Reconnecter" : "Reconnect"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </a>
        </div>
      )}

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
              delta={
                (kpis.orders?.value ?? 0) === 0 || (kpis.revenue?.value ?? 0) === 0
                  ? null
                  : (kpis.revenue?.change_percent ?? null)
              }
              period={periodLabel}
              icon={<DollarSign className="w-4 h-4" />}
            />

            {/* Commandes / Orders */}
            <MetricCard
              title={t.dashboard.orders}
              value={kpis.orders?.available ? (kpis.orders.value ?? 0).toLocaleString() : "—"}
              delta={
                (kpis.orders?.value ?? 0) === 0
                  ? null
                  : (kpis.orders?.change_percent ?? null)
              }
              period={periodLabel}
              icon={<ShoppingCart className="w-4 h-4" />}
            />

            {/* Clients / Customers */}
            <MetricCard
              title={t.dashboard.customers}
              value={kpis.customers?.available ? (kpis.customers.value ?? 0).toLocaleString() : "—"}
              delta={
                (kpis.orders?.value ?? 0) === 0 || (kpis.customers?.value ?? 0) === 0
                  ? null
                  : (kpis.customers?.change_percent ?? null)
              }
              period={periodLabel}
              icon={<Users className="w-4 h-4" />}
            />

            {/* Panier moyen / AOV */}
            <MetricCard
              title={t.dashboard.aov}
              value={kpis.aov?.available ? formatMoney(kpis.aov.value) : "—"}
              delta={
                (kpis.orders?.value ?? 0) === 0 || (kpis.aov?.value ?? 0) === 0
                  ? null
                  : (kpis.aov?.change_percent ?? null)
              }
              period={periodLabel}
              icon={<TrendingUp className="w-4 h-4" />}
            />

            {/* Taux de conversion */}
            <MetricCard
              title={t.dashboard.conversionRate}
              value={conversion.available && conversion.value != null ? `${conversion.value.toFixed(1)}%` : "—"}
              delta={
                (kpis.orders?.value ?? 0) === 0 || !conversion.available || (conversion.value ?? 0) === 0
                  ? null
                  : (kpis.conversion_rate?.change_percent ?? null)
              }
              period={conversion.available ? periodLabel : t.dashboard.conversionUnavailable}
              icon={<Percent className="w-4 h-4" />}
            />
          </>
        )}
      </div>

      {!isLoading && dateRange !== "all" && (kpis.orders?.value ?? 0) === 0 && (
        <div role="status" className="border-l-4 border-amber-500 bg-amber-50 dark:bg-amber-950/20 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
          {t.dashboard.noTransactionsForPeriod.replace("{period}", periodLabel)}
        </div>
      )}

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
              <div className="relative pt-4 overflow-x-auto">
                <div className="h-60 flex items-end gap-3 pt-4" style={{ minWidth: `${Math.max(trendPoints.length * 28, 100)}%` }}>
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
                title={t.dashboard.noTransactionsForPeriod.replace("{period}", periodLabel)}
                description={t.dashboard.aiInsightInsufficient}
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

              {isLoading ? (
                <ChartSkeleton height={120} />
              ) : categorySplit.available && categorySplit.items.length > 0 ? (
                <DashboardSplitList items={categorySplit.items} formatMoney={formatMoney} />
              ) : (
                <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                  {t.dashboard.categorySplitUnavailable}
                </div>
              )}
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

              {isLoading ? (
                <ChartSkeleton height={120} />
              ) : regionalSplit.available && regionalSplit.items.length > 0 ? (
                <DashboardSplitList items={regionalSplit.items} formatMoney={formatMoney} />
              ) : (
                <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                  {t.dashboard.regionalSalesUnavailable}
                </div>
              )}
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
                      {t.dashboard.aiInsightTitle}
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
                          {priorityTitle(p, dashboardHome, phase4d)}
                        </span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 dark:bg-[#0076FF]/20 dark:text-[#00D4FF]">
                          {prioritySeverity(p.severity, phase4d)}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600 dark:text-[#94A3B8] leading-relaxed">
                        {priorityExplanation(p, dashboardHome, phase4d)}
                      </p>
                      {p.suggested_action && (
                        <div className="pt-2 border-t border-slate-100 dark:border-white/[0.06] text-[11px] font-semibold text-[#0076FF] dark:text-[#00D4FF] flex items-center gap-1">
                          <ArrowRight className="w-3 h-3" />
                          <span>{priorityAction(p.suggested_action, phase4d, company)}</span>
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
                    {hasData ? t.dashboard.aiInsightNoPriority : t.dashboard.aiInsightInsufficient}
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-[#94A3B8]">
                    {!hasData && t.dashboard.aiInsightEmpty}
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="mt-4 pt-3 border-t border-blue-100 dark:border-white/[0.06] flex items-center justify-between text-xs text-slate-500 dark:text-[#94A3B8]">
              <div className="flex items-center gap-1.5 text-[11px]">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                <span>{t.dashboard.aiInsightConfidence}</span>
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

function DashboardSplitList({
  items,
  formatMoney,
}: {
  items: DashboardSplitItem[];
  formatMoney: (val: number | null | undefined) => string;
}) {
  const max = Math.max(...items.map((item) => item.revenue), 1);
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.label} className="space-y-1">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-semibold text-slate-800 dark:text-[#F4F7FB] truncate">{item.label}</span>
            <span className="shrink-0 text-slate-500 dark:text-[#94A3B8]">
              {formatMoney(item.revenue)} · {item.share.toFixed(1)}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-100 dark:bg-white/[0.06]">
            <div
              className="h-1.5 rounded-full bg-[#0076FF]"
              style={{ width: `${Math.max((item.revenue / max) * 100, 4)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function priorityTitle(
  priority: DashboardPriority,
  dashboardHome: { revenueDeclineTitle: string; revenueGrowthTitle: string },
  phase4d: {
    productDeclineTitle: string;
    productGrowthTitle: string;
    productConcentrationTitle: string;
    crossSellOpportunityTitle: string;
  },
) {
  const type = priority.type || priority.title;
  const productName = priority.evidence?.product_name;
  if (type === "revenue_decline") return dashboardHome.revenueDeclineTitle;
  if (type === "revenue_growth") return dashboardHome.revenueGrowthTitle;
  if (type === "product_decline") {
    return productName ? `${phase4d.productDeclineTitle} — ${productName}` : phase4d.productDeclineTitle;
  }
  if (type === "product_growth") {
    return productName ? `${phase4d.productGrowthTitle} — ${productName}` : phase4d.productGrowthTitle;
  }
  if (type === "product_concentration") {
    return productName ? `${phase4d.productConcentrationTitle} — ${productName}` : phase4d.productConcentrationTitle;
  }
  if (type === "cross_sell_opportunity") return phase4d.crossSellOpportunityTitle;
  return priority.title;
}

function priorityExplanation(
  priority: DashboardPriority,
  dashboardHome: { revenueChangedExplanation: string },
  phase4d: { productRevenueChangedExplanation: string; productConcentrationExplanation: string; crossSellOpportunityExplanation: string },
) {
  const type = priority.type || priority.title;
  if (type === "revenue_decline" || type === "revenue_growth") return dashboardHome.revenueChangedExplanation;
  if (type === "product_decline" || type === "product_growth") return phase4d.productRevenueChangedExplanation;
  if (type === "product_concentration") return phase4d.productConcentrationExplanation;
  if (type === "cross_sell_opportunity") return phase4d.crossSellOpportunityExplanation;
  return priority.explanation;
}

function priorityAction(
  action: string,
  phase4d: { reviewProductPerformance: string; reviewProductConcentration: string; reviewCrossSellOpportunities: string },
  company: { navSalesLabel: string; navRecommendationsLabel: string },
) {
  if (action === "review_product_performance") return phase4d.reviewProductPerformance;
  if (action === "review_product_concentration") return phase4d.reviewProductConcentration;
  if (action === "review_cross_sell_opportunities") return phase4d.reviewCrossSellOpportunities;
  if (action === "review_sales_performance") return company.navSalesLabel;
  return company.navRecommendationsLabel;
}

function prioritySeverity(
  severity: string,
  phase4d: { severityHigh: string; severityMedium: string; severityLow: string; severityCritical: string; severityInformational: string },
) {
  if (severity === "critical") return phase4d.severityCritical;
  if (severity === "high") return phase4d.severityHigh;
  if (severity === "medium") return phase4d.severityMedium;
  if (severity === "low") return phase4d.severityLow;
  if (severity === "informational") return phase4d.severityInformational;
  return severity;
}

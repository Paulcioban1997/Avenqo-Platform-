"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  ShoppingBag,
  TrendingUp,
  Package,
  Users,
  Warehouse,
  Sparkles,
  AlertTriangle,
  Lightbulb,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Database,
  ArrowDownUp,
  RefreshCw,
  Layers,
  Filter,
  Percent,
  Search,
  ExternalLink,
  Store,
} from "lucide-react";
import { AvenqoCard, MetricCard, StatusBadge } from "@/components/ui/avenqo-card";
import { TableSkeleton, KPISkeleton, ChartSkeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/status-states";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";
import { getAuthHeaders } from "@/lib/api-headers";

export type RetailSubTab =
  | "overview"
  | "sales"
  | "products"
  | "customers"
  | "inventory"
  | "forecasts"
  | "anomalies"
  | "recommendations";

export interface RetailIntelligenceViewProps {
  tenantName?: string;
  defaultTab?: RetailSubTab;
}

interface ProductItem {
  id: string;
  source_record_id: string;
  provider: string;
  product_name: string;
  sku: string;
  product_category: string;
  unit_price: number;
  stock_quantity: number;
  stock_status: string;
  store_url?: string | null;
}

interface OrderItem {
  id: string;
  source_record_id: string;
  order_number: string;
  customer_name: string;
  total_amount: number;
  currency: string;
  status: string;
  created_at: string | null;
}

interface CustomerItem {
  id: string;
  source_record_id: string;
  name: string;
  email: string;
  total_spent: number;
  orders_count: number;
}

interface InventoryItem {
  id: string;
  product_name: string;
  sku: string;
  stock_quantity: number | null;
  unit_price: number;
  status: "critical" | "warning" | "normal" | "unknown";
}

interface RetailStatus {
  is_connected: boolean;
  provider: string | null;
  store_url: string | null;
  status: string;
  last_synced_at: string | null;
  records_count: number;
  product_count: number;
  order_count: number;
  customer_count: number;
}

export function RetailIntelligenceView({
  tenantName = "",
  defaultTab = "overview",
}: RetailIntelligenceViewProps) {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const retail = t.retail;
  const integrations = t.integrations;
  const company = getApplicationCatalog(locale).company;
  const connector = company.connectorHub;

  const [activeTab, setActiveTab] = useState<RetailSubTab>(defaultTab);
  const [isLoading, setIsLoading] = useState(true);

  // Live retail data
  const [retailStatus, setRetailStatus] = useState<RetailStatus | null>(null);
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [customers, setCustomers] = useState<CustomerItem[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [stockAnomalies, setStockAnomalies] = useState<any[]>([]);

  // Search filter
  const [searchFilter, setSearchFilter] = useState("");

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const headers = getAuthHeaders();
      const [statusRes, prodRes, ordRes, custRes, invRes] = await Promise.all([
        fetch("/api/v1/retail/status", { headers }).catch(() => null),
        fetch("/api/v1/retail/products?limit=100", { headers }).catch(() => null),
        fetch("/api/v1/retail/orders?limit=100", { headers }).catch(() => null),
        fetch("/api/v1/retail/customers?limit=100", { headers }).catch(() => null),
        fetch("/api/v1/retail/inventory?limit=100", { headers }).catch(() => null),
      ]);

      if (statusRes && statusRes.ok) {
        const sData = await statusRes.json();
        setRetailStatus(sData);
      }

      if (prodRes && prodRes.ok) {
        const pData = await prodRes.json();
        setProducts(pData.products || []);
      }

      if (ordRes && ordRes.ok) {
        const oData = await ordRes.json();
        setOrders(oData.orders || []);
      }

      if (custRes && custRes.ok) {
        const cData = await custRes.json();
        setCustomers(cData.customers || []);
      }

      if (invRes && invRes.ok) {
        const iData = await invRes.json();
        setInventory(iData.inventory || []);
        setStockAnomalies(iData.anomalies || []);
      }
    } catch {
      // Local fallback
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData, tenantName]);

  const navTabs = [
    { id: "overview", label: t.retail.overview, icon: ShoppingBag },
    { id: "sales", label: t.retail.sales, icon: TrendingUp },
    { id: "products", label: t.retail.products, icon: Package },
    { id: "customers", label: t.retail.customers, icon: Users },
    { id: "inventory", label: t.retail.inventory, icon: Warehouse },
    { id: "forecasts", label: t.retail.forecasts, icon: Sparkles },
    { id: "anomalies", label: t.retail.anomalies, icon: AlertTriangle },
    { id: "recommendations", label: t.retail.recommendations, icon: Lightbulb },
  ];

  // Helper to open the client's store safely
  const handleOpenStore = () => {
    const url = retailStatus?.store_url;
    if (url) {
      const fullUrl = url.startsWith("http://") || url.startsWith("https://") ? url : `https://${url}`;
      window.open(fullUrl, "_blank", "noopener,noreferrer");
    }
  };

  const filteredProducts = products.filter(
    (p) =>
      !searchFilter.trim() ||
      p.product_name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      p.sku.toLowerCase().includes(searchFilter.toLowerCase()) ||
      p.product_category.toLowerCase().includes(searchFilter.toLowerCase())
  );
  const lowStockItems = inventory.filter(
    (item) => item.stock_quantity !== null && item.status !== "normal",
  );
  const inventoryHasStockData = inventory.some((item) => item.stock_quantity !== null);
  const retailCounts: Array<{ label: string; value: number }> = [
    { label: retail.products, value: retailStatus?.product_count ?? products.length },
    { label: retail.sales, value: retailStatus?.order_count ?? orders.length },
    { label: retail.customers, value: retailStatus?.customer_count ?? customers.length },
    { label: retail.inventory, value: inventory.length },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/80 dark:border-white/[0.08]">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-slate-900 dark:text-[#F4F7FB]">
              {t.navigation.retailAi}
            </h1>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/60">
              {t.retail.overview}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
            {t.retail.forecastDescription}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {retailStatus?.is_connected ? (
            <div className="flex items-center gap-2">
              <StatusBadge
                status="connected"
                label={`${retailStatus.provider?.toUpperCase() || company.connectionsUploadedSource} ${integrations.statusConnected}`}
                size="sm"
              />
              {retailStatus.store_url && (
                <button
                  onClick={handleOpenStore}
                  className="flex items-center gap-1 text-xs font-semibold text-[#0076FF] hover:underline cursor-pointer"
                >
                  <Store size={13} />
                  <span className="max-w-[140px] truncate">{retailStatus.store_url}</span>
                  <ExternalLink size={11} />
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <StatusBadge status="disconnected" label={integrations.statusDisconnected} size="sm" />
              <Link
                href="/integrations"
                className="text-xs font-semibold text-[#0076FF] hover:underline flex items-center gap-1"
              >
                <span>{integrations.googleCalendarConnect}</span>
                <ArrowRight size={11} />
              </Link>
            </div>
          )}

          <button
            onClick={() => setActiveTab("forecasts")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#0076FF] hover:bg-[#005bd3] text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#00D4FF]" />
            <span>{retail.forecasts}</span>
          </button>
        </div>
      </div>

      {/* 8-Tab Subnavigation Bar */}
      <div className="overflow-x-auto pb-1">
        <nav className="flex items-center gap-1 p-1 rounded-2xl bg-slate-100 dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] min-w-max">
          {navTabs.map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as RetailSubTab)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  isActive
                    ? "bg-white dark:bg-[#172652] text-[#0076FF] dark:text-[#00D4FF] shadow-xs"
                    : "text-slate-600 dark:text-[#94A3B8] hover:text-slate-900 dark:hover:text-[#F4F7FB] hover:bg-white/50 dark:hover:bg-white/[0.04]"
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    isActive ? "text-[#0076FF] dark:text-[#00D4FF]" : "text-slate-400"
                  }`}
                />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab 1: Overview backed by tenant source data */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <AvenqoCard variant="elevated" className="p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-white/[0.06]">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
                  {retail.overview}
                </h2>
                <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
                  {isLoading
                    ? "—"
                    : retailStatus?.is_connected
                      ? `${(retailStatus.records_count ?? 0).toLocaleString(locale)} ${connector.records}`
                      : t.common.insufficientData}
                </p>
              </div>
              {retailStatus?.last_synced_at && (
                <time
                  className="text-xs text-slate-500 dark:text-[#94A3B8]"
                  dateTime={retailStatus.last_synced_at}
                >
                  {new Date(retailStatus.last_synced_at).toLocaleString(locale)}
                </time>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4">
              {retailCounts.map((metric) => (
                <div key={metric.label} className="rounded-lg border border-slate-200/80 dark:border-white/[0.08] p-4">
                  <div className="text-xs font-medium text-slate-500 dark:text-[#94A3B8]">
                    {metric.label}
                  </div>
                  <div className="mt-1 text-xl font-bold text-slate-900 dark:text-[#F4F7FB]">
                    {isLoading ? "—" : metric.value.toLocaleString(locale)}
                  </div>
                </div>
              ))}
            </div>
          </AvenqoCard>
        </div>
      )}

      {/* Tab 3: Products (PRODUITS) — Real synchronized products from database */}
      {activeTab === "products" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder={t.shell.searchPlaceholder}
                className="w-full bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] rounded-xl pl-9 pr-3 py-2 text-xs text-slate-900 dark:text-[#F4F7FB] placeholder-slate-400 outline-none focus:border-[#0076FF]"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium">
                {products.length.toLocaleString(locale)} {connector.records}
              </span>
              <button
                onClick={loadData}
                disabled={isLoading}
                className="p-2 rounded-xl border border-slate-200 dark:border-white/[0.08] hover:bg-slate-100 dark:hover:bg-white/[0.04] text-slate-600 dark:text-slate-300"
              >
                <RefreshCw size={14} className={isLoading ? "animate-spin text-[#0076FF]" : ""} />
              </button>
            </div>
          </div>

          {isLoading ? (
            <TableSkeleton rows={6} columns={5} />
          ) : products.length > 0 ? (
            <AvenqoCard variant="default" className="overflow-hidden p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 dark:bg-[#060B13]/60 border-b border-slate-200/80 dark:border-white/[0.08] text-slate-500 dark:text-slate-400 font-semibold">
                      <th className="py-3 px-4">{retail.products}</th>
                      <th className="py-3 px-4">SKU</th>
                      <th className="py-3 px-4">{retail.overview}</th>
                      <th className="py-3 px-4 text-right">{retail.sales}</th>
                      <th className="py-3 px-4 text-center">{retail.inventory}</th>
                      <th className="py-3 px-4 text-center">{integrations.statusConnected}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                    {filteredProducts.map((p) => (
                      <tr
                        key={p.id}
                        className="hover:bg-slate-50/60 dark:hover:bg-white/[0.02] transition-colors"
                      >
                        <td className="py-3 px-4">
                          <div className="font-semibold text-slate-900 dark:text-[#F4F7FB]">
                            {p.product_name}
                          </div>
                          <div className="text-[10px] text-slate-400 uppercase">
                            {connector.connection} : {p.provider}
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px] text-slate-600 dark:text-slate-300">
                          {p.sku}
                        </td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                          {p.product_category}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-slate-900 dark:text-[#F4F7FB]">
                          ${p.unit_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              p.stock_quantity <= 5
                                ? "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400"
                                : p.stock_quantity <= 15
                                ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                                : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            }`}
                          >
                            {p.stock_quantity} u
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <StatusBadge
                            status={p.stock_quantity > 0 ? "connected" : "needs_attention"}
                            label={p.stock_quantity > 0 ? "En stock" : "Rupture"}
                            size="sm"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </AvenqoCard>
          ) : (
            <AvenqoCard variant="default" className="p-8">
              <EmptyState
                title={retail.noData}
                description="Connectez votre boutique en ligne (WooCommerce, Shopify...) ou importez vos données pour charger vos produits réels dans Avenqo."
                actionLabel="Connecter ou importer ma boutique"
                onAction={() => {
                  window.location.href = "/integrations";
                }}
              />
            </AvenqoCard>
          )}
        </div>
      )}

      {/* Tab 2: Sales (VENTES) — Real orders */}
      {activeTab === "sales" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">
              {orders.length.toLocaleString(locale)} {connector.records}
            </span>
          </div>

          {isLoading ? (
            <TableSkeleton rows={6} columns={5} />
          ) : orders.length > 0 ? (
            <AvenqoCard variant="default" className="overflow-hidden p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 dark:bg-[#060B13]/60 border-b border-slate-200/80 dark:border-white/[0.08] text-slate-500 dark:text-slate-400 font-semibold">
                      <th className="py-3 px-4">{t.crm.tabs.appointments}</th>
                      <th className="py-3 px-4">{retail.customers}</th>
                      <th className="py-3 px-4 text-right">{retail.sales}</th>
                      <th className="py-3 px-4 text-center">{integrations.statusConnected}</th>
                      <th className="py-3 px-4 text-right">{t.crm.calendar.today}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                    {orders.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-50/60 dark:hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-mono font-bold text-slate-900 dark:text-[#F4F7FB]">
                          #{o.order_number}
                        </td>
                        <td className="py-3 px-4 text-slate-700 dark:text-slate-300">
                          {o.customer_name}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-slate-900 dark:text-[#F4F7FB]">
                          ${o.total_amount.toFixed(2)} {o.currency}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <StatusBadge status="connected" label={o.status} size="sm" />
                        </td>
                        <td className="py-3 px-4 text-right text-slate-400 text-[11px]">
                          {o.created_at ? new Date(o.created_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </AvenqoCard>
          ) : (
            <AvenqoCard variant="default" className="p-8">
              <EmptyState
                title={retail.noData}
                description="Connectez votre boutique en ligne pour importer vos ventes et calculer vos prévisions d'encaissements."
                actionLabel="Connecter ma boutique"
                onAction={() => {
                  window.location.href = "/integrations";
                }}
              />
            </AvenqoCard>
          )}
        </div>
      )}

      {/* Tab 4: Customers (CLIENTS) */}
      {activeTab === "customers" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">
              {customers.length.toLocaleString(locale)} {connector.records}
            </span>
          </div>

          {isLoading ? (
            <TableSkeleton rows={6} columns={4} />
          ) : customers.length > 0 ? (
            <AvenqoCard variant="default" className="overflow-hidden p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 dark:bg-[#060B13]/60 border-b border-slate-200/80 dark:border-white/[0.08] text-slate-500 dark:text-slate-400 font-semibold">
                      <th className="py-3 px-4">{retail.customers}</th>
                      <th className="py-3 px-4">{retail.email}</th>
                      <th className="py-3 px-4 text-right">{retail.customers}</th>
                      <th className="py-3 px-4 text-center">{retail.sales}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                    {customers.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-50/60 dark:hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-semibold text-slate-900 dark:text-[#F4F7FB]">
                          {c.name}
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-500">{c.email}</td>
                        <td className="py-3 px-4 text-right font-bold text-slate-900 dark:text-[#F4F7FB]">
                          ${c.total_spent.toFixed(2)} CAD
                        </td>
                        <td className="py-3 px-4 text-center font-semibold text-slate-700 dark:text-slate-300">
                          {c.orders_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </AvenqoCard>
          ) : (
            <AvenqoCard variant="default" className="p-8">
              <EmptyState
                title={retail.noData}
                description="Connectez vos flux e-commerce pour générer la vue 360° et la segmentation RFM prédictive."
                actionLabel="Connecter ma boutique"
                onAction={() => {
                  window.location.href = "/integrations";
                }}
              />
            </AvenqoCard>
          )}
        </div>
      )}

      {/* Tab 5: Inventory (INVENTAIRE) */}
      {activeTab === "inventory" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">
              {retail.inventoryCount.replace("{count}", inventory.length.toLocaleString(locale))}
            </span>
          </div>

          {isLoading ? (
            <TableSkeleton rows={6} columns={4} />
          ) : inventory.length > 0 ? (
            <AvenqoCard variant="default" className="overflow-hidden p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 dark:bg-[#060B13]/60 border-b border-slate-200/80 dark:border-white/[0.08] text-slate-500 dark:text-slate-400 font-semibold">
                      <th className="py-3 px-4">{retail.products}</th>
                      <th className="py-3 px-4">SKU</th>
                      <th className="py-3 px-4 text-center">{retail.inventory}</th>
                      <th className="py-3 px-4 text-center">{retail.anomalies}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                    {inventory.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50/60 dark:hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-semibold text-slate-900 dark:text-[#F4F7FB]">
                          {item.product_name}
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-500">{item.sku}</td>
                        <td className="py-3 px-4 text-center font-bold">
                          <span
                            className={`px-2.5 py-1 rounded-full text-xs ${
                              item.status === "critical"
                                ? "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400"
                                : item.status === "warning"
                                ? "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400"
                                : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400"
                            }`}
                          >
                            {item.stock_quantity === null
                              ? "—"
                              : `${item.stock_quantity.toLocaleString(locale)} ${retail.unit}`}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center">
                          {item.status === "critical" ? (
                            <span className="text-xs font-bold text-rose-600 flex items-center justify-center gap-1">
                              <AlertTriangle size={13} />
                              <span>{retail.stockoutRiskAlert}</span>
                            </span>
                          ) : item.status === "warning" ? (
                            <span className="text-xs font-semibold text-amber-600">{retail.overstockAlert}</span>
                          ) : (
                            <span className="text-xs text-emerald-600 font-medium">{integrations.statusConnected}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </AvenqoCard>
          ) : (
            <AvenqoCard variant="default" className="p-8">
              <EmptyState
                title={retail.noData}
                description="Synchronisez votre boutique WooCommerce ou Shopify pour activer le suivi en direct des stocks."
                actionLabel="Connecter ma boutique"
                onAction={() => {
                  window.location.href = "/integrations";
                }}
              />
            </AvenqoCard>
          )}
        </div>
      )}

      {/* Tab 6: Demand Forecast Module */}
      {activeTab === "forecasts" && (
        <EmptyState
          icon={<Sparkles className="w-8 h-8 text-neutral-400" />}
          title={retail.forecasts}
          description={retail.forecastUnavailable}
        />
      )}

      {/* Tab 7: Anomalies & Stock Alerts */}
      {activeTab === "anomalies" && (
        <div className="space-y-6">
          <AvenqoCard variant="default" className="p-6">
            <div className="pb-4 mb-4 border-b border-slate-100 dark:border-white/[0.06]">
              <h3 className="text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
                {retail.anomalies}
              </h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-[#94A3B8]">
                {retail.anomalyDescription}
              </p>
            </div>

            <div className="space-y-4">
              {stockAnomalies.length > 0 ? (
                stockAnomalies.map((anom) => (
                  <div
                    key={anom.id}
                    className={`p-4 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                      anom.type === "stockout_risk"
                        ? "bg-rose-50/40 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900/50"
                        : "bg-amber-50/40 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/50"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`p-2 rounded-xl text-white ${
                          anom.type === "stockout_risk" ? "bg-rose-600" : "bg-amber-600"
                        }`}
                      >
                        <AlertTriangle className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 dark:text-[#F4F7FB]">
                            {anom.product}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">({anom.sku})</span>
                        </div>
                        <p className="text-xs text-slate-600 dark:text-[#94A3B8] mt-1">
                          {anom.message}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-xs">
                      <div className="text-right">
                        <div className="font-bold text-slate-900 dark:text-[#F4F7FB]">
                          {retail.stock}: {anom.currentStock.toLocaleString(locale)} {retail.unit}
                        </div>
                        <div className="text-[10px] text-slate-400">
                          {retail.safetyThreshold}: {anom.safetyThreshold.toLocaleString(locale)} {retail.unit}
                        </div>
                      </div>
                      <button
                        onClick={() => setActiveTab("products")}
                        className="px-3 py-1.5 rounded-xl bg-white dark:bg-[#111D3D] border border-slate-200 dark:border-white/[0.1] font-semibold text-xs text-slate-800 dark:text-[#F4F7FB] hover:bg-slate-50 dark:hover:bg-[#172652] transition-colors"
                      >
                        {retail.products}
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-6 text-center text-slate-400 text-xs">
                  {inventory.length > 0 && !inventoryHasStockData
                    ? t.common.insufficientData
                    : retail.noAnomaliesMessage}
                </div>
              )}
            </div>
          </AvenqoCard>
        </div>
      )}

      {/* Tab 8: Recommendations */}
      {activeTab === "recommendations" && (
        <AvenqoCard variant="default" className="p-6 space-y-4">
          <div className="pb-3 border-b border-slate-100 dark:border-white/[0.06]">
            <h3 className="text-base font-bold text-slate-900 dark:text-[#F4F7FB]">
              {retail.recommendations}
            </h3>
          </div>

          <div className="space-y-3">
            {isLoading ? (
              <TableSkeleton rows={3} columns={2} />
            ) : lowStockItems.length > 0 ? (
              lowStockItems.map((item) => (
                <div key={item.id} className="flex items-start gap-3 rounded-lg border border-slate-200/80 dark:border-white/[0.08] p-4">
                  <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-[#0076FF]" />
                  <div>
                    <h4 className="text-xs font-bold text-slate-900 dark:text-[#F4F7FB]">
                      {item.status === "critical" ? retail.stockoutRiskAlert : retail.reorderTitle}
                    </h4>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                      {item.product_name} · {retail.stock}: {item.stock_quantity?.toLocaleString(locale)} {retail.unit}
                    </p>
                  </div>
                </div>
              ))
            ) : inventory.length === 0 || !inventoryHasStockData ? (
              <EmptyState title={retail.noData} description={t.common.insufficientData} />
            ) : (
              <div className="p-6 text-center text-slate-400 text-xs">
                {retail.noAnomaliesMessage}
              </div>
            )}
          </div>
        </AvenqoCard>
      )}
    </div>
  );
}

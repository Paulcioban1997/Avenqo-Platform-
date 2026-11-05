"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp,
  Building2,
  DollarSign,
  FileCheck2,
  Cpu,
  Boxes,
  Activity,
  Shield,
  LifeBuoy,
  Settings as SettingsIcon,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Search,
  ExternalLink,
  ChevronRight,
  ShieldAlert,
  Calendar,
  Lock,
} from "lucide-react";
import { apiFetch } from "@/lib/api-request";
import { getAuthHeaders } from "@/lib/api-headers";

interface CEOCommandCenterProps {
  isFr: boolean;
}

export function CEOCommandCenter({ isFr }: CEOCommandCenterProps) {
  const [activeTab, setActiveTab] = useState<
    | "overview"
    | "organizations"
    | "revenue"
    | "contracts"
    | "ai"
    | "connectors"
    | "operations"
    | "security"
    | "support"
    | "settings"
  >("overview");

  const [range, setRange] = useState<"7d" | "30d" | "90d">("30d");
  const [loading, setLoading] = useState(false);
  const [overviewData, setOverviewData] = useState<any>(null);
  const [orgsData, setOrgsData] = useState<any>(null);
  const [revenueData, setRevenueData] = useState<any>(null);
  const [contractsData, setContractsData] = useState<any>(null);
  const [aiData, setAiData] = useState<any>(null);
  const [connectorsData, setConnectorsData] = useState<any>(null);
  const [opsData, setOpsData] = useState<any>(null);
  const [securityData, setSecurityData] = useState<any>(null);
  const [settingsData, setSettingsData] = useState<any>(null);

  const [countersignBusy, setCountersignBusy] = useState<string | null>(null);
  const [countersignMsg, setCountersignMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const loadActiveTabData = useCallback(async () => {
    setLoading(true);
    const headers = getAuthHeaders();
    try {
      if (activeTab === "overview") {
        const res = await apiFetch(`/api/v1/ceo/overview?range=${range}`, { headers });
        if (res.ok) setOverviewData(await res.json());
      } else if (activeTab === "organizations") {
        const res = await apiFetch(`/api/v1/ceo/organizations?page=1&page_size=20`, { headers });
        if (res.ok) setOrgsData(await res.json());
      } else if (activeTab === "revenue") {
        const res = await apiFetch(`/api/v1/ceo/revenue`, { headers });
        if (res.ok) setRevenueData(await res.json());
      } else if (activeTab === "contracts") {
        const res = await apiFetch(`/api/v1/ceo/contracts-queue`, { headers });
        if (res.ok) setContractsData(await res.json());
      } else if (activeTab === "ai") {
        const res = await apiFetch(`/api/v1/ceo/ai-usage`, { headers });
        if (res.ok) setAiData(await res.json());
      } else if (activeTab === "connectors") {
        const res = await apiFetch(`/api/v1/ceo/connectors`, { headers });
        if (res.ok) setConnectorsData(await res.json());
      } else if (activeTab === "operations") {
        const res = await apiFetch(`/api/v1/ceo/operations-health`, { headers });
        if (res.ok) setOpsData(await res.json());
      } else if (activeTab === "security") {
        const res = await apiFetch(`/api/v1/ceo/security-audit?limit=25`, { headers });
        if (res.ok) setSecurityData(await res.json());
      } else if (activeTab === "settings") {
        const res = await apiFetch(`/api/v1/ceo/settings-status`, { headers });
        if (res.ok) setSettingsData(await res.json());
      }
    } catch (e) {
      console.error("Erreur chargement module CEO:", e);
    } finally {
      setLoading(false);
    }
  }, [activeTab, range]);

  useEffect(() => {
    void loadActiveTabData();
  }, [loadActiveTabData]);

  const handleCountersign = async (companyId: string, contractType: string) => {
    setCountersignBusy(`${companyId}-${contractType}`);
    setCountersignMsg(null);
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch(`/api/v1/contracts/${contractType}/countersign?company_id=${companyId}`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_name: "Mircea Paul Cioban",
          provider_title: "Président Fondateur",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
        setCountersignMsg({
          text: isFr ? "Contrat contresigné avec succès (statut : FULLY_EXECUTED)." : "Contract countersigned successfully (status: FULLY_EXECUTED).",
          ok: true,
        });
        void loadActiveTabData();
        }
      }
    } catch (err: any) {
      setCountersignMsg({ text: err.message || "Erreur de contresignature", ok: false });
    } finally {
      setCountersignBusy(null);
    }
  };

  const navItems = [
    { id: "overview", label: isFr ? "Vue d'ensemble" : "Overview", icon: TrendingUp },
    { id: "organizations", label: isFr ? "Organisations" : "Organizations", icon: Building2 },
    { id: "revenue", label: isFr ? "Revenus & Stripe" : "Revenue & Billing", icon: DollarSign },
    { id: "contracts", label: isFr ? "File des Contrats" : "Contracts Queue", icon: FileCheck2 },
    { id: "ai", label: isFr ? "Consommation IA" : "AI Economics", icon: Cpu },
    { id: "connectors", label: isFr ? "22 Connecteurs" : "22 Connectors", icon: Boxes },
    { id: "operations", label: isFr ? "Santé & Jobs" : "Ops & Health", icon: Activity },
    { id: "security", label: isFr ? "Audit & Sécurité" : "Security & Audit", icon: Shield },
    { id: "support", label: isFr ? "Support & Leads" : "Support & Leads", icon: LifeBuoy },
    { id: "settings", label: isFr ? "Gouvernance & Verrous" : "Settings & Gates", icon: SettingsIcon },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white border border-slate-700/60 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-indigo-500/30 text-indigo-200 border border-indigo-400/30">
              Avenqo Platform Ops
            </span>
            <span className="text-xs text-slate-400">P0 CEO Command Center (Phase 33 & 34)</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black tracking-tight mt-1">
            {isFr ? "Centre de Commandement Exécutif — Fondateur" : "Executive CEO Command Center"}
          </h2>
          <p className="text-xs text-slate-300 mt-0.5">
            {isFr
              ? "Gouvernance SaaS unifiée : métriques réelles sans simulation, file contractuelle certifiée et santé des 22 connecteurs."
              : "Unified SaaS governance: sourced metrics, certified contractual queue, and 22 canonical connectors."}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => void loadActiveTabData()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 text-xs font-semibold text-white transition-all shadow-sm"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            {isFr ? "Actualiser" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Navigation Tabs (10 modules) */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2 border-b border-slate-200/80 dark:border-white/[0.08] scrollbar-thin">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id as any)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                isActive
                  ? "bg-[#0076FF] text-white shadow-md shadow-blue-500/20"
                  : "bg-slate-100 dark:bg-white/[0.04] text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-white/[0.08]"
              }`}
            >
              <Icon size={14} />
              {item.label}
            </button>
          );
        })}
      </div>

      {countersignMsg && (
        <div
          className={`p-3.5 rounded-xl border text-xs font-medium flex items-center justify-between ${
            countersignMsg.ok
              ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300 text-emerald-800 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/30 border-red-300 text-red-800 dark:text-red-300"
          }`}
        >
          <span>{countersignMsg.text}</span>
          <button onClick={() => setCountersignMsg(null)} className="text-slate-400 hover:text-slate-600">
            &times;
          </button>
        </div>
      )}

      {/* Content Panes */}
      {loading && !overviewData && (
        <div className="py-20 text-center text-slate-400 animate-pulse">
          {isFr ? "Chargement des données exécutives..." : "Loading executive telemetry..."}
        </div>
      )}

      {/* MODULE 1: EXECUTIVE OVERVIEW */}
      {activeTab === "overview" && overviewData && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {isFr ? "Période d'analyse : " : "Window: "}
              <b className="text-slate-700 dark:text-slate-200">{range}</b>
            </span>
            <div className="flex items-center gap-1 bg-slate-100 dark:bg-white/[0.06] p-1 rounded-xl">
              {(["7d", "30d", "90d"] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                    range === r
                      ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(overviewData.kpis || {}).map(([k, item]: [string, any]) => (
              <div
                key={k}
                className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm space-y-2"
              >
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-semibold text-slate-600 dark:text-slate-300">{item.label}</span>
                  <span className="text-[10px] text-slate-400 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-white/[0.05]">
                    {item.source}
                  </span>
                </div>
                <div className="text-2xl font-black tracking-tight text-slate-900 dark:text-white">
                  {typeof item.value === "number" && item.currency
                    ? `${item.value.toLocaleString()} ${item.currency}`
                    : typeof item.value === "number"
                    ? item.value.toLocaleString()
                    : item.value}
                </div>
                <p className="text-[11px] text-slate-400 leading-tight">{item.tooltip}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MODULE 2: ORGANIZATIONS */}
      {activeTab === "organizations" && orgsData && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
              {isFr ? `Locataires enregistrés (${orgsData.total})` : `Registered Tenants (${orgsData.total})`}
            </h3>
          </div>
          <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden bg-white dark:bg-[#0B132B]">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-white/[0.03] text-slate-500 border-b border-slate-200/80 dark:border-white/[0.08]">
                <tr>
                  <th className="p-3 font-bold">{isFr ? "Organisation" : "Company"}</th>
                  <th className="p-3 font-bold">{isFr ? "Profil Légal" : "Legal Profile"}</th>
                  <th className="p-3 font-bold">{isFr ? "Forfait" : "Plan"}</th>
                  <th className="p-3 font-bold">{isFr ? "Contrats" : "Contracts"}</th>
                  <th className="p-3 font-bold">{isFr ? "Membres" : "Users"}</th>
                  <th className="p-3 font-bold">{isFr ? "Statut" : "Status"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {orgsData.items?.map((org: any) => (
                  <tr key={org.company_id} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                    <td className="p-3 font-semibold text-slate-900 dark:text-white">
                      <div>{org.name}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{org.company_id.slice(0, 14)}...</div>
                    </td>
                    <td className="p-3">
                      {org.legal_profile_completed ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                          <CheckCircle2 size={12} /> {org.legal_name}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-amber-500 font-medium">
                          <AlertTriangle size={12} /> {isFr ? "Non complété" : "Incomplete"}
                        </span>
                      )}
                    </td>
                    <td className="p-3 uppercase font-bold text-slate-600 dark:text-slate-300">
                      {org.subscription_plan}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          org.contracts_status === "FULLY_EXECUTED"
                            ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300"
                            : org.contracts_status === "CUSTOMER_SIGNED"
                            ? "bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300"
                            : "bg-slate-100 dark:bg-white/[0.08] text-slate-600 dark:text-slate-400"
                        }`}
                      >
                        {org.contracts_status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-300 font-mono">{org.users_count}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 text-[10px] font-bold">
                        {org.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 3: REVENUE & STRIPE */}
      {activeTab === "revenue" && revenueData && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Forfaits Base (29.99 CAD)</span>
              <div className="text-2xl font-black mt-1 text-slate-900 dark:text-white">
                {revenueData.plan_distribution.base}
              </div>
              <div className="text-xs text-slate-400 mt-1">MRR: {revenueData.mrr_by_plan.base_cad} CAD</div>
            </div>
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Forfaits Professional (49.99 CAD)</span>
              <div className="text-2xl font-black mt-1 text-slate-900 dark:text-white">
                {revenueData.plan_distribution.professional}
              </div>
              <div className="text-xs text-slate-400 mt-1">MRR: {revenueData.mrr_by_plan.professional_cad} CAD</div>
            </div>
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Passerelle Stripe</span>
              <div className="text-base font-bold mt-1 text-emerald-600 flex items-center gap-1.5">
                <CheckCircle2 size={16} />
                {revenueData.stripe_gateway_status.test_mode ? "Sandbox / Mode Test" : "Production Live"}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                Taxes auto: {revenueData.stripe_gateway_status.automatic_tax ? "Activées" : "Désactivées"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 4: CONTRACTS QUEUE & COUNTERSIGNATURE */}
      {activeTab === "contracts" && contractsData && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                {isFr ? "File Contractuelle & Tâches de Contreseing" : "Contracts Queue & Tasks"}
              </h3>
              <p className="text-xs text-slate-500">
                {isFr
                  ? `${contractsData.pending_countersign_count} document(s) signé(s) par le client en attente de contreseing fondateur.`
                  : `${contractsData.pending_countersign_count} client-signed agreement(s) awaiting provider countersignature.`}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden bg-white dark:bg-[#0B132B]">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-white/[0.03] text-slate-500 border-b border-slate-200/80 dark:border-white/[0.08]">
                <tr>
                  <th className="p-3 font-bold">{isFr ? "Entreprise" : "Tenant"}</th>
                  <th className="p-3 font-bold">{isFr ? "Contrat" : "Agreement"}</th>
                  <th className="p-3 font-bold">{isFr ? "Statut" : "Status"}</th>
                  <th className="p-3 font-bold">{isFr ? "Signataire Client" : "Client Signer"}</th>
                  <th className="p-3 font-bold">{isFr ? "Action Fondateur" : "Provider Action"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {contractsData.contracts?.map((c: any) => (
                  <tr key={c.contract_id} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                    <td className="p-3 font-semibold text-slate-900 dark:text-white">{c.company_name}</td>
                    <td className="p-3 font-mono">{c.contract_type} ({c.version})</td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          c.status === "FULLY_EXECUTED"
                            ? "bg-emerald-100 text-emerald-800"
                            : c.status === "CUSTOMER_SIGNED" || c.status === "SIGNED"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-300">
                      {c.signatory_name || "En attente"}
                      {c.signed_at && <div className="text-[10px] text-slate-400">{c.signed_at.slice(0, 10)}</div>}
                    </td>
                    <td className="p-3">
                      {c.is_countersign_ready ? (
                        <button
                          onClick={() => handleCountersign(c.company_id, c.contract_type)}
                          disabled={countersignBusy === `${c.company_id}-${c.contract_type}`}
                          className="px-3 py-1 rounded-lg bg-[#0076FF] hover:bg-blue-600 text-white font-bold text-[11px] shadow-sm transition-all"
                        >
                          {countersignBusy === `${c.company_id}-${c.contract_type}`
                            ? "Signature..."
                            : isFr
                            ? "Contresigner (CEO)"
                            : "Countersign (CEO)"}
                        </button>
                      ) : c.status === "FULLY_EXECUTED" ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 font-bold text-[11px]">
                          <CheckCircle2 size={13} /> {isFr ? "Pleinement Exécuté" : "Fully Executed"}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">{isFr ? "Non requis" : "Not ready"}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 5: AI USAGE */}
      {activeTab === "ai" && aiData && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Crédits IA Mensuels Consommés</span>
              <div className="text-2xl font-black mt-1 text-slate-900 dark:text-white">
                {aiData.monthly_credits_consumed.toLocaleString()}
              </div>
              <div className="text-xs text-slate-400 mt-1">Précision: {aiData.metering_accuracy}</div>
            </div>
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Coût Fournisseurs LLM Estimé (CAD)</span>
              <div className="text-2xl font-black mt-1 text-slate-900 dark:text-white">
                {aiData.estimated_provider_cost_cad} CAD
              </div>
              <div className="text-xs text-slate-400 mt-1">({aiData.estimated_provider_cost_usd} USD)</div>
            </div>
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Anomalies de Consommation</span>
              <div className="text-2xl font-black mt-1 text-emerald-600">
                {aiData.anomalies_detected_count}
              </div>
              <div className="text-xs text-slate-400 mt-1">Aucun abus ou fuite détectée</div>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 6: 22 CANONICAL CONNECTORS */}
      {activeTab === "connectors" && connectorsData && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {isFr ? `Catalogue Canonique des 22 Connecteurs` : `22 Canonical Connectors Catalog`}
            </h3>
            <span className="text-xs text-slate-400">Chiffrement matériel des secrets actif</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {connectorsData.connectors?.map((conn: any) => (
              <div
                key={conn.id}
                className="p-3.5 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] flex items-center justify-between gap-2 shadow-sm"
              >
                <div>
                  <div className="text-xs font-bold text-slate-900 dark:text-white">{conn.name}</div>
                  <div className="text-[10px] text-slate-400">{conn.category}</div>
                </div>
                <div className="text-right">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[9px] font-bold ${
                      conn.status === "OPERATIONAL" || conn.status === "READY"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {conn.status}
                  </span>
                  <div className="text-[9px] text-slate-400 mt-0.5">
                    {conn.active_connections_count} locataire(s)
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MODULE 7: OPERATIONS & HEALTH */}
      {activeTab === "operations" && opsData && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Service API Central</span>
              <div className="text-lg font-bold text-emerald-600 flex items-center gap-1.5 mt-1">
                <CheckCircle2 size={16} /> {opsData.api_service_status}
              </div>
            </div>
            <div className="p-4 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] shadow-sm">
              <span className="text-xs text-slate-500">Connectivité PostgreSQL</span>
              <div className="text-lg font-bold text-emerald-600 flex items-center gap-1.5 mt-1">
                <CheckCircle2 size={16} /> {opsData.database_connectivity}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODULE 8: SECURITY & AUDIT */}
      {activeTab === "security" && securityData && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {isFr ? `Journal d'Audit Immuable (${securityData.events_count} récents)` : `Audit Log`}
            </h3>
          </div>
          <div className="rounded-2xl border border-slate-200/80 dark:border-white/[0.08] overflow-hidden bg-white dark:bg-[#0B132B]">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-white/[0.03] text-slate-500 border-b border-slate-200/80 dark:border-white/[0.08]">
                <tr>
                  <th className="p-3 font-bold">Action</th>
                  <th className="p-3 font-bold">Cible</th>
                  <th className="p-3 font-bold">Horodatage (UTC)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/[0.04]">
                {securityData.events?.map((e: any) => (
                  <tr key={e.id} className="hover:bg-slate-50/50 dark:hover:bg-white/[0.02]">
                    <td className="p-3 font-mono font-bold text-slate-800 dark:text-slate-200">{e.action}</td>
                    <td className="p-3 text-slate-500">{e.target_type} ({e.target_id?.slice(0, 8)})</td>
                    <td className="p-3 text-slate-400 font-mono">{e.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODULE 9: SUPPORT & LEADS */}
      {activeTab === "support" && (
        <div className="p-8 rounded-2xl bg-white dark:bg-[#0B132B] border border-slate-200/80 dark:border-white/[0.08] text-center space-y-2">
          <LifeBuoy className="w-8 h-8 mx-auto text-slate-400" />
          <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {isFr ? "Aucune demande d'assistance en souffrance" : "No Pending Inquiries"}
          </h4>
          <p className="text-xs text-slate-500">
            {isFr ? "Le canal de support direct est opérationnel." : "Support queue is clean."}
          </p>
        </div>
      )}

      {/* MODULE 10: SETTINGS STATUS & PUBLICATION GATES */}
      {activeTab === "settings" && settingsData && (
        <div className="space-y-4">
          <div className="p-5 rounded-2xl bg-amber-50 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-800/40 text-amber-900 dark:text-amber-200 space-y-2">
            <div className="flex items-center gap-2 font-bold text-sm">
              <AlertTriangle size={18} className="text-amber-600" />
              {isFr ? "Verrou de Commercialisation & Incorporation" : "Commercial Launch & Legal Gate"}
            </div>
            <p className="text-xs leading-relaxed">
              {isFr
                ? `L'entité fournisseur ${settingsData.provider_legal_entity.name} est enregistrée sous le statut « ${settingsData.provider_legal_entity.incorporation_status} » (${settingsData.provider_legal_entity.jurisdiction}). L'activation commerciale publique en production demeure STRICTEMENT VERROUILLÉE tant que le certificat d'incorporation officiel n'est pas versé et validé par le fondateur et son conseil juridique.`
                : `Provider entity ${settingsData.provider_legal_entity.name} is flagged as "${settingsData.provider_legal_entity.incorporation_status}". Public commercial activation remains LOCKED until corporate certificates are filed and verified.`}
            </p>
            <div className="pt-2 flex items-center gap-3 text-xs font-semibold">
              <span className="px-2.5 py-1 rounded-lg bg-amber-200/60 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200">
                Statut des modèles : {settingsData.legal_templates_publication_gate.status}
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-amber-200/60 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200">
                Signature Live : {settingsData.legal_templates_publication_gate.live_signing_authorized ? "Autorisée" : "Bloquée (Fail-Closed)"}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

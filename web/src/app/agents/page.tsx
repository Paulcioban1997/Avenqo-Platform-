"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/app-shell";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import {
  Bot,
  Sparkles,
  PhoneCall,
  Calendar,
  ShoppingBag,
  CreditCard,
  Layers,
  CheckCircle,
  AlertCircle,
  Settings,
  MessageSquare,
  Search,
  ArrowRight,
  RefreshCw,
  Power,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

type AgentItem = {
  slug: string;
  name_key: string;
  status: string;
  module_code?: string;
  executable: boolean;
};

type UnavailableAgent = {
  slug: string;
  name_key: string;
  reason: string;
  required: string[];
};

type AgentsApiResponse = {
  active_modules: string[];
  agents: AgentItem[];
  unavailable_agents: UnavailableAgent[];
};

interface AgentMeta {
  titleFr: string;
  titleEn: string;
  descFr: string;
  descEn: string;
  categoryFr: string;
  categoryEn: string;
  icon: typeof Bot;
  settingsUrl: string;
  capabilitiesFr: string[];
  capabilitiesEn: string[];
}

const AGENT_METADATA: Record<string, AgentMeta> = {
  voice: {
    titleFr: "Voice AI — Réceptionniste Téléphonique",
    titleEn: "Voice AI — Telephone Receptionist",
    descFr:
      "Répond automatiquement aux appels entrants 24/7, renseigne les clients, planifie des rendez-vous et transfère les urgences.",
    descEn:
      "Automatically handles incoming customer calls 24/7, answers business inquiries, schedules appointments, and routes emergencies.",
    categoryFr: "Téléphonie & Voix",
    categoryEn: "Telephony & Voice",
    icon: PhoneCall,
    settingsUrl: "/settings/voice",
    capabilitiesFr: ["Prise de rendez-vous", "Détection de langue", "Enrôlement PIN", "Call Control Telnyx"],
    capabilitiesEn: ["Appointment booking", "Language detection", "PIN enrollment", "Telnyx Call Control"],
  },
  crm: {
    titleFr: "CRM AI — Assistant Planification & Clients",
    titleEn: "CRM AI — Scheduling & Client Specialist",
    descFr:
      "Gère vos agendas, valide les disponibilités selon vos horaires d'ouverture réels, résout les conflits et synchronise Google Calendar.",
    descEn:
      "Manages client records, verifies availability according to real business hours, prevents conflicts, and syncs external calendars.",
    categoryFr: "Relation Client & Calendrier",
    categoryEn: "Customer Relations & Calendar",
    icon: Calendar,
    settingsUrl: "/crm",
    capabilitiesFr: ["Moteur d'horaires stricts", "Anti-doublon d'intentions", "Synchronisation Google Calendar", "Gestion multi-employés"],
    capabilitiesEn: ["Strict hours engine", "Idempotent booking", "Google Calendar sync", "Multi-employee scheduling"],
  },
  retail: {
    titleFr: "Retail AI — Analyste Ventes & Commerce",
    titleEn: "Retail AI — Sales & Commerce Analyst",
    descFr:
      "Analyse les ventes omnicanales, les tendances de panier moyen, surveille les ruptures de stocks et génère des prévisions.",
    descEn:
      "Analyzes omnichannel sales, average order value trends, monitors inventory depletion, and generates demand forecasts.",
    categoryFr: "Commerce & Vente",
    categoryEn: "Commerce & Sales",
    icon: ShoppingBag,
    settingsUrl: "/retail",
    capabilitiesFr: ["Connexion Shopify", "Analyse des commandes", "Alertes d'inventaire", "Rapports de marge"],
    capabilitiesEn: ["Shopify integration", "Order analytics", "Inventory alerts", "Margin reporting"],
  },
  tenant_capabilities: {
    titleFr: "Facturation & Quotas AI",
    titleEn: "Billing & Subscriptions AI",
    descFr:
      "Supervise la consommation des crédits IA, le renouvellement des forfaits, les plafonds par module et l'historique des factures.",
    descEn:
      "Monitors real-time AI credit consumption, subscription renewals, module limits, and invoice history.",
    categoryFr: "Administration & Forfaits",
    categoryEn: "Administration & Plans",
    icon: CreditCard,
    settingsUrl: "/billing",
    capabilitiesFr: ["Registre de crédits en direct", "Gestion Stripe Sandbox", "Devis Enterprise", "Exports comptables"],
    capabilitiesEn: ["Live credit ledger", "Stripe Sandbox management", "Enterprise quotes", "Accounting exports"],
  },
  platform_support: {
    titleFr: "Support Central & Diagnostic Avenqo",
    titleEn: "Central Diagnostics & System Agent",
    descFr:
      "Supervise l'état de santé de l'espace de travail, l'audit multi-tenant et la résolution des requêtes transversales.",
    descEn:
      "Monitors tenant health, enforces multi-tenant security boundaries, and handles cross-module user requests.",
    categoryFr: "Plateforme & Sécurité",
    categoryEn: "Platform & Security",
    icon: ShieldCheck,
    settingsUrl: "/settings",
    capabilitiesFr: ["Isolation multi-tenant stricte", "Mémoire persistante Mem0", "Audit de requêtes", "Routage d'outils"],
    capabilitiesEn: ["Strict multi-tenant isolation", "Mem0 persistent memory", "Request auditing", "Tool routing"],
  },
};

export default function AgentsPage() {
  const { locale } = useLocale();
  const fr = locale.startsWith("fr");
  const [data, setData] = useState<AgentsApiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const loadAgents = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/api/v1/agents");
      if (response.ok) {
        setData(await response.json());
      }
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.publicMessage || (fr ? "Erreur de chargement." : "Load error."));
      } else {
        setError(fr ? "Erreur de connexion au serveur." : "Server connection error.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAgents();
  }, []);

  const allAgents = useMemo(() => {
    if (!data) return [];
    const active = data.agents.map((a) => ({ ...a, is_active: true }));
    const inactive = data.unavailable_agents.map((u) => ({
      slug: u.slug,
      name_key: u.name_key,
      status: "unavailable",
      module_code: u.required[0] || undefined,
      executable: false,
      is_active: false,
      reason: u.reason,
    }));
    return [...active, ...inactive];
  }, [data]);

  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) return allAgents;
    const q = searchQuery.toLowerCase();
    return allAgents.filter((agent) => {
      const meta = AGENT_METADATA[agent.slug];
      const title = fr ? meta?.titleFr || agent.slug : meta?.titleEn || agent.slug;
      const desc = fr ? meta?.descFr || "" : meta?.descEn || "";
      return title.toLowerCase().includes(q) || desc.toLowerCase().includes(q) || agent.slug.includes(q);
    });
  }, [allAgents, searchQuery, fr]);

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-6 animate-in fade-in duration-300">
        {/* HEADER */}
        <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-widest text-[#0076FF] dark:text-[#00D4FF]">
                Avenqo Intelligence
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium">
                {data?.agents.length || 0} {fr ? "Agents actifs" : "Active Agents"}
              </span>
            </div>
            <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              {fr ? "Gestion des Agents Spécialisés" : "Specialized AI Agents"}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {fr
                ? "Assistants IA autorisés et connectés aux modules de votre entreprise."
                : "Authorized AI assistants connected to your company's entitled modules."}
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => void loadAgents()}
              disabled={loading}
              className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 transition"
              title={fr ? "Actualiser" : "Refresh"}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <Link
              href="/marketplace"
              className="flex items-center gap-2 px-4 py-2.5 text-xs font-bold rounded-xl bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-md hover:shadow-lg transition"
            >
              <Layers className="w-4 h-4" />
              <span>{fr ? "Marketplace des Modules" : "Modules Marketplace"}</span>
            </Link>
          </div>
        </header>

        {error && (
          <div role="alert" className="flex items-center gap-2.5 p-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* SEARCH & FILTERS */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white dark:bg-[#0B132B] p-3 rounded-2xl border border-slate-200 dark:border-slate-800">
          <div className="relative w-full sm:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={fr ? "Rechercher un agent par nom ou capacité..." : "Search agents by name or capability..."}
              className="w-full pl-10 pr-4 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-hidden focus:ring-2 focus:ring-[#0076FF]"
            />
          </div>

          <button
            onClick={() => setShowDiagnostics(!showDiagnostics)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 dark:hover:text-white px-3 py-2 rounded-xl transition"
          >
            <span>{fr ? "Diagnostic technique" : "Technical Diagnostics"}</span>
            {showDiagnostics ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* AGENTS GRID */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filteredAgents.map((agent) => {
            const meta = AGENT_METADATA[agent.slug] || {
              titleFr: agent.slug.toUpperCase(),
              titleEn: agent.slug.toUpperCase(),
              descFr: "Assistant métier spécialisé de la plateforme Avenqo.",
              descEn: "Specialized business assistant of the Avenqo platform.",
              categoryFr: "Module Métier",
              categoryEn: "Business Module",
              icon: Bot,
              settingsUrl: "/settings",
              capabilitiesFr: ["Exécution autorisée"],
              capabilitiesEn: ["Authorized execution"],
            };
            const Icon = meta.icon;
            const title = fr ? meta.titleFr : meta.titleEn;
            const desc = fr ? meta.descFr : meta.descEn;
            const category = fr ? meta.categoryFr : meta.categoryEn;
            const capabilities = fr ? meta.capabilitiesFr : meta.capabilitiesEn;

            return (
              <div
                key={agent.slug}
                className="flex flex-col justify-between rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0B132B] p-6 shadow-xs hover:border-slate-300 dark:hover:border-slate-700 transition"
              >
                <div className="space-y-4">
                  {/* TOP ROW: ICON, BADGE, STATUS */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-3 rounded-2xl bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-950 dark:to-slate-900 text-[#0076FF] dark:text-[#00D4FF] border border-blue-200/50 dark:border-blue-900/40 shadow-xs">
                        <Icon className="w-6 h-6" />
                      </div>
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          {category}
                        </span>
                        <h3 className="font-extrabold text-slate-900 dark:text-white text-base">
                          {title}
                        </h3>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {agent.is_active ? (
                        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 text-xs font-bold border border-emerald-200/60 dark:border-emerald-800/60">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                          <span>{fr ? "Actif" : "Active"}</span>
                        </span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 text-xs font-semibold">
                          {fr ? "Module requis" : "Module required"}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* DESCRIPTION */}
                  <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                    {desc}
                  </p>

                  {/* CAPABILITIES CHIPS */}
                  <div>
                    <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                      {fr ? "Capacités & Permissions" : "Capabilities & Permissions"}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 text-slate-700 dark:text-slate-300 text-xs font-medium"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* RAW DIAGNOSTICS */}
                  {showDiagnostics && (
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-[11px] font-mono text-slate-500 space-y-1">
                      <p>slug: {agent.slug}</p>
                      <p>module_code: {agent.module_code || "platform"}</p>
                      <p>status: {agent.status}</p>
                    </div>
                  )}
                </div>

                {/* BOTTOM ACTIONS */}
                <div className="flex items-center justify-between gap-3 pt-5 mt-5 border-t border-slate-100 dark:border-slate-800">
                  <Link
                    href={meta.settingsUrl}
                    className="flex items-center gap-1.5 text-xs font-bold text-[#0076FF] dark:text-[#00D4FF] hover:underline"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    <span>{fr ? "Configurer" : "Configure"}</span>
                  </Link>

                  <div className="flex items-center gap-2">
                    <Link
                      href={agent.is_active ? "/" : "/marketplace"}
                      className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition ${
                        agent.is_active
                          ? "bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200"
                          : "bg-gradient-to-r from-[#0076FF] to-[#00D4FF] text-white shadow-xs"
                      }`}
                    >
                      {agent.is_active ? (
                        <>
                          <MessageSquare className="w-3.5 h-3.5" />
                          <span>{fr ? "Tester dans Central AI" : "Test in Central AI"}</span>
                        </>
                      ) : (
                        <>
                          <span>{fr ? "Activer le module" : "Activate Module"}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </>
                      )}
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}

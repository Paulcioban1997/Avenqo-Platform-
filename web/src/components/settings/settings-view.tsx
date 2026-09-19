"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Settings,
  Building2,
  Shield,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Zap,
  CreditCard,
  Plug,
  Database,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  Info,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";

interface ModuleItem {
  key: string;
  display_name: string;
  description: string;
  availability: string;
  active: boolean;
  state: string;
  premium: boolean;
  category: string;
  credit_multiplier: number;
}

interface EntitlementsData {
  company_id: string;
  plan_code: string;
  active_modules: string[];
  module_limit: number | null;
  remaining_module_slots: number | null;
  modules: ModuleItem[];
}

interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_platform_admin?: boolean;
}

interface OrgInfo {
  name: string;
  id: string;
  slug?: string;
  subscription_plan?: string;
}

export function SettingsView() {
  const { locale } = useLocale();
  const t = getAppTranslations(locale);
  const isFr = locale === "fr";

  const [loading, setLoading] = useState(true);
  const [entitlements, setEntitlements] = useState<EntitlementsData | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [company, setCompany] = useState<OrgInfo | null>(null);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const getHeaders = useCallback(() => {
    const token = typeof window !== "undefined"
      ? localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token")
      : null;
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const headers = getHeaders();
      const [userRes, entRes] = await Promise.all([
        fetch("/api/v1/auth/me", { headers }),
        fetch("/api/v1/modules/entitlements", { headers }),
      ]);

      if (userRes.ok) {
        const userData = await userRes.json();
        setUser(userData.user);
        setCompany(userData.company);
      }

      if (entRes.ok) {
        const entData = await entRes.json();
        setEntitlements(entData);
      }
    } catch {
      setStatusMsg({
        type: "error",
        text: isFr ? "Erreur de chargement des paramètres" : "Error loading settings",
      });
    } finally {
      setLoading(false);
    }
  }, [getHeaders, isFr]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggleModule = async (mod: ModuleItem) => {
    setUpdatingKey(mod.key);
    setStatusMsg(null);
    try {
      const headers = getHeaders();
      const action = mod.active ? "deactivate" : "activate";
      const res = await fetch(`/api/v1/modules/${mod.key}/${action}`, {
        method: "POST",
        headers,
      });

      if (res.ok) {
        const updated = await res.json();
        setEntitlements(updated);
        setStatusMsg({
          type: "success",
          text: isFr
            ? `Module « ${mod.display_name} » ${mod.active ? "désactivé" : "activé"} avec succès.`
            : `Module "${mod.display_name}" ${mod.active ? "deactivated" : "activated"} successfully.`,
        });
      } else {
        const err = await res.json().catch(() => ({ detail: "Action impossible" }));
        setStatusMsg({
          type: "error",
          text: err.detail || (isFr ? "Action impossible avec votre plan actuel." : "Action not permitted on current plan."),
        });
      }
    } catch {
      setStatusMsg({
        type: "error",
        text: isFr ? "Erreur réseau lors de la mise à jour" : "Network error during update",
      });
    } finally {
      setUpdatingKey(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-white/[0.08] pb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2.5 rounded-xl bg-blue-50 dark:bg-[#111D3D] text-[#0076FF] border border-blue-200/40 dark:border-white/[0.08]">
              <Settings className="w-6 h-6" />
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {isFr ? "Paramètres de l'Organisation" : "Organization Settings"}
            </h1>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {isFr
              ? "Gérez les modules activés, les droits de votre abonnement et la sécurité de votre espace."
              : "Manage enabled modules, subscription plan entitlements, and organization security."}
          </p>
        </div>

        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors shadow-xs"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-[#0076FF]" : ""}`} />
          {isFr ? "Actualiser" : "Refresh"}
        </button>
      </div>

      {/* Status banner */}
      {statusMsg && (
        <div
          className={`p-4 rounded-xl text-sm flex items-center gap-3 border ${
            statusMsg.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/40 text-emerald-800 dark:text-emerald-300"
              : "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800/40 text-red-800 dark:text-red-300"
          }`}
        >
          {statusMsg.type === "success" ? <CheckCircle2 className="w-5 h-5 shrink-0" /> : <AlertTriangle className="w-5 h-5 shrink-0" />}
          <span>{statusMsg.text}</span>
        </div>
      )}

      {/* Organization and Subscription Overview Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {isFr ? "Organisation Active" : "Active Organization"}
            </span>
            <Building2 className="w-4 h-4 text-[#0076FF]" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white truncate">
              {company?.name || (isFr ? "Chargement..." : "Loading...")}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-1 truncate">
              ID: {company?.id || entitlements?.company_id || "—"}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04] text-xs text-slate-500">
            {isFr ? "Utilisateur :" : "User :"} <span className="font-medium text-slate-700 dark:text-slate-300">{user?.first_name} {user?.last_name} ({user?.role})</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {isFr ? "Abonnement & Plan" : "Subscription & Plan"}
            </span>
            <CreditCard className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white uppercase tracking-wide">
              {entitlements?.plan_code || company?.subscription_plan || "STANDARD"}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {isFr ? "Facturation centralisée et quotas d'IA" : "Centralized billing and AI allocations"}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04]">
            <Link
              href="/billing"
              className="text-xs font-medium text-[#0076FF] hover:underline flex items-center gap-1"
            >
              {isFr ? "Gérer l'abonnement et factures" : "Manage subscription & invoices"}
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {isFr ? "Quotas de Modules" : "Module Quotas"}
            </span>
            <Layers className="w-4 h-4 text-purple-500" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900 dark:text-white">
              {entitlements?.active_modules?.length || 0}
              {entitlements?.module_limit ? ` / ${entitlements.module_limit}` : ` ${isFr ? "activés" : "active"}`}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {entitlements?.remaining_module_slots !== null && entitlements?.remaining_module_slots !== undefined
                ? `${entitlements.remaining_module_slots} ${isFr ? "emplacements disponibles" : "slots available"}`
                : isFr ? "Modules illimités selon votre forfait" : "Unlimited modules per plan"}
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 dark:border-white/[0.04] text-xs text-slate-500">
            {isFr ? "Ségrégation multi-tenant garantie" : "Guaranteed multi-tenant isolation"}
          </div>
        </div>
      </div>

      {/* Module Entitlements Section */}
      <div className="bg-white dark:bg-[#0B132B] rounded-2xl border border-slate-200/80 dark:border-white/[0.08] p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 dark:border-white/[0.06] pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-[#0076FF]" />
              {isFr ? "Modules Métiers Disponibles" : "Available Business Modules"}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {isFr
                ? "Activez ou désactivez les modules autorisés pour cette organisation. Les modifications sont appliquées instantanément."
                : "Activate or deactivate authorized modules for this organization. Changes apply instantly."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs px-2.5 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 text-[#0076FF] font-medium border border-blue-200/60 dark:border-blue-700/40">
              {entitlements?.active_modules?.length || 0} {isFr ? "en ligne" : "online"}
            </span>
          </div>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-[#0076FF]" />
            <span className="text-sm">{isFr ? "Chargement des modules..." : "Loading modules..."}</span>
          </div>
        ) : !entitlements?.modules || entitlements.modules.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            {isFr ? "Aucun module configuré pour cette organisation." : "No modules configured for this organization."}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {entitlements.modules.map((mod) => {
              const isUpdating = updatingKey === mod.key;
              const isLocked = mod.state === "upgrade_required";

              return (
                <div
                  key={mod.key}
                  className={`p-4 rounded-xl border transition-all flex flex-col justify-between gap-4 ${
                    mod.active
                      ? "bg-blue-50/30 dark:bg-[#111D3D]/30 border-blue-200/80 dark:border-blue-900/50"
                      : "bg-slate-50/50 dark:bg-white/[0.02] border-slate-200/60 dark:border-white/[0.06]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-sm text-slate-900 dark:text-white">
                          {mod.display_name}
                        </span>
                        {mod.premium && (
                          <span className="text-[10px] px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 font-semibold uppercase">
                            Premium
                          </span>
                        )}
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-medium uppercase ${
                            mod.active
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                              : "bg-slate-100 text-slate-600 dark:bg-white/[0.06] dark:text-slate-400"
                          }`}
                        >
                          {mod.active ? (isFr ? "Actif" : "Active") : (isFr ? "Inactif" : "Inactive")}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                        {mod.description}
                      </p>
                    </div>

                    {isLocked ? (
                      <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400" title={isFr ? "Mise à niveau requise" : "Upgrade required"}>
                        <Lock className="w-4 h-4" />
                      </div>
                    ) : (
                      <button
                        onClick={() => handleToggleModule(mod)}
                        disabled={isUpdating}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                          mod.active ? "bg-[#0076FF]" : "bg-slate-300 dark:bg-slate-700"
                        } ${isUpdating ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                            mod.active ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-100 dark:border-white/[0.04] pt-2">
                    <span>{isFr ? "Catégorie :" : "Category :"} {mod.category}</span>
                    {mod.active && (
                      <Link
                        href={
                          mod.key === "accounting" ? "/accounting" :
                          mod.key === "marketing" ? "/marketing" :
                          mod.key === "retail" ? "/retail" :
                          mod.key === "crm" ? "/crm" :
                          "/dashboard"
                        }
                        className="text-[#0076FF] hover:underline flex items-center gap-1 font-medium"
                      >
                        {isFr ? "Accéder au module" : "Open module"}
                        <ChevronRight className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Security & Multi-Tenant Notice */}
      <div className="bg-slate-50 dark:bg-[#060B13] rounded-2xl p-6 border border-slate-200 dark:border-white/[0.08] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-blue-100 dark:bg-[#111D3D] text-[#0076FF] shrink-0">
            <Shield className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              {isFr ? "Sécurité & Isolation Multi-Tenant Avenqo" : "Avenqo Multi-Tenant Security & Isolation"}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-2xl">
              {isFr
                ? "Toutes les connexions de données, clés API, fichiers et modèles d'IA sont strictement scellés au niveau de l'organisation. Aucune fuite d'informations n'est permise entre locataires."
                : "All data connections, API keys, files, and AI models are strictly scoped to your tenant. Cross-tenant leakage is strictly prevented."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Link
            href="/connections"
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-[#0076FF] text-white hover:bg-blue-600 transition-colors shadow-xs"
          >
            {isFr ? "Connexions Données" : "Data Connections"}
          </Link>
          <Link
            href="/billing"
            className="px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-white/[0.1] bg-white dark:bg-[#0B132B] text-slate-700 dark:text-white hover:bg-slate-50 dark:hover:bg-white/[0.04] transition-colors shadow-xs"
          >
            {isFr ? "Facturation" : "Billing"}
          </Link>
        </div>
      </div>
    </div>
  );
}

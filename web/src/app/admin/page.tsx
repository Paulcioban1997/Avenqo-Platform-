"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/app-shell";
import {
  ShieldAlert,
  Building2,
  Users,
  CreditCard,
  Layers,
  Activity,
  CheckCircle2,
  Lock,
  ArrowLeft,
  FileSpreadsheet,
} from "lucide-react";
import { useLocale } from "@/lib/i18n/locale-context";

export default function AdminPage() {
  const { locale } = useLocale();
  const isFr = locale === "fr";

  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [company, setCompany] = useState<any>(null);

  useEffect(() => {
    async function checkAuth() {
      try {
        const token = typeof window !== "undefined"
          ? localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token")
          : null;
        if (!token) {
          setLoading(false);
          return;
        }
        const res = await fetch("/api/v1/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
          setCompany(data.company);
          if (data.user?.is_platform_admin || data.user?.role === "SUPER_ADMIN" || data.user?.role === "ADMIN") {
            setIsAdmin(true);
          }
        }
      } catch {}
      setLoading(false);
    }
    checkAuth();
  }, []);

  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
        {loading ? (
          <div className="py-20 text-center text-slate-400">
            {isFr ? "Vérification des droits d'administration..." : "Checking administrative permissions..."}
          </div>
        ) : !isAdmin ? (
          <div className="bg-white dark:bg-[#0B132B] rounded-3xl p-8 sm:p-12 border border-slate-200/80 dark:border-white/[0.08] text-center max-w-lg mx-auto space-y-4 shadow-lg">
            <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 flex items-center justify-center mx-auto">
              <Lock className="w-6 h-6" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              {isFr ? "Accès Réservé à l'Administration" : "Restricted Administrative Access"}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {isFr
                ? "Cette section est réservée aux administrateurs autorisés de la plateforme Avenqo. Votre compte actuel ne dispose pas des privilèges nécessaires."
                : "This section is restricted to authorized Avenqo platform administrators. Your account does not have the required privileges."}
            </p>
            <div className="pt-2">
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0076FF] text-white text-xs font-semibold hover:bg-blue-600 transition-colors shadow-xs"
              >
                <ArrowLeft className="w-4 h-4" />
                {isFr ? "Retour au Tableau de Bord" : "Return to Dashboard"}
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-white/[0.08] pb-6">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <div className="p-2.5 rounded-xl bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 border border-purple-200/40 dark:border-white/[0.08]">
                    <ShieldAlert className="w-6 h-6" />
                  </div>
                  <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                    {isFr ? "Console d'Administration Plateforme" : "Platform Admin Console"}
                  </h1>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {isFr
                    ? "Gestion globale des organisations, statuts d'infrastructure et audit des demandes de devis Enterprise."
                    : "Global tenant overview, infrastructure health, and Enterprise quote requests audit."}
                </p>
              </div>

              <span className="self-start sm:self-auto text-xs px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 font-semibold border border-emerald-200/60 dark:border-emerald-700/40 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {isFr ? "Mode Administrateur Actif" : "Admin Mode Active"}
              </span>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Organisation Courante" : "Current Organization"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 truncate">
                  {company?.name || "—"}
                </div>
                <div className="text-xs text-slate-400 mt-0.5 font-mono truncate">
                  Plan: {company?.subscription_plan || "Standard"}
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Rôle Opérateur" : "Operator Role"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1">
                  {user?.role || "ADMIN"}
                </div>
                <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">
                  {isFr ? "Privilèges étendus" : "Elevated privileges"}
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Infrastructure Backend" : "Backend Infrastructure"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span>api.avenqo.ca</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  FastAPI v1 • PostgreSQL • Redis
                </div>
              </div>

              <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-5 border border-slate-200/80 dark:border-white/[0.08] shadow-xs">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {isFr ? "Frontend Canonique" : "Canonical Frontend"}
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white mt-1 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <span>avenqo.ca</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  Next.js App Router • Vercel Edge
                </div>
              </div>
            </div>

            {/* Admin Management Links */}
            <div className="bg-white dark:bg-[#0B132B] rounded-2xl p-6 border border-slate-200/80 dark:border-white/[0.08] shadow-xs space-y-4">
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                {isFr ? "Actions Rapides d'Exploitation" : "Quick Operations"}
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Link
                  href="/settings"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <Layers className="w-5 h-5 text-[#0076FF]" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Modules & Entitlements" : "Modules & Entitlements"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Gérer les quotas par organisation" : "Manage per-tenant quotas"}
                    </div>
                  </div>
                </Link>

                <Link
                  href="/connections"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <Activity className="w-5 h-5 text-emerald-500" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Hub de Connexions" : "Connections Hub"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Auditer imports et synchronisations" : "Audit imports & synchronizations"}
                    </div>
                  </div>
                </Link>

                <Link
                  href="/billing"
                  className="p-4 rounded-xl border border-slate-200 dark:border-white/[0.08] bg-slate-50/50 dark:bg-white/[0.02] hover:bg-slate-100 dark:hover:bg-white/[0.04] transition-colors flex items-center gap-3"
                >
                  <CreditCard className="w-5 h-5 text-purple-500" />
                  <div>
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">
                      {isFr ? "Facturation & Factures" : "Billing & Invoices"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {isFr ? "Factures certifiées et crédits IA" : "Certified invoices & AI credits"}
                    </div>
                  </div>
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
